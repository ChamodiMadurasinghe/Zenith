import unittest
from datetime import date
from unittest.mock import MagicMock

from core.dates import (
    impossible_days_from_form,
    is_impossible_day,
    parse_impossible_days,
)


class TestImpossibleDays(unittest.TestCase):
    def test_parses_mixed_case_and_order(self):
        self.assertEqual(parse_impossible_days("Sunday, monday"), "Monday, Sunday")

    def test_parses_checkbox_list(self):
        self.assertEqual(parse_impossible_days(["Friday", "Sunday"]), "Friday, Sunday")

    def test_ignores_unknown_days(self):
        self.assertEqual(parse_impossible_days("Funday, Sunday"), "Sunday")

    def test_empty(self):
        self.assertEqual(parse_impossible_days(""), "")
        self.assertEqual(parse_impossible_days([]), "")

    def test_form_checkboxes_none_selected(self):
        form = MagicMock()
        form.get.side_effect = lambda key, default=None: "1" if key == "impossible_days_present" else default
        form.getlist.return_value = []
        self.assertEqual(impossible_days_from_form(form), "")

    def test_form_checkboxes_selected(self):
        form = MagicMock()
        form.get.side_effect = lambda key, default=None: "1" if key == "impossible_days_present" else default
        form.getlist.return_value = ["Sunday", "Wednesday"]
        self.assertEqual(impossible_days_from_form(form), "Wednesday, Sunday")

    def test_legacy_text_field(self):
        form = MagicMock()
        form.get.side_effect = lambda key, default=None: "Sunday, monday" if key == "impossible_days" else None
        form.getlist.return_value = ["Sunday, monday"]
        self.assertEqual(impossible_days_from_form(form), "Monday, Sunday")

    def test_is_impossible_day_is_case_insensitive(self):
        sunday = date(2026, 9, 6)
        self.assertTrue(is_impossible_day(sunday, "sunday"))
        self.assertFalse(is_impossible_day(sunday, "Monday"))


if __name__ == "__main__":
    unittest.main()
