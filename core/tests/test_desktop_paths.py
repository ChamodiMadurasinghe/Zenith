import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import BASE_DIR, resolve_storage_path


class TestDesktopPaths(unittest.TestCase):
    def test_desktop_mode_uses_localappdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "ZENITH_DESKTOP": "true",
                "LOCALAPPDATA": tmp,
                "DATABASE_PATH": "database/invoice_cheque.db",
            }
            with patch.dict(os.environ, env, clear=False):
                path = resolve_storage_path("DATABASE_PATH", "database/invoice_cheque.db")
            self.assertEqual(path, Path(tmp) / "Zenith" / "invoice_cheque.db")

    def test_desktop_mode_keeps_absolute_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = Path(tmp) / "custom.db"
            env = {
                "ZENITH_DESKTOP": "true",
                "LOCALAPPDATA": tmp,
                "DATABASE_PATH": str(custom),
            }
            with patch.dict(os.environ, env, clear=False):
                path = resolve_storage_path("DATABASE_PATH", "database/invoice_cheque.db")
            self.assertEqual(path, custom)

    def test_project_mode_stays_in_repo(self):
        env = {"ZENITH_DESKTOP": "false", "DATABASE_PATH": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("DATABASE_PATH", None)
            path = resolve_storage_path("DATABASE_PATH", "database/invoice_cheque.db")
        self.assertEqual(path, BASE_DIR / "database" / "invoice_cheque.db")
