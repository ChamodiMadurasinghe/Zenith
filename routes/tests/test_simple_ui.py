import unittest
from datetime import date

from app import create_app
from config import Config
from core.i18n import MESSAGES, translate
from core.i18n_simple import SIMPLE_MESSAGES
from core.ui.format import initials, long_date
from core.ui.nav import MAIN_ITEMS, SETTINGS_ITEM, is_active


class TestSimpleShell(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _login(self, lang="en"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = Config.USER_ID
            sess["lang"] = lang

    def test_preview_requires_login(self):
        resp = self.client.get("/ui/preview")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_preview_renders_shell_and_components(self):
        self._login()
        resp = self.client.get("/ui/preview")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        # Shell: sidebar, language switch, help, account menu with logout, mobile dock.
        for text in ("What to do now", "Check new bills", "Is there enough?", "Shop, bank, printer",
                     "Need help? Call us", "සිංහල", "தமிழ்", "Log out", "Add a photo of an invoice"):
            self.assertIn(text, html)
        self.assertIn("simple/tokens.css", html)
        self.assertIn("simple/icons.svg#i-home", html)
        self.assertIn(long_date(date.today(), "en"), html)

    def test_preview_in_sinhala(self):
        self._login("si")
        html = self.client.get("/ui/preview").get_data(as_text=True)
        self.assertIn("දැන් කළ යුතු දේ", html)
        self.assertIn('lang="si"', html)

    def test_classic_home_unchanged(self):
        self._login()
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("simple/app.css", resp.get_data(as_text=True))


class TestSimpleHelpers(unittest.TestCase):
    def test_initials(self):
        self.assertEqual(initials("Perera Hardware (Pvt) Ltd"), "PH")
        self.assertEqual(initials("admin"), "AD")
        self.assertEqual(initials("Mala Silva"), "MS")
        self.assertEqual(initials(""), "?")
        self.assertEqual(initials(None), "?")

    def test_long_date(self):
        d = date(2026, 10, 14)
        self.assertEqual(long_date(d, "en"), "Wednesday, 14 October")
        self.assertEqual(long_date(d, "ta"), "புதன், 14 அக்டோபர்")

    def test_nav_active_state(self):
        today, invoices, cheques, money = MAIN_ITEMS
        self.assertTrue(is_active(today, "simple.today"))
        self.assertFalse(is_active(today, "simple.invoices"))
        self.assertTrue(is_active(invoices, "simple.invoice_check"))
        self.assertTrue(is_active(cheques, "simple.supplier"))
        self.assertTrue(is_active(money, "simple.money_deposit"))
        self.assertTrue(is_active(SETTINGS_ITEM, "simple.settings"))
        self.assertFalse(is_active(money, None))

    def test_every_simple_key_is_translated(self):
        english = set(SIMPLE_MESSAGES["en"])
        for lang in ("si", "ta"):
            self.assertEqual(english, set(SIMPLE_MESSAGES[lang]), lang)
        self.assertEqual(translate("s_nav_money", "en"), "Money")
        self.assertIn("s_nav_today", MESSAGES["si"])


if __name__ == "__main__":
    unittest.main()
