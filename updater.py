"""Remote update check and install for Zenith.

Check (`check_for_updates`) is separate from install (`apply_remote_update`) so
admins can inspect a changelog before applying a payload.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import requests
from packaging.version import InvalidVersion, parse as parse_version

APP_ROOT = Path(__file__).resolve().parent
CURRENT_VERSION = os.getenv("ZENITH_VERSION", "0.1.0").strip() or "0.1.0"
MANIFEST_URL = os.getenv("ZENITH_MANIFEST_URL", "").strip()

PRESERVE_FILES = frozenset({".env", "mycreds.txt"})
PRESERVE_DIRS = frozenset({"database", "storage"})
REQUEST_TIMEOUT_SEC = 10
DOWNLOAD_TIMEOUT_SEC = 60
RESTART_DELAY_SEC = 2


def check_for_updates() -> dict:
    """Fetch the remote manifest and compare it to CURRENT_VERSION."""
    if not MANIFEST_URL:
        return {"update_available": False, "error": "Offline or server unreachable"}

    try:
        resp = requests.get(MANIFEST_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        manifest = resp.json()
    except (requests.RequestException, ValueError):
        return {"update_available": False, "error": "Offline or server unreachable"}

    latest_version = str(manifest.get("latest_version") or "")
    try:
        update_available = parse_version(latest_version) > parse_version(CURRENT_VERSION)
    except InvalidVersion:
        update_available = False

    return {
        "update_available": update_available,
        "current_version": CURRENT_VERSION,
        "latest_version": latest_version,
        "changelog": manifest.get("changelog", ""),
        "release_date": manifest.get("release_date", ""),
        "has_new_deps": manifest.get("has_new_deps", False),
        "download_url": manifest.get("download_url", ""),
    }


def apply_remote_update(manifest_data=None) -> bool:
    """Download and install a remote payload, then schedule a process restart."""
    info = manifest_data if isinstance(manifest_data, dict) else check_for_updates()

    if info.get("error") or not info.get("download_url"):
        return False

    zip_path = None
    try:
        zip_path = _download_to_temp(str(info["download_url"]))
        _extract_payload_zip(zip_path, APP_ROOT)
        _run_alembic_upgrade()
        if info.get("has_new_deps"):
            _install_requirements()
        holiday_url = info.get("holiday_pack_url") or ""
        if holiday_url:
            _install_holiday_pack(str(holiday_url))
        restart_application()
        return True
    finally:
        _unlink_quiet(zip_path)


def restart_application() -> None:
    """Replace this process after a short delay so the HTTP response can flush."""

    def _restart():
        time.sleep(RESTART_DELAY_SEC)
        os.execv(sys.executable, [sys.executable, *sys.argv])

    threading.Thread(target=_restart, daemon=True).start()


def _unlink_quiet(path: Path | str | None) -> None:
    if path is None:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _download_to_temp(url: str, suffix: str = ".zip") -> Path:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.close()
    path = Path(tmp.name)
    try:
        with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            resp.raise_for_status()
            with path.open("wb") as handle:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        handle.write(chunk)
        return path
    except Exception:
        _unlink_quiet(path)
        raise


def _extract_payload_zip(zip_path: Path, dest: Path) -> None:
    dest_resolved = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            relative = _safe_relative_path(info.filename)
            if relative is None or _is_preserved(relative):
                continue
            target = (dest / relative).resolve()
            try:
                target.relative_to(dest_resolved)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                out.write(src.read())


def _install_holiday_pack(url: str) -> None:
    packs_dir = APP_ROOT / "storage" / "packs"
    packs_dir.mkdir(parents=True, exist_ok=True)
    pack_path = _download_to_temp(url)
    try:
        dest_resolved = packs_dir.resolve()
        with zipfile.ZipFile(pack_path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                relative = _safe_relative_path(info.filename)
                if relative is None:
                    continue
                target = (packs_dir / relative).resolve()
                try:
                    target.relative_to(dest_resolved)
                except ValueError:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as out:
                    out.write(src.read())
    finally:
        _unlink_quiet(pack_path)


def _safe_relative_path(name: str) -> Path | None:
    cleaned = name.replace("\\", "/").lstrip("/")
    if not cleaned:
        return None
    relative = Path(cleaned)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return relative


def _is_preserved(relative: Path) -> bool:
    if not relative.parts:
        return False
    if relative.parts[0] in PRESERVE_DIRS:
        return True
    if relative.name in PRESERVE_FILES and len(relative.parts) == 1:
        return True
    return False


def _run_alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    ini_path = APP_ROOT / "alembic.ini"
    cfg = AlembicConfig(str(ini_path))
    cfg.set_main_option("script_location", str(APP_ROOT / "alembic"))
    command.upgrade(cfg, "head")


def _install_requirements() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(APP_ROOT / "requirements.txt")],
    )
