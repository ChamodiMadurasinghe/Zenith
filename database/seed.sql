-- Users
INSERT INTO user (user_name, email, password) VALUES
    ('yohan_merchant', 'yohan@hardware.lk', 'hashed_pw_yohan_2024'),
    ('admin_store',    'admin@store.lk',    'hashed_pw_admin_2024');

-- User bank accounts
INSERT INTO user_bank_account (user_id, account_name, nickname, available_balance, branch_name, bank_name) VALUES
    (1, 'Yohan Hardware Pvt Ltd', 'Main Hardware Checking', 2500000.00, 'Pettah Branch',       'Commercial Bank of Ceylon'),
    (1, 'Yohan Hardware Pvt Ltd', 'Reserve Account',        850000.00,  'Colombo Fort Branch', 'Hatton National Bank'),
    (2, 'Admin Store Lanka',      'Primary Checking',       1200000.00, 'Kandy Branch',          'Sampath Bank');

-- Dealers (from dealers.txt)
INSERT INTO dealers (dealer_name, dealer_email, dealer_telno, dealer_address, dealer_strictness, casual_days, impossible_days) VALUES
    ('ABD Traders',   'abd@traders.lk',    '0771234567', 'Colombo',  'High',   3, 'Sunday'),
    ('X Suppliers',  'x@suppliers.lk',    '0719876543', 'Galle',    'Medium', 5, 'Saturday,Sunday'),
    ('Tech World',   'sales@techworld.lk','0755555555', 'Kandy',    'Low',    7, 'Sunday'),
    ('Future Tech',  'info@futuretech.lk','0112223344', 'Colombo',  'High',   2, 'Sunday'),
    ('Smart Systems','contact@smart.lk',  '0914445566', 'Matara',   'Medium', 4, 'Sunday'),
    ('Island PC',    'orders@islandpc.lk','0317778899', 'Negombo',  'Low',    6, 'Saturday');

-- Dealer bank accounts
INSERT INTO dealers_bank_account (dealer_id, account_name, branch_name, bank_name) VALUES
    (1, 'ABD Traders',          'Colombo City',    'Bank of Ceylon'),
    (2, 'X Suppliers',          'Galle Fort',      'People''s Bank'),
    (3, 'Tech World',           'Kandy City',      'Sampath Bank'),
    (4, 'Future Tech',          'Sampath Corporate','Sampath Bank'),
    (5, 'Smart Systems',        'Matara',          'Hatton National Bank'),
    (6, 'Island PC',            'Negombo',         'Commercial Bank of Ceylon');

-- CBSL bank holidays
INSERT INTO cbsl_bank_holidays (holiday_date, description) VALUES
    ('2025-01-01', 'New Year Day'),
    ('2025-01-14', 'Tamil Thai Pongal Day'),
    ('2025-02-04', 'Independence Day'),
    ('2025-04-13', 'Sinhala and Tamil New Year Eve'),
    ('2025-04-14', 'Sinhala and Tamil New Year'),
    ('2025-05-12', 'Vesak Full Moon Poya Day'),
    ('2025-12-25', 'Christmas Day'),
    ('2026-01-01', 'New Year Day');

-- Cheques
INSERT INTO cheque (user_bank_acc_id, cheque_no, cheque_date, amount_in_words, amount_in_numerals, verification_status, predicted_clearance_date, cheque_print_date) VALUES
    (1, '000145', '2025-03-15', 'Sixty Nine Thousand Rupees Only',              69000.00,   1, '2025-03-20', '2025-03-14 10:30:00'),
    (1, '000146', '2025-04-01', 'Three Hundred Twenty Nine Thousand Rupees Only', 329000.00,  1, '2025-04-07', '2025-03-31 14:15:00'),
    (2, '000089', '2025-05-10', 'Three Hundred Sixty Nine Thousand Five Hundred Rupees Only', 369500.00, 0, '2025-05-16', '2025-05-09 09:00:00');

