import unittest
from unittest.mock import patch

from db import repositories as repo


class TestWhatsappWhitelistRepository(unittest.TestCase):
    def setUp(self):
        repo.ensure_whatsapp_allowed_senders_schema()

    def test_crud_allowed_sender(self):
        sender_id = repo.add_allowed_sender("+94779998877", "Test Co")
        rows = repo.list_allowed_senders()
        self.assertTrue(any(r["sender_id"] == sender_id for r in rows))
        self.assertTrue(repo.is_sender_allowed("+94779998877"))
        repo.update_allowed_sender(sender_id, display_name="Updated Co", is_active=False)
        self.assertFalse(repo.is_sender_allowed("+94779998877"))
        repo.update_allowed_sender(sender_id, is_active=True)
        self.assertTrue(repo.is_sender_allowed("+94779998877"))
        repo.remove_allowed_sender(sender_id)
        self.assertFalse(repo.is_sender_allowed("+94779998877"))

    @patch("db.repositories._env_merchant_whatsapp_phone", return_value="")
    def test_merchant_whatsapp_phone(self, _env):
        repo.save_merchant_whatsapp_phone("0771234567")
        self.assertEqual(repo.get_merchant_whatsapp_phone(), "+94771234567")
        repo.clear_merchant_whatsapp_phone()
        self.assertEqual(repo.get_merchant_whatsapp_phone(), "")


if __name__ == "__main__":
    unittest.main()
