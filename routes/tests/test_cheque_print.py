import unittest
from unittest.mock import patch

from routes.cheque_print import _generate_pdf_for_account


class TestChequePrintApi(unittest.TestCase):
    @patch("routes.cheque_print.generate_cheque_pdf")
    @patch("routes.cheque_print.repo.get_bank_cheque_template")
    @patch("routes.cheque_print.repo.get_printer_settings")
    @patch("routes.cheque_print.resolve_bank_code")
    @patch("routes.cheque_print.repo.get_bank_account")
    def test_generate_pdf_with_preview_offsets(
        self,
        mock_account,
        mock_resolve,
        mock_settings,
        mock_template,
        mock_pdf,
    ):
        mock_account.return_value = {"bank_name": "Commercial Bank of Ceylon"}
        mock_resolve.return_value = "COMB"
        mock_settings.return_value = {
            "offset_x_mm": 0.0,
            "offset_y_mm": 0.0,
            "feed_orientation": "VERTICAL",
        }
        mock_template.return_value = {
            "cheque_width_mm": 177.8,
            "cheque_height_mm": 88.9,
            "date_x": 135,
            "date_y": 75,
            "payee_x": 25,
            "payee_y": 56,
            "amount_words_x": 25,
            "amount_words_y": 43,
            "amount_figures_x": 135,
            "amount_figures_y": 43,
        }
        mock_pdf.return_value = b"%PDF-test"

        result = _generate_pdf_for_account(
            1,
            payee_name="TEST PAYEE",
            amount=1234.56,
            date_str="2026-08-30",
            offset_x_mm=2.0,
            offset_y_mm=-1.0,
            feed_orientation="HORIZONTAL",
        )

        self.assertEqual(result[0], b"%PDF-test")
        self.assertEqual(result[1], "COMB")
        printer_settings = mock_pdf.call_args.kwargs["printer_settings"]
        self.assertEqual(printer_settings["offset_x_mm"], 2.0)
        self.assertEqual(printer_settings["offset_y_mm"], -1.0)
        self.assertEqual(printer_settings["feed_orientation"], "HORIZONTAL")


if __name__ == "__main__":
    unittest.main()
