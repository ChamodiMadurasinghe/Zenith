-- Uncalibrated default coordinates for CITS-standard Sri Lankan cheques (177.8 x 88.9 mm).
-- Validate with physical test prints and adjust via shop_printer_settings offsets.
INSERT INTO bank_cheque_templates
    (bank_code, bank_name, date_x, date_y, payee_x, payee_y,
     amount_words_x, amount_words_y, amount_figures_x, amount_figures_y)
VALUES
    ('COMB', 'Commercial Bank of Ceylon', 135.0, 75.0, 25.0, 56.0, 25.0, 43.0, 135.0, 43.0),
    ('HNB', 'Hatton National Bank', 138.0, 74.0, 28.0, 54.0, 28.0, 41.0, 138.0, 41.0),
    ('SAMPATH', 'Sampath Bank', 134.0, 76.0, 24.0, 57.0, 24.0, 44.0, 134.0, 44.0),
    ('BOC', 'Bank of Ceylon', 132.0, 73.0, 26.0, 53.0, 26.0, 40.0, 132.0, 40.0),
    ('SEYLAN', 'Seylan Bank', 136.0, 75.0, 27.0, 55.0, 27.0, 42.0, 136.0, 42.0)
ON CONFLICT(bank_code) DO UPDATE SET
    bank_name = excluded.bank_name,
    date_x = excluded.date_x,
    date_y = excluded.date_y,
    payee_x = excluded.payee_x,
    payee_y = excluded.payee_y,
    amount_words_x = excluded.amount_words_x,
    amount_words_y = excluded.amount_words_y,
    amount_figures_x = excluded.amount_figures_x,
    amount_figures_y = excluded.amount_figures_y;
