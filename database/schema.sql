PRAGMA foreign_keys = ON;

CREATE TABLE user (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name       TEXT    NOT NULL UNIQUE,
    email           TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL
);

CREATE TABLE user_bank_account (
    user_bank_acc_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    account_name        TEXT    NOT NULL,
    nickname            TEXT,
    available_balance   REAL    NOT NULL DEFAULT 0.00,
    overdraft_limit     REAL    NOT NULL DEFAULT 0.00,
    branch_name         TEXT,
    bank_name           TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(user_id)
);

CREATE TABLE dealers (
    dealer_id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_name                     TEXT    NOT NULL,
    dealer_email                    TEXT,
    dealer_telno                    TEXT,
    dealer_address                  TEXT,
    dealer_strictness               TEXT,
    casual_days                     INTEGER DEFAULT 0,
    impossible_days                 TEXT,
    preferred_dealer_bank_acc_id    INTEGER,
    default_user_bank_acc_id        INTEGER REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE TABLE dealers_bank_account (
    dealer_bank_acc_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_id           INTEGER NOT NULL,
    account_name        TEXT    NOT NULL,
    branch_name         TEXT,
    bank_name           TEXT    NOT NULL,
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
);

CREATE TABLE cheque (
    cheque_id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id            INTEGER NOT NULL,
    cheque_no                   TEXT    NOT NULL,
    cheque_date                 TEXT    NOT NULL,
    amount_in_words             TEXT,
    amount_in_numerals          REAL    NOT NULL,
    verification_status         INTEGER NOT NULL DEFAULT 0,
    predicted_clearance_date    TEXT,
    cheque_print_date           TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE TABLE invoices (
    invoices_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL,
    dealer_id               INTEGER NOT NULL,
    cheque_id               INTEGER,
    invoice_no              TEXT    NOT NULL,
    invoiced_date           TEXT    NOT NULL,
    delivery_date           TEXT,
    credit_period_days      INTEGER NOT NULL,
    total_amount            REAL    NOT NULL,
    location_path           TEXT,
    pending_dealer_json     TEXT,
    is_invoice_verified     INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id)   REFERENCES user(user_id),
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id),
    FOREIGN KEY (cheque_id) REFERENCES cheque(cheque_id)
);

CREATE TABLE item (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    invoices_id     INTEGER NOT NULL,
    item_code       TEXT    NOT NULL,
    item_name       TEXT    NOT NULL,
    item_qty        INTEGER NOT NULL,
    item_price      REAL    NOT NULL,
    item_discount   REAL    NOT NULL DEFAULT 0,
    FOREIGN KEY (invoices_id) REFERENCES invoices(invoices_id)
);

-- One invoice may fund multiple cheques via amount parts
CREATE TABLE cheque_invoice_allocation (
    allocation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    cheque_id       INTEGER NOT NULL,
    invoices_id     INTEGER NOT NULL,
    amount          REAL    NOT NULL,
    part_index      INTEGER NOT NULL DEFAULT 1,
    part_count      INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (cheque_id) REFERENCES cheque(cheque_id),
    FOREIGN KEY (invoices_id) REFERENCES invoices(invoices_id)
);

CREATE TABLE cbsl_bank_holidays (
    holiday_date    TEXT PRIMARY KEY,
    description     TEXT
);

CREATE TABLE bank_deposits (
    deposit_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id    INTEGER NOT NULL,
    deposit_date        TEXT    NOT NULL,
    amount              REAL    NOT NULL,
    reference           TEXT,
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE TABLE planned_deposits (
    planned_deposit_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id    INTEGER NOT NULL,
    planned_date        TEXT    NOT NULL,
    amount              REAL    NOT NULL,
    notes               TEXT,
    status              TEXT    NOT NULL DEFAULT 'planned',
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id)
);

CREATE TABLE app_settings (
    setting_key         TEXT PRIMARY KEY,
    setting_value       TEXT NOT NULL
);

