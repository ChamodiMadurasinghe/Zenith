# Zenith Database Reference

SQLite file: `database/invoice_cheque.db`  
Rebuild: `python scripts/init_db.py` (reads `APP_PASSWORD` from `.env`)

## Tables

### `user`
Single merchant account used for login.

| Column | Type | Notes |
|--------|------|-------|
| user_id | INTEGER PK | Always `1` |
| user_name | TEXT | Merchant display name |
| email | TEXT | Contact email |
| password_hash | TEXT | Werkzeug hash (set by init_db.py) |

### `user_bank_account`
Your bank accounts.

| Column | Type | Notes |
|--------|------|-------|
| user_bank_acc_id | INTEGER PK | |
| user_id | INTEGER FK → user | |
| account_name | TEXT | Legal account name |
| nickname | TEXT | Short label for UI |
| available_balance | REAL | Current ledger balance (updated via Cash Flow UI) |
| overdraft_limit | REAL | Cheque overdraft facility (0 = none). Usable funds = balance + overdraft |
| branch_name | TEXT | |
| bank_name | TEXT | |

### `dealers`
Supplier registry.

| Column | Type | Notes |
|--------|------|-------|
| dealer_id | INTEGER PK | |
| dealer_name | TEXT | Matched during invoice ingestion |
| dealer_email | TEXT | |
| dealer_telno | TEXT | |
| dealer_address | TEXT | |
| dealer_strictness | TEXT | High / Medium / Low |
| casual_days | INTEGER | Extra days before cheque date |
| impossible_days | TEXT | Comma-separated weekdays (e.g. `Sunday`) |
| preferred_dealer_bank_acc_id | INTEGER FK | Preferred supplier bank for interbank clearing (+1 day) |

### `dealers_bank_account`
Supplier bank details (reference only).

### `deposit_timetable`
Max-liquidity funding schedule for pending cheque outflows.

| Column | Type | Notes |
|--------|------|-------|
| timetable_id | INTEGER PK | |
| user_bank_acc_id | INTEGER FK | Merchant account debited |
| cheque_id | INTEGER FK | NULL until committed |
| dealer_id | INTEGER FK | For interbank detection |
| stated_date | TEXT | Cheque stated date |
| true_settlement_date | TEXT | Forward-rolled CBSL business day |
| target_funding_date | TEXT | Latest legal fund-by date |
| total_amount | REAL | LKR outflow |
| days_gained | INTEGER | Holiday/weekend lag days |
| status | TEXT | `pending` \| `cleared` |

### `cheque`
Issued cheques.

| Column | Type | Notes |
|--------|------|-------|
| cheque_id | INTEGER PK | |
| user_bank_acc_id | INTEGER FK | Account debited |
| cheque_no | TEXT | |
| cheque_date | TEXT | YYYY-MM-DD |
| amount_in_words | TEXT | |
| amount_in_numerals | REAL | |
| verification_status | INTEGER | 0=draft, 1=committed |
| predicted_clearance_date | TEXT | Used by cash-flow projection |
| cheque_print_date | TEXT | Timestamp |

### `invoices`
Invoice headers.

| Column | Type | Notes |
|--------|------|-------|
| invoices_id | INTEGER PK | |
| user_id | INTEGER FK | Always `1` |
| dealer_id | INTEGER FK | |
| cheque_id | INTEGER FK | NULL until bundled |
| invoice_no | TEXT | |
| invoiced_date | TEXT | YYYY-MM-DD |
| credit_period_days | INTEGER | Due = invoiced_date + days |
| total_amount | REAL | LKR |
| location_path | TEXT | Path to scanned image |
| is_invoice_verified | INTEGER | 0=pending, 1=verified |

### `item`
Invoice line items (workflow "invoice_items").

| Column | Type | Notes |
|--------|------|-------|
| item_id | INTEGER PK | |
| invoices_id | INTEGER FK | |
| item_code | TEXT | |
| item_name | TEXT | |
| item_qty | INTEGER | |
| item_price | REAL | |
| item_discount | REAL | |

### `cbsl_bank_holidays`
Sri Lanka bank holidays for guardrails and date calculations. Includes every **Saturday and Sunday** plus named CBSL public/bank holidays.

| Column | Type | Notes |
|--------|------|-------|
| holiday_date | TEXT PK | YYYY-MM-DD |
| description | TEXT | CBSL holiday name, or `Saturday` / `Sunday` |

**Populate / refresh** from the official CBSL pages (defaults 2025–2027):

```bash
pip install -r requirements.txt
python scripts/sync_cbsl_holidays.py
python scripts/sync_cbsl_holidays.py --dry-run
python scripts/sync_cbsl_holidays.py --years 2025,2026,2027
```

`scripts/init_db.py` runs the sync automatically after a fresh database create (best-effort if CBSL is unreachable).

Source: [CBSL bank holidays](https://www.cbsl.gov.lk/en/about/about-the-bank/bank-holidays)

### `bank_deposits`
Actual money deposited into your accounts.

| Column | Type | Notes |
|--------|------|-------|
| deposit_id | INTEGER PK | |
| user_bank_acc_id | INTEGER FK | |
| deposit_date | TEXT | YYYY-MM-DD |
| amount | REAL | LKR |
| reference | TEXT | Optional note |

### `planned_deposits`
Future deposits you plan to make (Cash Flow UI).

| Column | Type | Notes |
|--------|------|-------|
| planned_deposit_id | INTEGER PK | |
| user_bank_acc_id | INTEGER FK | |
| planned_date | TEXT | Target deposit-by date |
| amount | REAL | LKR |
| notes | TEXT | |
| status | TEXT | `planned` or `done` |

### `app_settings`
Key-value app configuration.

| Key | Default | Purpose |
|-----|---------|---------|
| min_cash_buffer_lkr | 500000 | Minimum safe balance |
| default_bank_acc_id | 1 | Default account for Cash Flow |

### `analyst_reports`
Cached Agent 3 markdown reports.

| Column | Type | Notes |
|--------|------|-------|
| report_id | INTEGER PK | |
| generated_at | TEXT | Timestamp |
| report_markdown | TEXT | Full markdown report |
