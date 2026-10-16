# Zenith UI redesign — simple version

Implementation plan for rebuilding the Zenith web UI from the Figma file
[Zenith UI revamp](https://www.figma.com/design/Y9MEK7oT5rXKlQXHvs8c6b/Zenith-UI-revamp),
page **Simple version**. The old UI is not restyled; the new one is built
next to it and replaces it page by page.

## 1. What the design contains

**Design system page**

- 35 colour variables (Light and Dark modes), 9 spacing variables.
- 13 text styles, all Poppins: Hero 38, Display 32, H1 28, H2 21, H3 17,
  Body Large 18, Body 16 (Regular/Medium), Caption 14 (Regular/Medium),
  Overline 14, Number 16 and Number Large 32 (SemiBold).
- 43 icons, Button (Primary, Secondary, AI, Danger, Ghost), Badge, Alert,
  Input (Default, Low confidence, Error, Verified), Cap meter, Stat card,
  Top bar, Sidebar.

**Simple version page (11 screens)**

| Screen | Purpose |
|---|---|
| Today | Numbered to-do list, one button per item |
| Invoices | Invoices waiting to be checked, "Add a photo" |
| Check invoice | Photo + 4 fields, "2 of 7", Save / Finish later / Remove |
| Cheques | Suppliers ready to be paid |
| Supplier (Tokyo Cement) | Unpaid invoices, recent cheques, contact |
| Cheques for Tokyo Cement | The ready-made cheque plan, "Print 3 cheques" |
| Cheques printed | Done page with next steps |
| Money | "Do you have enough money?" answer + next 7 days |
| Add a deposit | Amount + day, cutoff hint |
| Money — after deposit | Green "You have enough money" state |
| Settings | Business, printer, bank accounts, WhatsApp, cheque limit, language, password |
| Today — mobile | Same to-do list, bottom navigation, camera button |

**Design rules** (from the "Designed for low digital literacy" board)

Plain words · one dark primary button per screen · every icon has a word ·
status = icon + word + colour, never colour alone · 16px text, 48px buttons,
52px fields · amounts in full ("Rs. 4,400,500"), no "4.4M", no percentages ·
answer the question first · choices over typing · nothing saves silently ·
always a way out · සිංහල / தமிழ் / English always visible.

## 2. Approach

- A new blueprint `routes/simple.py` with thin routes. Page data comes from
  pure functions in `core/views/`, which reuse `db/repositories.py`,
  `core/cash_flow.py`, `core/bundling.py`, `core/guardrails.py` and the
  existing agents.
- Business logic that lives inside old routes moves into services so both
  UIs call the same code:
  - `core/invoice_service.py` from `routes/ingestion.py` (`verify_invoice`).
  - `core/cheque_service.py` from `routes/bundling.py` (`commit`).
- New templates in `templates/simple/`, new static files in `static/simple/`.
  Nothing in `templates/` or `static/css/main.css` is changed until the
  switch-over.
- `UI_MODE=simple|classic` (env, default `classic` until task 9) decides
  where `/`, login and the language switch land. Old pages keep their URLs
  during the migration.

## 3. Screen → existing code

| Screen | Route | Reuses | Missing (built in this plan) |
|---|---|---|---|
| Today | `GET /` | `build_cash_flow_projection().alerts`, `get_pending_verification_invoices`, `get_whatsapp_inbox_pending`, `get_verified_unassigned_invoices` | one "suppliers ready to pay" query, time estimate |
| Invoices | `GET /invoices` | pending + WhatsApp inbox queries, `POST /upload` | merged queue; upload currently goes to a session draft |
| Check invoice | `GET/POST /invoices/<id>/check` | `verify_invoice` logic, Agent 2 audit, `_block_duplicate_invoice`, dealer quick-add, `delete_invoice` | "2 of 7" + next, Pay-by ↔ credit days, per-field states |
| Cheques | `GET /cheques` | same "ready" query | — |
| Supplier | `GET /suppliers/<id>` | `get_dealer`, `get_dealer_invoices`, `get_committed_cheque_bundles` | contact person, WhatsApp, cheque status |
| Cheque plan | `GET /cheques/<dealer_id>` | `compute_bundles`, `collect_bundle_issues`, `simulate_extra_cheques` | plain-language problems and fixes |
| Print | `POST /cheques/<dealer_id>/print` | `repo.save_cheques`, ceiling check, `generate_cheques_pdf` | automatic cheque numbers, save + print in one step |
| Cheques printed | `GET /cheques/printed/<batch>` | cheque rows | number range, reprint |
| Money | `GET /money` | `CashFlowReport` (alerts, timeline, cheque timetable) | grouping by day, enough/not-enough answer |
| Add a deposit | `GET/POST /money/deposit` | `repo.add_planned_deposit` (already in the projection) | prefill shortfall, bank cutoff hint |
| Remind me | `POST /money/remind` | `core/alert_scheduler.py` | one-off reminder |
| Settings | `GET /settings` | accounts + `ceiling_lkr`, WhatsApp number and senders, `/api/cheque/print-test`, `/api/cheque/calibration`, `set_language`, onboarding password code | business details, printer name/status, last test page, password date |

### Necessary features without a screen in the design

These are needed to run the shop, so they are built into the simple screens
in the same visual language:

- **Bank balance** — "In the bank today" on Money gets a *Change* link and a
  small form (writes `available_balance`).
- **Printer alignment** — Settings → Cheque printer gets *Print a test page*
  and *Line it up* (move left/right/up/down buttons; saves calibration).
- **Plan problems** — when a plan breaks a rule (single invoice over the
  limit, not enough money, bank holiday) the cheque plan shows a red alert
  that answers the question first and offers plain fixes (change date, add a
  deposit, raise the limit).
- **Logout** — avatar menu in the top bar.
- **Several bank accounts** — the main account is used by default; Money and
  the cheque plan show an account picker only when there is more than one.
- **Typing an invoice in** — "No photo? Type it in" on Invoices, a simple
  form with the same four fields.
- **Backup** — Settings card using the existing `/api/backup/now` endpoint.

Kept on the old pages only (reachable by URL, not in the new navigation):
bundling chat and AI reviewer, drag-and-drop bundling, Reports, dealer hub
tabs, bank-statement mail, dark mode, font-size setting.

## 4. Helpers

**`core/ui/format.py`** (Jinja filters)

- `lkr(amount)` → "Rs. 2,140,000"; negative → "-Rs. 385,000"; none → "None".
- `long_date` → "Wednesday, 14 October"; `day_label` → "Thu 22 Oct";
  `relative_day` → "Today" / "Yesterday" / "Mon 12 Oct".
- `count_label(n, key)` → "1 cheque" / "5 cheques" (en/si/ta).
- `mask_account` → "Commercial Bank •••4521"; `initials` → "MS".

**`core/ui/status.py`**

- One table: status → icon, word, tone (enough, not_enough, looks_right,
  please_check, printed, paid_by_bank, ready, main, selected).
- `field_states(anomalies)` maps Agent 2 codes to the four check fields:
  `duplicate_invoice_no` → invoice number; `unknown_dealer` → supplier;
  `bad_date`, `future_date`, `stale_date` → pay by; `amount_outlier`,
  `math_mismatch`, `missing_amount`, `possible_missing_discount` → total;
  `item_*`, `qty_unusual` → note under total.

**`core/ui/nav.py`** — sidebar items (Today, Invoices, Cheques, Money,
Settings), active state, mobile dock.

**`core/views/`**

- `today.py` — to-do items in priority order (money shortfall, invoices to
  check, one item per supplier ready to pay), greeting, count.
- `invoices.py` — merged queue, `queue_position(id)`, due date ↔ credit days.
- `cheques.py` — ready suppliers, `make_plan(dealer_id)`, plan problems,
  `next_cheque_numbers`, `batch_summary`.
- `money.py` — `answer()`, `next_days(7)`, `deposit_suggestion()`.
- `settings.py` — the settings cards.

## 5. Data changes (`scripts/init_db.migrate_existing_db` + `database/schema.sql`)

- `cheque.status` (`saved`/`printed`/`given`/`cleared`), `cheque.printed_at`,
  `cheque.cleared_at`.
- `user_bank_account.next_cheque_no`.
- `dealers.contact_person`, `dealers.whatsapp`.
- `app_settings` keys: `business_name`, `business_address`, `printer_name`,
  `printer_last_test`, `password_changed_at`, `reminders`.
- Config: `SUPPORT_PHONE`, `BANK_CUTOFF_TIME` (default `15:00`), `UI_MODE`.

## 6. Tasks

Each task is one pull request.

1. **Foundation** — tokens from Figma variables, icon sprite, macros
   (`templates/simple/_ui.html`), base layout with sidebar, top bar
   (date, language, Help, avatar menu with Logout) and mobile dock,
   `UI_MODE` flag, language switch returns to the current page, a style
   preview page at `/ui/preview`.
2. **Helpers** — `core/ui/format.py`, `status.py`, `nav.py`, i18n strings
   (en/si/ta), unit tests.
3. **Data** — migrations and repository functions listed in section 5.
4. **Today** — desktop and mobile.
5. **Money** — answer, next 7 days, Add a deposit, bank balance, reminder,
   account picker.
6. **Invoices** — queue, Check invoice, upload straight into the queue,
   type-it-in form; `core/invoice_service.py`.
7. **Cheques** — ready list, supplier page, plan with problems and fixes,
   save + print, printed page, reprint; `core/cheque_service.py`.
8. **Settings** — all cards, printer test and alignment, accounts and cheque
   limit, first cheque number, password, backup.
9. **Switch-over** — `UI_MODE=simple` by default, route tests, browser
   screenshots against Figma, remove dead templates.

Tasks 4–8 depend on 1–3. Task 9 depends on all.

## 7. Testing

- Unit tests for `core/ui/*` and `core/views/*` (temporary SQLite, like
  `core/tests`).
- Render tests for every simple route in `routes/tests/test_simple_ui.py`.
- Existing suites run unchanged after each refactor
  (`python -m unittest discover -s <dir>/tests`).
- Playwright screenshots of each page compared with the Figma frames.

## 8. Open points

- Poppins has no Sinhala or Tamil glyphs; Noto Sans Sinhala and Noto Sans
  Tamil are added as fallbacks.
- "Why these cheques" stays rule-based (from guardrail results), not AI.
