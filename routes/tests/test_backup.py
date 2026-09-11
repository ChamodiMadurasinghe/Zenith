import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import create_app, is_internet_available
from backup_engine import (
    GCM_NONCE_BYTES,
    GCM_TAG_BYTES,
    ZIP_CHROMA_PREFIX,
    ZIP_DB_ARCNAME,
    ZIP_INVOICES_PREFIX,
    _derive_key,
    _purge_old_drive_backups,
    create_backup_zip,
    encrypt_archive,
    run_backup_pipeline,
)
from config import Config


def _make_sqlite(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES ('zenith')")
        conn.commit()
    finally:
        conn.close()


class TestBackupEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="zenith_backup_test_"))
        self.db_path = self.tmp / "invoice_cheque.db"
        self.invoices = self.tmp / "invoices"
        self.chroma = self.tmp / "chroma"
        self.invoices.mkdir()
        self.chroma.mkdir()
        _make_sqlite(self.db_path)
        (self.invoices / "inv-1.jpg").write_bytes(b"fake-image")
        (self.chroma / "chroma.sqlite3").write_bytes(b"vec")

    def tearDown(self):
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.tmp.rmdir()

    def test_create_backup_zip_internal_paths(self):
        zip_path = create_backup_zip(self.db_path, self.invoices, self.chroma)
        self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
        self.assertTrue(zip_path.exists())
        self.assertFalse((zip_path.parent / "temp_sqlite_copy.db").exists())
        with zipfile.ZipFile(zip_path) as zf:
            names = set(zf.namelist())
        self.assertIn(ZIP_DB_ARCNAME, names)
        self.assertIn(f"{ZIP_INVOICES_PREFIX}/inv-1.jpg", names)
        self.assertIn(f"{ZIP_CHROMA_PREFIX}/chroma.sqlite3", names)
        with zipfile.ZipFile(zip_path) as zf:
            extracted = self.tmp / "extracted.db"
            extracted.write_bytes(zf.read(ZIP_DB_ARCNAME))
        conn = sqlite3.connect(str(extracted))
        try:
            row = conn.execute("SELECT v FROM t").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "zenith")

    def test_encrypt_archive_nonce_tag_ciphertext(self):
        from Crypto.Cipher import AES

        zip_path = create_backup_zip(self.db_path, self.invoices, self.chroma)
        self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
        original = zip_path.read_bytes()
        enc_path = encrypt_archive(zip_path, "test-passphrase-not-for-prod")
        self.addCleanup(lambda: enc_path.unlink(missing_ok=True))
        blob = enc_path.read_bytes()
        self.assertGreater(len(blob), GCM_NONCE_BYTES + GCM_TAG_BYTES)
        nonce = blob[:GCM_NONCE_BYTES]
        tag = blob[GCM_NONCE_BYTES : GCM_NONCE_BYTES + GCM_TAG_BYTES]
        ciphertext = blob[GCM_NONCE_BYTES + GCM_TAG_BYTES :]
        cipher = AES.new(
            _derive_key("test-passphrase-not-for-prod"),
            AES.MODE_GCM,
            nonce=nonce,
            mac_len=GCM_TAG_BYTES,
        )
        self.assertEqual(cipher.decrypt_and_verify(ciphertext, tag), original)

    def test_pipeline_cleans_temp_files_when_upload_fails(self):
        with patch(
            "backup_engine.upload_to_gdrive",
            side_effect=RuntimeError("drive down"),
        ):
            with self.assertRaises(RuntimeError):
                run_backup_pipeline(
                    "test-passphrase-not-for-prod",
                    db_path=self.db_path,
                    invoices_dir=self.invoices,
                    chroma_dir=self.chroma,
                )

    def test_pipeline_rejects_empty_passphrase(self):
        with self.assertRaises(ValueError):
            run_backup_pipeline("  ")

    def test_purge_deletes_old_backups_keeps_latest(self):
        keep = "Zenith_Backup_20260911_210000.enc"
        old = MagicMock()
        old.__getitem__.side_effect = lambda key: "Zenith_Backup_20260910_010000.enc"
        other = MagicMock()
        other.__getitem__.side_effect = lambda key: "not-a-backup.txt"
        latest = MagicMock()
        latest.__getitem__.side_effect = lambda key: keep
        drive = MagicMock()
        drive.ListFile.return_value.GetList.return_value = [old, other, latest]
        removed = _purge_old_drive_backups(drive, keep)
        self.assertEqual(removed, 1)
        old.Delete.assert_called_once()
        other.Delete.assert_not_called()
        latest.Delete.assert_not_called()


class TestBackupRoute(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID

    def test_backup_requires_login(self):
        resp = self.client.post("/api/backup/now", json={})
        self.assertEqual(resp.status_code, 401)

    def test_offline_returns_warning(self):
        self._login()
        with patch("app.is_internet_available", return_value=False):
            resp = self.client.post("/api/backup/now", json={"passphrase": "x"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "warning")
        self.assertIn("No internet connection detected", data["message"])

    def test_success_returns_drive_title(self):
        self._login()
        title = "Zenith_Backup_20260911_153000.enc"
        with patch("app.is_internet_available", return_value=True), patch(
            "app.run_backup_pipeline", return_value=title
        ) as mock_run:
            resp = self.client.post("/api/backup/now", json={"passphrase": "secret"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["file_name"], title)
        self.assertIn(title, data["message"])
        mock_run.assert_called_once_with("secret")

    def test_failure_returns_500_without_crashing(self):
        self._login()
        with patch("app.is_internet_available", return_value=True), patch(
            "app.run_backup_pipeline", side_effect=RuntimeError("upload denied")
        ):
            resp = self.client.post("/api/backup/now", json={"passphrase": "secret"})
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("Backup failed: upload denied", data["message"])
        self.assertIn("Core app continues running", data["message"])

    def test_is_internet_available_false_on_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(is_internet_available(timeout=1))

    def test_settings_menu_includes_backup_button_when_logged_in(self):
        self._login()
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("backup-now-btn", html)
        self.assertIn("Backup to Google Drive", html)
        self.assertIn("js/backup.js", html)

    def test_settings_menu_hides_backup_button_when_logged_out(self):
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn("backup-now-btn", html)


if __name__ == "__main__":
    unittest.main()
