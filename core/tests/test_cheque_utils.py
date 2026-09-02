import unittest

from core.cheque_utils import format_cheque_amount_in_words, resolve_bank_code


class TestChequeUtils(unittest.TestCase):
    def test_format_large_amount_with_cents(self):
        result = format_cheque_amount_in_words(150000.50)
        self.assertIn("One Hundred Fifty Thousand Rupees", result)
        self.assertIn("And Fifty Cents", result)
        self.assertNotRegex(result, r"\d")
        self.assertTrue(result.endswith("Only ***"))

    def test_format_zero(self):
        self.assertEqual(format_cheque_amount_in_words(0), "Zero Rupees Only ***")

    def test_format_one_rupee(self):
        self.assertEqual(format_cheque_amount_in_words(1), "One Rupees Only ***")

    def test_format_million(self):
        result = format_cheque_amount_in_words(1000000)
        self.assertIn("One Million Rupees", result)

    def test_format_cents_in_words_not_digits(self):
        result = format_cheque_amount_in_words(1234.56)
        self.assertIn("One Thousand, Two Hundred Thirty-Four Rupees", result)
        self.assertIn("And Fifty-Six Cents", result)
        self.assertNotRegex(result, r"\d")

    def test_format_rounding(self):
        result = format_cheque_amount_in_words(10.999)
        self.assertIn("Eleven Rupees", result)

    def test_negative_raises(self):
        with self.assertRaises(ValueError):
            format_cheque_amount_in_words(-1)

    def test_resolve_commercial_bank(self):
        self.assertEqual(resolve_bank_code("Commercial Bank of Ceylon"), "COMB")

    def test_resolve_hnb_partial(self):
        self.assertEqual(resolve_bank_code("Hatton National Bank"), "HNB")

    def test_resolve_sampath(self):
        self.assertEqual(resolve_bank_code("Sampath Bank"), "SAMPATH")

    def test_resolve_ndb(self):
        self.assertEqual(resolve_bank_code("NDB Bank"), "NDB")
        self.assertEqual(resolve_bank_code("National Development Bank PLC"), "NDB")

    def test_resolve_unknown(self):
        self.assertIsNone(resolve_bank_code("Unknown Bank PLC"))


if __name__ == "__main__":
    unittest.main()
