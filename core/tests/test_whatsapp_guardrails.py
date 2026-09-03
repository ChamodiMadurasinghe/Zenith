"""Unit tests for WhatsApp approved-sender guardrails."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.whatsapp_guardrails import is_approved_sender


class TestWhatsappGuardrails(unittest.TestCase):
    @patch("core.whatsapp_guardrails.list_active_approved_phones", return_value=[])
    @patch("core.whatsapp_guardrails.Config.whatsapp_allowed_numbers", return_value=[])
    def test_empty_whitelist_allows_all(self, *_mocks):
        self.assertTrue(is_approved_sender("+94771112222"))

    @patch(
        "core.whatsapp_guardrails.list_active_approved_phones",
        return_value=["+94771112222"],
    )
    @patch("core.whatsapp_guardrails.repo.is_sender_allowed", return_value=True)
    def test_db_allow(self, mock_allowed, *_):
        self.assertTrue(is_approved_sender("94771112222"))
        mock_allowed.assert_called()

    @patch(
        "core.whatsapp_guardrails.list_active_approved_phones",
        return_value=["+94771112222"],
    )
    @patch("core.whatsapp_guardrails.repo.is_sender_allowed", return_value=False)
    def test_db_deny(self, *_mocks):
        self.assertFalse(is_approved_sender("+94779998877"))

    @patch("core.whatsapp_guardrails.list_active_approved_phones", return_value=[])
    @patch(
        "core.whatsapp_guardrails.Config.whatsapp_allowed_numbers",
        return_value=["+94771112222"],
    )
    def test_env_fallback(self, *_mocks):
        self.assertTrue(is_approved_sender("94771112222"))
        self.assertFalse(is_approved_sender("+94770001111"))


if __name__ == "__main__":
    unittest.main()
