import unittest

from core.cheque_printer import generate_cheque_pdf, generate_cheques_pdf, normalize_cheque_date


SAMPLE_TEMPLATE = {
    "cheque_width_mm": 177.8,
    "cheque_height_mm": 88.9,
    "date_x": 128.0,
    "date_y": 75.0,
    "date_letter_spacing": 6.0,
    "payee_x": 25.0,
    "payee_y": 56.0,
    "amount_words_x": 25.0,
    "amount_words_y": 43.0,
    "amount_words_max_width": 110.0,
    "amount_figures_x": 135.0,
    "amount_figures_y": 43.0,
    "crossing_x": 15.0,
    "crossing_y": 75.0,
}


class TestChequePrinter(unittest.TestCase):
    def test_normalize_iso_date(self):
        self.assertEqual(normalize_cheque_date("2026-08-30"), "30082026")

    def test_normalize_eight_digits(self):
        self.assertEqual(normalize_cheque_date("30082026"), "30082026")

    def test_normalize_keeps_full_year(self):
        self.assertEqual(normalize_cheque_date("2026-09-02"), "02092026")
        self.assertEqual(len(normalize_cheque_date("2026-09-02")), 8)

    def test_generate_pdf_vertical(self):
        pdf = generate_cheque_pdf(
            date_str="2026-08-30",
            payee_name="Test Dealer",
            amount=150000.50,
            bank_template=SAMPLE_TEMPLATE,
            printer_settings={"offset_x_mm": 0, "offset_y_mm": 0, "feed_orientation": "VERTICAL"},
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 100)

    def test_generate_pdf_ndb_skips_century(self):
        template = dict(SAMPLE_TEMPLATE)
        template["bank_code"] = "NDB"
        template["date_x"] = 154.0
        template["date_y"] = 85.0
        template["date_letter_spacing"] = 3.2
        pdf = generate_cheque_pdf(
            date_str="2026-09-02",
            payee_name="TEST PAYEE",
            amount=1234.56,
            bank_template=template,
            printer_settings={"offset_x_mm": 0, "offset_y_mm": 0, "feed_orientation": "VERTICAL"},
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 100)

    def test_generate_pdf_horizontal(self):
        pdf = generate_cheque_pdf(
            date_str="2026-08-30",
            payee_name="Test Dealer",
            amount=1000,
            bank_template=SAMPLE_TEMPLATE,
            printer_settings={"offset_x_mm": 1.5, "offset_y_mm": -0.5, "feed_orientation": "HORIZONTAL"},
            crossing=False,
        )
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_generate_cheques_pdf_multi_page(self):
        pdf = generate_cheques_pdf(
            [
                {"date_str": "2026-08-30", "payee_name": "A", "amount": 1000},
                {"date_str": "2026-09-01", "payee_name": "B", "amount": 2000},
            ],
            SAMPLE_TEMPLATE,
            {"offset_x_mm": 0, "offset_y_mm": 0, "feed_orientation": "VERTICAL"},
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 200)


if __name__ == "__main__":
    unittest.main()
