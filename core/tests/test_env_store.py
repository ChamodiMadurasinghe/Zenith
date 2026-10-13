import tempfile
import unittest
from pathlib import Path

from core.env_store import update_keys


class TestEnvStore(unittest.TestCase):
    def test_upsert_keeps_other_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("HOST=127.0.0.1\nAPP_PASSWORD=old\n", encoding="utf-8")
            update_keys({"APP_PASSWORD": "new", "USE_FAKE_AI": "true"}, path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("HOST=127.0.0.1", text)
        self.assertIn("APP_PASSWORD=new", text)
        self.assertIn("USE_FAKE_AI=true", text)
        self.assertNotIn("APP_PASSWORD=old", text)
