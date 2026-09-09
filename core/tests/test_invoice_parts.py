import unittest

from core.invoice_parts import equal_part_amounts, make_split_parts


class TestInvoiceParts(unittest.TestCase):
    def test_equal_three_way_split_sums_to_original(self):
        amounts = equal_part_amounts(600000.0, 3)
        self.assertEqual(len(amounts), 3)
        self.assertEqual(round(sum(amounts), 2), 600000.0)
        self.assertTrue(all(a > 0 for a in amounts))

    def test_equal_split_rounding_on_last_part(self):
        amounts = equal_part_amounts(100.0, 3)
        self.assertEqual(amounts[0], 33.33)
        self.assertEqual(amounts[1], 33.33)
        self.assertEqual(amounts[2], 33.34)
        self.assertEqual(round(sum(amounts), 2), 100.0)

    def test_make_split_parts_three_way(self):
        inv = {
            "invoices_id": 10,
            "invoice_no": "INV-A",
            "total_amount": 600000.0,
        }
        parts = make_split_parts(inv, [200000.0, 200000.0, 200000.0])
        self.assertEqual(len(parts), 3)
        for i, part in enumerate(parts, start=1):
            self.assertEqual(part["part_index"], i)
            self.assertEqual(part["part_count"], 3)
            self.assertEqual(part["original_amount"], 600000.0)
            self.assertEqual(part["total_amount"], 200000.0)

    def test_make_split_parts_rejects_sum_mismatch(self):
        inv = {"invoices_id": 10, "invoice_no": "INV-A", "total_amount": 100.0}
        with self.assertRaises(ValueError):
            make_split_parts(inv, [40.0, 40.0])


if __name__ == "__main__":
    unittest.main()
