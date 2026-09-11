"""Disaster-recovery backup: SQLite + invoices + Chroma → AES-256-GCM zip → Google Drive."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import BASE_DIR, Config

logger = logging.getLogger(__name__)

PBKDF2_SALT = b"zenith_chequemate_salt_2026"
PBKDF2_ITERATIONS = 100_000
AES_KEY_BYTES = 32
GCM_NONCE_BYTES = 16
GCM_TAG_BYTES = 16
CHUNK_SIZE = 1024 * 1024
ZIP_DB_ARCNAME = "database/invoice_cheque.db"
ZIP_INVOICES_PREFIX = "storage/invoices"
ZIP_CHROMA_PREFIX = "chroma"
BACKUP_TITLE_PREFIX = "Zenith_Backup_"
BACKUP_TITLE_SUFFIX = ".enc"


def _resolve_db_path(db_path: Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else Path(Config.DATABASE_PATH)


def _resolve_invoices_dir(invoices_dir: Path | None = None) -> Path:
    return Path(invoices_dir) if invoices_dir is not None else Path(Config.UPLOAD_FOLDER)


def _resolve_chroma_dir(chroma_dir: Path | None = None) -> Path:
    if chroma_dir is not None:
        return Path(chroma_dir)
    configured = Path(Config.chroma_persist_dir())
    if configured.exists():
        return configured
    return BASE_DIR / "chroma"


def _resolve_creds_path(creds_path: Path | None = None) -> Path:
    if creds_path is not None:
        return Path(creds_path)
    return Path(Config.gdrive_credentials_path())


def _derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        PBKDF2_SALT,
        PBKDF2_ITERATIONS,
        dklen=AES_KEY_BYTES,
    )


def _safe_copy_sqlite(src: Path, dest: Path) -> None:
    """Copy a live SQLite database via the backup API so writers are not blocked."""
    if not src.exists():
        raise FileNotFoundError(f"SQLite database not found at {src}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(str(src), timeout=30.0)
    try:
        dest_conn = sqlite3.connect(str(dest), timeout=30.0)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Failed to copy SQLite database from {src} (file may be locked): {exc}"
        ) from exc
    finally:
        source_conn.close()


def _add_directory(zf: zipfile.ZipFile, source: Path, arc_prefix: str) -> None:
    if not source.exists() or not source.is_dir():
        logger.info("Skipping missing backup directory %s", source)
        return
    count = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source).as_posix()
        zf.write(path, arcname=f"{arc_prefix}/{rel}")
        count += 1
    logger.info("Added %s file(s) from %s as %s/", count, source, arc_prefix)


def create_backup_zip(
    db_path: Path | None = None,
    invoices_dir: Path | None = None,
    chroma_dir: Path | None = None,
) -> Path:
    """Bundle SQLite, invoice images, and Chroma files into a temporary zip.

    Returns the temporary zip path. The SQLite snapshot ``temp_sqlite_copy.db``
    is deleted before return.
    """
    src_db = _resolve_db_path(db_path)
    src_invoices = _resolve_invoices_dir(invoices_dir)
    src_chroma = _resolve_chroma_dir(chroma_dir)

    tmp_dir = Path(tempfile.mkdtemp(prefix="zenith_backup_"))
    sqlite_copy = tmp_dir / "temp_sqlite_copy.db"
    zip_path = tmp_dir / "zenith_backup.zip"

    try:
        logger.info("Snapshotting SQLite database from %s", src_db)
        _safe_copy_sqlite(src_db, sqlite_copy)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(sqlite_copy, arcname=ZIP_DB_ARCNAME)
            _add_directory(zf, src_invoices, ZIP_INVOICES_PREFIX)
            _add_directory(zf, src_chroma, ZIP_CHROMA_PREFIX)
        logger.info("Backup archive created at %s", zip_path)
        return zip_path
    except Exception:
        zip_path.unlink(missing_ok=True)
        sqlite_copy.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        sqlite_copy.unlink(missing_ok=True)


def encrypt_archive(zip_path: Path | str, passphrase: str) -> Path:
    """Encrypt a zip with AES-256-GCM. Output: nonce(16) + tag(16) + ciphertext."""
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes

    src = Path(zip_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup zip not found at {src}")
    if not passphrase:
        raise ValueError("Backup passphrase is required")

    enc_path = src.with_suffix(".enc")
    key = _derive_key(passphrase)
    nonce = get_random_bytes(GCM_NONCE_BYTES)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=GCM_TAG_BYTES)

    logger.info("Encrypting backup archive with AES-256-GCM")
    try:
        with src.open("rb") as inf, enc_path.open("wb") as outf:
            outf.write(nonce)
            tag_offset = outf.tell()
            outf.write(b"\x00" * GCM_TAG_BYTES)
            while True:
                chunk = inf.read(CHUNK_SIZE)
                if not chunk:
                    break
                outf.write(cipher.encrypt(chunk))
            tag = cipher.digest()
            if len(tag) != GCM_TAG_BYTES:
                raise RuntimeError("Unexpected GCM tag length")
            outf.seek(tag_offset)
            outf.write(tag)
    except Exception:
        enc_path.unlink(missing_ok=True)
        raise
    logger.info("Encrypted backup written to %s", enc_path)
    return enc_path


def _is_managed_backup_title(title: str | None) -> bool:
    name = (title or "").strip()
    return name.startswith(BACKUP_TITLE_PREFIX) and name.endswith(BACKUP_TITLE_SUFFIX)


def _purge_old_drive_backups(drive, keep_title: str) -> int:
    """Delete previous Zenith_Backup_*.enc files, keeping only keep_title."""
    query = f"title contains '{BACKUP_TITLE_PREFIX}' and trashed=false"
    removed = 0
    try:
        old_files = drive.ListFile({"q": query, "maxResults": 100}).GetList()
    except Exception as exc:
        logger.warning("Could not list previous Google Drive backups: %s", exc)
        return 0
    for remote in old_files:
        try:
            title = remote["title"]
        except Exception:
            title = ""
        if title == keep_title or not _is_managed_backup_title(title):
            continue
        try:
            remote.Delete()
            removed += 1
            logger.info("Deleted previous Google Drive backup %s", title)
        except Exception as exc:
            logger.warning("Could not delete previous backup %s: %s", title, exc)
    return removed


def upload_to_gdrive(enc_path: Path | str, creds_path: Path | None = None) -> str:
    """Upload an encrypted backup silently using saved PyDrive2 credentials."""
    try:
        from pydrive2.auth import GoogleAuth
        from pydrive2.drive import GoogleDrive
    except ImportError as exc:
        raise RuntimeError(
            "PyDrive2 is required for Google Drive backup. Install with: pip install PyDrive2"
        ) from exc

    src = Path(enc_path)
    if not src.exists():
        raise FileNotFoundError(f"Encrypted backup not found at {src}")

    creds = _resolve_creds_path(creds_path)
    if not creds.exists():
        raise FileNotFoundError(
            f"Google Drive credentials not found at {creds}. "
            "Place a PyDrive2 token file (mycreds.txt) next to the app before backing up."
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    title = f"Zenith_Backup_{stamp}.enc"

    try:
        gauth = GoogleAuth()
        gauth.LoadCredentialsFile(str(creds))
        if gauth.credentials is None:
            raise RuntimeError(
                f"Google Drive credentials in {creds} are empty or invalid."
            )
        if gauth.access_token_expired:
            logger.info("Refreshing Google Drive access token")
            gauth.Refresh()
            gauth.SaveCredentialsFile(str(creds))
        else:
            gauth.Authorize()

        drive = GoogleDrive(gauth)
        remote = drive.CreateFile({"title": title})
        remote.SetContentFile(str(src))
        remote.Upload()
        removed = _purge_old_drive_backups(drive, keep_title=title)
        if removed:
            logger.info("Removed %s previous Google Drive backup(s)", removed)
    except Exception as exc:
        if isinstance(exc, (FileNotFoundError, RuntimeError)) and "Google Drive" in str(exc):
            raise
        raise RuntimeError(f"Failed to upload backup to Google Drive: {exc}") from exc

    logger.info("Uploaded backup to Google Drive as %s", title)
    return title


def _unlink_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent.name.startswith("zenith_backup_"):
            try:
                parent.rmdir()
            except OSError:
                pass
    except OSError as exc:
        logger.warning("Could not remove temporary file %s: %s", path, exc)


def run_backup_pipeline(passphrase: str, **paths) -> str:
    """Create, encrypt, and upload a backup. Always deletes local .zip and .enc files.

    Returns the Google Drive file title. Exceptions bubble with informative messages;
    callers must catch them so worker threads are not killed.
    """
    if not passphrase or not str(passphrase).strip():
        raise ValueError("Backup passphrase is required")

    zip_path: Path | None = None
    enc_path: Path | None = None
    try:
        zip_path = create_backup_zip(
            db_path=paths.get("db_path"),
            invoices_dir=paths.get("invoices_dir"),
            chroma_dir=paths.get("chroma_dir"),
        )
        enc_path = encrypt_archive(zip_path, str(passphrase).strip())
        return upload_to_gdrive(enc_path, creds_path=paths.get("creds_path"))
    finally:
        _unlink_quietly(zip_path)
        _unlink_quietly(enc_path)