-- Invoices
-- Invoice 1: ABD Traders — total 69000 (5*2000 + 3*3000 + 2*25000)
INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, invoiced_date, credit_period_days, total_amount, location_path, is_invoice_verified) VALUES
    (1, 1, 1, 'INV-ABD-2025-001', '2025-02-01', 30, 69000.00,   'storage/invoices/inv_abd_001.jpg', 1);

-- Invoice 2: Tech World — total 329000 (2*150000 + 5*3000 + 2*7000)
INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, invoiced_date, credit_period_days, total_amount, location_path, is_invoice_verified) VALUES
    (1, 3, 2, 'INV-TW-2025-002',  '2025-03-01', 45, 329000.00,  'storage/invoices/inv_tw_002.jpg',  1);

-- Invoice 3: Future Tech — total 1471000 (5*185000 + 10*45000 + 8*12000), no cheque yet
INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, invoiced_date, credit_period_days, total_amount, location_path, is_invoice_verified) VALUES
    (1, 4, NULL, 'INV-FT-2025-003', '2025-04-01', 60, 1471000.00, 'storage/invoices/inv_ft_003.jpg', 0);

-- Invoice 4: Island PC — total 369500 (2*125000 + 4*18000 + 5*9500)
INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, invoiced_date, credit_period_days, total_amount, location_path, is_invoice_verified) VALUES
    (2, 6, 3, 'INV-IPC-2025-004', '2025-04-15', 30, 369500.00, 'storage/invoices/inv_ipc_004.jpg', 1);

-- Invoice 5: X Suppliers — total 177000 (2*50000 + 4*8000 + 3*15000)
INSERT INTO invoices (user_id, dealer_id, cheque_id, invoice_no, invoiced_date, credit_period_days, total_amount, location_path, is_invoice_verified) VALUES
    (2, 2, NULL, 'INV-XS-2025-005', '2025-05-01', 30, 177000.00, 'storage/invoices/inv_xs_005.jpg', 0);

-- Invoice line items
-- Invoice 1: ABD Traders items (from dealers.txt)
INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount) VALUES
    (1, 'MOUSE-DELL-001',    'Mouse',    5, 2000.00,   0),
    (1, 'KBD-HP-002',        'Keyboard', 3, 3000.00,   0),
    (1, 'MON-SAM-003',       'Monitor',  2, 25000.00,  0);

-- Invoice 2: Tech World items (from dealers.txt)
INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount) VALUES
    (2, 'LAP-DELL-001',      'Laptop',   2, 150000.00, 0),
    (2, 'MOUSE-LOGI-002',    'Mouse',    5, 3000.00,   0),
    (2, 'KBD-RED-003',       'Keyboard', 2, 7000.00,   0);

-- Invoice 3: Future Tech items (from dealers.txt)
INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount) VALUES
    (3, 'TAB-APL-001',       'Tablet',   5, 185000.00, 0),
    (3, 'STY-APL-002',       'Stylus',   10, 45000.00, 0),
    (3, 'CASE-LOGI-003',     'Case',     8, 12000.00,  0);

-- Invoice 4: Island PC items (from dealers.txt)
INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount) VALUES
    (4, 'GPU-NV-001',        'GPU',      2, 125000.00, 0),
    (4, 'PSU-COR-002',       'PSU',      4, 18000.00,  0),
    (4, 'COOL-CM-003',       'Cooler',   5, 9500.00,   0);

-- Invoice 5: X Suppliers items (from dealers.txt)
INSERT INTO item (invoices_id, item_code, item_name, item_qty, item_price, item_discount) VALUES
    (5, 'CPU-INT-001',       'CPU',  2, 50000.00, 0),
    (5, 'RAM-KIN-002',       'RAM',  4, 8000.00,  0),
    (5, 'SSD-SAM-003',       'SSD',  3, 15000.00, 0);
