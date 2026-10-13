-- First launch for a real shop. No demo dealers, invoices, or cheques.
-- Password hash is set by scripts/init_db.py from APP_PASSWORD.
INSERT INTO user (user_name, email, password_hash) VALUES
    ('shop_owner', 'owner@local', 'pending');

INSERT INTO dealers (dealer_name, dealer_email, dealer_telno, dealer_address, dealer_strictness, casual_days, impossible_days) VALUES
    ('Pending Supplier', NULL, NULL, NULL, 'Medium', 3, 'Sunday');

INSERT INTO app_settings (setting_key, setting_value) VALUES
    ('min_cash_buffer_lkr', '500000'),
    ('onboarding_status', 'pending');