CREATE TABLE analyst_reports (
    report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at    TEXT    DEFAULT (datetime('now')),
    report_markdown TEXT    NOT NULL
);

CREATE TABLE bundle_drafts (
    dealer_id               INTEGER PRIMARY KEY,
    ceiling_lkr             REAL NOT NULL,
    bundles_json            TEXT NOT NULL,
    validation_issues_json  TEXT,
    allow_exceed_ceiling    INTEGER NOT NULL DEFAULT 0,
    chat_history_json       TEXT,
    updated_at              TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
);

CREATE TABLE deposit_timetable (
    timetable_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_bank_acc_id        INTEGER NOT NULL,
    cheque_id               INTEGER,
    dealer_id               INTEGER,
    stated_date             TEXT NOT NULL,
    true_settlement_date    TEXT,
    target_funding_date     TEXT,
    total_amount            REAL NOT NULL,
    days_gained             INTEGER DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (user_bank_acc_id) REFERENCES user_bank_account(user_bank_acc_id),
    FOREIGN KEY (cheque_id) REFERENCES cheque(cheque_id),
    FOREIGN KEY (dealer_id) REFERENCES dealers(dealer_id)
);

CREATE TABLE whatsapp_sessions (
    phone           TEXT PRIMARY KEY,
    state           TEXT NOT NULL,
    context_json    TEXT,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE whatsapp_inbox (
    inbox_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    sender_phone    TEXT,
    location_path   TEXT NOT NULL,
    received_at     TEXT DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'pending',
    invoice_id      INTEGER,
    FOREIGN KEY (user_id) REFERENCES user(user_id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(invoices_id)
);

CREATE TABLE alert_log (
    alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    channel         TEXT NOT NULL,
    recipient       TEXT NOT NULL,
    message         TEXT NOT NULL,
    sent_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_user_bank_account_user_id ON user_bank_account(user_id);
CREATE INDEX idx_cheque_user_bank_acc_id ON cheque(user_bank_acc_id);
CREATE INDEX idx_cheque_predicted_clearance ON cheque(predicted_clearance_date);
CREATE INDEX idx_invoices_user_id ON invoices(user_id);
CREATE INDEX idx_invoices_dealer_id ON invoices(dealer_id);
CREATE INDEX idx_invoices_cheque_id ON invoices(cheque_id);
CREATE INDEX idx_invoices_invoice_no ON invoices(invoice_no);
CREATE INDEX idx_item_invoices_id ON item(invoices_id);
CREATE INDEX idx_item_item_code ON item(item_code);
CREATE INDEX idx_dealers_bank_account_dealer_id ON dealers_bank_account(dealer_id);
CREATE INDEX idx_cheque_cheque_no ON cheque(cheque_no);
CREATE INDEX idx_dealers_dealer_name ON dealers(dealer_name);
CREATE INDEX idx_bank_deposits_date ON bank_deposits(deposit_date);
CREATE INDEX idx_planned_deposits_date ON planned_deposits(planned_date);
CREATE INDEX idx_deposit_timetable_account ON deposit_timetable(user_bank_acc_id);
CREATE INDEX idx_deposit_timetable_status ON deposit_timetable(status);
CREATE INDEX idx_deposit_timetable_stated ON deposit_timetable(stated_date);
CREATE INDEX idx_whatsapp_sessions_updated ON whatsapp_sessions(updated_at);
CREATE INDEX idx_whatsapp_inbox_status ON whatsapp_inbox(status);
CREATE INDEX idx_whatsapp_inbox_user ON whatsapp_inbox(user_id);
CREATE INDEX idx_alert_log_sent_at ON alert_log(sent_at);

-- One invoice number per dealer (per user). Different dealers may reuse the same number.
CREATE UNIQUE INDEX idx_invoices_user_dealer_invoice_no
    ON invoices(user_id, dealer_id, invoice_no);
