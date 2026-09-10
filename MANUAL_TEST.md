# Manual test checklist — cheque edit (Person One)

Prerequisites: logged-in Zenith session, at least one committed cheque on a dealer Cheques tab.

1. **Open detail**
   - Go to Dealers → pick a dealer → Cheques.
   - Click a written-cheque row (`data-cheque-id`).
   - Modal loads number, date, amount, clearance, payee, invoices.
   - Amount is visible but not editable.

2. **Edit → Cancel**
   - Click **Edit**.
   - Cheque number becomes a text input; date becomes a date input.
   - Change either field, then **Cancel** (or press Escape).
   - View mode restores prior values; table row unchanged.

3. **Validation**
   - Edit again; clear cheque number → **Save** → blocked (required).
   - Enter a non-`YYYY-MM-DD` date if possible → blocked.
   - Confirm dialog must appear before a successful save; dismiss confirm → no API write.

4. **Save number only**
   - Change cheque number only → confirm → Save.
   - Modal shows new number; table first column updates.
   - Clearance / days gained unchanged.

5. **Save date (clearance recompute)**
   - Change cheque date to another business week → confirm → Save.
   - Modal clearance (`expected_clearance_date`) updates.
   - Table clearance (and days gained if shown) update.
   - Cash-flow / deposit timetable for that cheque reflects the new stated date (pending row).

6. **Auth / ownership**
   - While logged out (or other session), `POST /dealers/cheques/<id>/edit` must not succeed (401/redirect).
   - Unknown `cheque_id` → `{ok:false,error:"not_found"}` (404).
   - Wrong `dealer_id` in JSON body → not_found.

7. **Out of scope (smoke)**
   - No amount field, delete control, or bundling changes in this modal.
