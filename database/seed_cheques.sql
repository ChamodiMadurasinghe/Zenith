-- Uncalibrated default coordinates for CITS-standard Sri Lankan cheques (177.8 x 88.9 mm).
-- date_letter_spacing = fixed pitch (mm) between digit origins for DDMMYYYY boxes.
-- Validate with physical test prints and adjust via shop_printer_settings offsets.
INSERT INTO bank_cheque_templates
    (bank_code, bank_name, date_x, date_y, date_letter_spacing, payee_x, payee_y,
     amount_words_x, amount_words_y, amount_figures_x, amount_figures_y)
VALUES
    ('COMB', 'Commercial Bank of Ceylon', 128.0, 75.0, 6.0, 25.0, 56.0, 25.0, 43.0, 135.0, 43.0),
    ('HNB', 'Hatton National Bank', 130.0, 74.0, 6.0, 28.0, 54.0, 28.0, 41.0, 138.0, 41.0),
    ('SAMPATH', 'Sampath Bank', 127.0, 76.0, 6.0, 24.0, 57.0, 24.0, 44.0, 134.0, 44.0),
    ('BOC', 'Bank of Ceylon', 126.0, 73.0, 6.0, 26.0, 53.0, 26.0, 40.0, 132.0, 40.0),
    ('SEYLAN', 'Seylan Bank', 128.0, 75.0, 6.0, 27.0, 55.0, 27.0, 42.0, 136.0, 42.0),
    -- NDB: date/figures unchanged; payee + words +8 mm up; A/C PAYEE centered in printer
    ('NDB', 'National Development Bank', 154.0, 85.0, 3.2, 26.0, 68.0, 26.0, 55.0, 136.0, 48.0)
ON CONFLICT(bank_code) DO UPDATE SET
    bank_name = excluded.bank_name,
    date_x = excluded.date_x,
    date_y = excluded.date_y,
    date_letter_spacing = excluded.date_letter_spacing,
    payee_x = excluded.payee_x,
    payee_y = excluded.payee_y,
    amount_words_x = excluded.amount_words_x,
    amount_words_y = excluded.amount_words_y,
    amount_figures_x = excluded.amount_figures_x,
    amount_figures_y = excluded.amount_figures_y;

-- NDB: wrap words before figures box; crossing height (X ignored — drawn centered)
UPDATE bank_cheque_templates
SET amount_words_max_width = 100.0,
    crossing_y = 78.0,
    crossing_x = 88.9
WHERE bank_code = 'NDB';
