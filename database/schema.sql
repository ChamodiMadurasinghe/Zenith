PRAGMA foreign_keys = ON;

CREATE TABLE user (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name       TEXT    NOT NULL UNIQUE,
    email           TEXT    NOT NULL UNIQUE,
    password        TEXT    NOT NULL
);

CREATE TABLE user_bank_account (
    user_bank_acc_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    account_name        TEXT    NOT NULL,
    nickname            TEXT,
    available_balance   REAL    NOT NULL DEFAULT 0.00,
    branch_name         TEXT,
    bank_name           TEXT    NOT NULL,
    FOREIGN KEY (user_id) REFERENCES user(user_id)
);

CREATE TABLE dealers (
    dealer_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dealer_name         TEXT    NOT NULL,
    dealer_email        TEXT,
    dealer_telno        TEXT,
    dealer_address      TEXT,
    dealer_strictness   TEXT,
    casual_days         INTEGER DEFAULT 0,
    impossible_days     TEXT
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
    credit_period_days      INTEGER NOT NULL,
    total_amount            REAL    NOT NULL,
    location_path           TEXT,
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

CREATE TABLE cbsl_bank_holidays (
    holiday_date    TEXT PRIMARY KEY,
    description     TEXT
);

CREATE INDEX idx_user_bank_account_user_id ON user_bank_account(user_id);
CREATE INDEX idx_cheque_user_bank_acc_id ON cheque(user_bank_acc_id);
CREATE INDEX idx_invoices_user_id ON invoices(user_id);
CREATE INDEX idx_invoices_dealer_id ON invoices(dealer_id);
CREATE INDEX idx_invoices_cheque_id ON invoices(cheque_id);
CREATE INDEX idx_invoices_invoice_no ON invoices(invoice_no);
CREATE INDEX idx_item_invoices_id ON item(invoices_id);
CREATE INDEX idx_item_item_code ON item(item_code);
CREATE INDEX idx_dealers_bank_account_dealer_id ON dealers_bank_account(dealer_id);
CREATE INDEX idx_cheque_cheque_no ON cheque(cheque_no);
CREATE INDEX idx_dealers_dealer_name ON dealers(dealer_name);
