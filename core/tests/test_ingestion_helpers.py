import unittest
from unittest.mock import MagicMock

from core.ingestion_helpers import (
    compute_item_line_total,
    normalize_line_item,
    parse_items_from_form,
)


class TestInvoiceLineItemFields(unittest.TestCase):
    def test_compute_line_total_with_percent_discount(self):
        self.assertEqual(compute_item_line_total(10, 100, 10), 900.0)

    def test_normalize_fills_line_total(self):
        item = normalize_line_item(
            {"item_code": "A", "item_name": "Bulb", "item_qty": 2, "item_price": 50, "item_discount": 0, "item_mrp": 80}
        )
        self.assertEqual(item["item_mrp"], 80.0)
        self.assertEqual(item["item_price"], 50.0)
        self.assertEqual(item["item_line_total"], 100.0)

    def test_parse_form_reads_mrp_discount_prices(self):
        form = MagicMock()
        form.getlist.side_effect = lambda name: {
            "item_code": ["SKU1", ""],
            "item_name": ["Lamp", ""],
            "item_qty": ["4", "1"],
            "item_mrp": ["200", "0"],
            "item_price": ["150", "0"],
            "item_discount": ["10", "0"],
            "item_line_total": ["540", "0"],
        }[name]
        items = parse_items_from_form(form)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_mrp"], 200.0)
        self.assertEqual(items[0]["item_price"], 150.0)
        self.assertEqual(items[0]["item_discount"], 10.0)
        self.assertEqual(items[0]["item_line_total"], 540.0)


if __name__ == "__main__":
    unittest.main()
