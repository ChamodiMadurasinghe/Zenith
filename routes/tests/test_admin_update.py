import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

import updater
from app import create_app
from config import Config


def _manifest(**overrides):
    data = {
        "latest_version": "1.1.0",
        "changelog": "Bug fixes",
        "release_date": "2026-09-11",
        "has_new_deps": False,
        "download_url": "https://example.com/zenith-1.1.0.zip",
    }
    data.update(overrides)
    return data


class TestCheckForUpdates(unittest.TestCase):
    def test_newer_version_is_available(self):
        resp = MagicMock()
        resp.json.return_value = _manifest()
        resp.raise_for_status.return_value = None
        with patch.object(updater, "MANIFEST_URL", "https://example.com/manifest.json"), patch.object(
            updater, "CURRENT_VERSION", "1.0.0"
        ), patch("updater.requests.get", return_value=resp) as mock_get:
            result = updater.check_for_updates()
        mock_get.assert_called_once()
        self.assertTrue(result["update_available"])
        self.assertEqual(result["current_version"], "1.0.0")
        self.assertEqual(result["latest_version"], "1.1.0")
        self.assertEqual(result["changelog"], "Bug fixes")
        self.assertEqual(result["release_date"], "2026-09-11")
        self.assertEqual(result["has_new_deps"], False)
        self.assertEqual(result["download_url"], "https://example.com/zenith-1.1.0.zip")

    def test_equal_versions_not_available(self):
        resp = MagicMock()
        resp.json.return_value = _manifest(latest_version="1.0.0")
        resp.raise_for_status.return_value = None
        with patch.object(updater, "MANIFEST_URL", "https://example.com/manifest.json"), patch.object(
            updater, "CURRENT_VERSION", "1.0.0"
        ), patch("updater.requests.get", return_value=resp):
            result = updater.check_for_updates()
        self.assertFalse(result["update_available"])
        self.assertEqual(result["latest_version"], "1.0.0")

    def test_timeout_returns_offline_error(self):
        with patch.object(updater, "MANIFEST_URL", "https://example.com/manifest.json"), patch(
            "updater.requests.get", side_effect=requests.Timeout("timed out")
        ):
            result = updater.check_for_updates()
        self.assertEqual(
            result,
            {"update_available": False, "error": "Offline or server unreachable"},
        )

    def test_connection_error_returns_offline_error(self):
        with patch.object(updater, "MANIFEST_URL", "https://example.com/manifest.json"), patch(
            "updater.requests.get",
            side_effect=requests.ConnectionError("dns"),
        ):
            result = updater.check_for_updates()
        self.assertFalse(result["update_available"])
        self.assertEqual(result["error"], "Offline or server unreachable")

    def test_empty_manifest_url_is_offline(self):
        with patch.object(updater, "MANIFEST_URL", ""):
            result = updater.check_for_updates()
        self.assertEqual(
            result,
            {"update_available": False, "error": "Offline or server unreachable"},
        )


class TestApplyRemoteUpdate(unittest.TestCase):
    def test_apply_remote_update_uses_manifest_and_restarts(self):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        handle.close()
        tmp = Path(handle.name)
        try:
            with patch.object(updater, "_download_to_temp", return_value=tmp), patch.object(
                updater, "_extract_payload_zip"
            ), patch.object(updater, "_run_alembic_upgrade"), patch.object(
                updater, "_install_requirements"
            ) as pip, patch.object(updater, "restart_application") as restart:
                ok = updater.apply_remote_update(_manifest())
            self.assertTrue(ok)
            restart.assert_called_once()
            pip.assert_not_called()
        finally:
            tmp.unlink(missing_ok=True)

    def test_apply_remote_update_false_without_download_url(self):
        self.assertFalse(updater.apply_remote_update({"latest_version": "1.1.0"}))


class TestAdminUpdateRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID

    def test_check_update_requires_login(self):
        resp = self.client.get("/api/admin/check-update")
        self.assertEqual(resp.status_code, 401)

    def test_apply_update_requires_login(self):
        resp = self.client.post("/api/admin/apply-update", json={})
        self.assertEqual(resp.status_code, 401)

    def test_check_update_maps_offline_message(self):
        self._login()
        offline = {"update_available": False, "error": "Offline or server unreachable"}
        with patch("updater.check_for_updates", return_value=offline):
            resp = self.client.get("/api/admin/check-update")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["update_available"])
        self.assertEqual(data["message"], "System is offline or central server unreachable")

    def test_check_update_returns_manifest_fields(self):
        self._login()
        payload = {
            "update_available": True,
            "current_version": "1.0.0",
            "latest_version": "1.1.0",
            "changelog": "Bug fixes",
            "release_date": "2026-09-11",
            "has_new_deps": False,
            "download_url": "https://example.com/zenith-1.1.0.zip",
        }
        with patch("updater.check_for_updates", return_value=payload):
            resp = self.client.get("/api/admin/check-update")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["latest_version"], "1.1.0")
        self.assertEqual(resp.get_json()["changelog"], "Bug fixes")

    def test_apply_update_success_returns_restarting(self):
        self._login()
        body = _manifest()
        with patch("updater.apply_remote_update", return_value=True) as mock_apply:
            resp = self.client.post("/api/admin/apply-update", json=body)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "restarting")
        self.assertIn("v1.1.0", data["message"])
        self.assertIn("restart", data["message"].lower())
        mock_apply.assert_called_once()

    def test_apply_update_false_returns_500(self):
        self._login()
        with patch("updater.apply_remote_update", return_value=False):
            resp = self.client.post("/api/admin/apply-update", json=_manifest())
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Update failed. App remains on current version.")

    def test_apply_update_exception_returns_500(self):
        self._login()
        with patch("updater.apply_remote_update", side_effect=RuntimeError("boom")):
            resp = self.client.post("/api/admin/apply-update", json=_manifest())
        self.assertEqual(resp.status_code, 500)
        data = resp.get_json()
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["message"], "Update failed. App remains on current version.")


if __name__ == "__main__":
    unittest.main()
