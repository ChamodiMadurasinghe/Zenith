# Zenith — Idealize Demo Video Guide

**Presenter cue sheet + submission checklist**  
**Max length:** 5 minutes  
**Language:** English  

| Item | Value |
|------|--------|
| Suggested video file name | `Zenith_Video_Pitch` |
| Recording | Zoom screen share + camera picture-in-picture (presenter visible and audible) |
| Attire | Casual allowed |
| Category note | Open Category — show AI agent **inputs, steps, and outputs** |

> **Word document:** `docs/Zenith_Video_Pitch_Presenter_Guide.docx` (regenerate with `python scripts/generate_demo_pitch_docx.py`).

---

## 1. Submission requirements (checklist)

- [ ] Screen recording demonstrating and explaining the application (≤ 5 minutes)
- [ ] Navigate through each major page/feature with voiceover
- [ ] Open Category: show the AI Agent in action — **inputs, steps, outputs**
- [ ] Presenter clearly audible and visible (e.g. Zoom PiP)
- [ ] Language of use: **English**
- [ ] Video named: `[Team Name]_Video_Pitch` (use `Zenith_Video_Pitch` unless Idealize team name differs)
- [ ] GitHub README covers: project purpose, tech stack (match proposal), setup instructions, core features including **AI agent workflow**

---

## 2. Truth checks (do not oversell)

- Login is **password-only** (`APP_PASSWORD`). Say “login password,” not username + password.
- **RAG / vector database is still in build** — say “next milestone,” not “already live.”
- Cheque **Print** exists on preview (browser print). Full bank stationery cheque print, dedicated clearing tracker page, and owner WhatsApp clearing alerts are **roadmap**.
- This recording assumes live **Gemini**, **OpenAI** Bundling Assistant / Analyst, **WhatsApp Cloud API** via **Cloudflare tunnel**, and agents running.

---

## 3. Pre-demo checklist (before Record)

1. `python app.py` running; Cloudflare tunnel pointing to WhatsApp webhook.
2. Two sample invoice photos ready in WhatsApp inbox: **Invoice A** = known dealer; **Invoice B** = new/unregistered supplier.
3. At least one merchant bank account ready on Bank Balance.
4. One dealer with `casual_days` / `impossible_days` set (to explain float).
5. OpenAI credits + Gemini key working; avoid `USE_FAKE_AI` unless emergency.
6. Browser in English; light mode first; camera PiP visible.

---

## 4. Timed schedule (~4:50)

| Time | Screen | Goal |
|------|--------|------|
| 0:00–0:20 | Title / login | Problem + login |
| 0:20–0:45 | Bank Balance | Add/select bank; ready for invoices |
| 0:45–1:50 | Invoices → WhatsApp → AI → verify (2 invoices) | Vision agent + dealer difference |
| 1:50–3:25 | Cheques tab | Options, batching, holiday float, AI suggestions |
| 3:25–3:55 | Bank Balance + Reports | Cheques about to clear + analyst report |
| 3:55–4:25 | Dark mode, languages, Guide chat | Local SME UX |
| 4:25–4:50 | Roadmap close | RAG, print, clearing page, WhatsApp alerts |

---

## 5. Cheques tab — every option to name or show

On the dealer **Cheques** page, briefly point at as many of these as time allows (name them even if you do not click every control):

1. **LKR ceiling** (max per cheque)
2. **Select invoices** / Select all
3. **Compute bundles**
4. **One cheque per invoice**
5. **Proposed cheque cards** (stated date, settlement, fund-by / keep money until, **Extra days gained**, interbank badge)
6. **Drag invoices** between cheques
7. **Move to…** dropdown (other cheque / new cheque)
8. **Add cheque**
9. **Right-click Split** → separate cheques / same cheque / undo split (red `INV · 1`, `INV · 2`)
10. **Edit stated cheque date** on a card
11. **Auto-optimize bundles** (reviewer loop)
12. **Bundling Assistant chat** (mic / send / stop / mute / speak / reset / hide)
13. **Apply reviewer suggestions**
14. **Preview & write cheques** → bank account select → cheque numbers → **Print** → **Commit to database**
15. Committed cheques table + pending verification links (if visible)

---

## 6. AI agents — say inputs → steps → outputs

Open Category requirement: clearly show the AI agent working. Call out at least Vision and Bundling Assistant.

| Agent | Input | Steps | Output |
|-------|--------|--------|--------|
| **Vision (Gemini)** | Invoice photo (WhatsApp / upload) | Extract + structure fields; human verifies | Invoice #, dates, amount, supplier, line items on verify screen |
| **Bundling Assistant (OpenAI + tools)** | Current bundles + dealer context + chat | Tool calls into Python bundling / guardrails (no invented dates) | Reply + updated cheque groups; Apply suggestions |
| **Analyst (OpenAI)** | Committed cheques / metrics after commit | Generate narrative report | Reports page analysis |

**Flow:** WhatsApp photo → Vision agent → human verify/save → Bundling Assistant + Python bundling/guardrails → Preview/Commit → Analyst report.

---

## 7. Spoken script (say this while clicking)

Read the *italic / quoted* lines aloud. Follow the **On screen** cues. Keep total under **5:00**.

### 0:00–0:20 — Intro + login

> Hello, we are team Zenith. Our app helps Sri Lankan SMEs turn supplier invoices into smarter post-dated cheques—using Sri Lanka’s weekend and CBSL holiday clearing lag as legal float. I’m logging in with our app password on this machine. After login, the merchant is ready to configure banking and receive invoices.

**On screen:** Show login page → enter password → Invoices dashboard.

### 0:20–0:45 — Bank details first

> First the merchant adds their bank account details on Bank Balance—nickname, bank name, branch, and opening balance—and can keep several accounts. Cheques will later be written from a chosen account. Once banking is set, they are ready to receive invoices.

**On screen:** Open Bank Balance; add or select an account; show balance cards.

### 0:45–1:50 — WhatsApp → AI → two invoices

> Cashiers send invoice photos on WhatsApp. Photos land in the WhatsApp inbox first. I open Invoices, open WhatsApp photos, and tap Send to AI. That’s our vision agent: **input** is the photo, **steps** are Gemini extraction plus checks, **output** is structured fields on the verify screen.  
> **Invoice one**—supplier already registered. I confirm invoice number, date, amount, credit period, and dealer. Here we set supplier rules: **casual days**—extra business days the dealer usually allows—and **impossible days** like Sunday, plus strictness. Python uses that when proposing cheque dates.  
> **Invoice two**—new supplier. The app asks us to register the dealer once—name, bank, pay-from account—then save. Same dealer won’t be duplicated next time; same dealer also cannot reuse the same invoice number. Both invoices are verified and ready to bundle.

**On screen:** WhatsApp inbox → Send to AI → verify Invoice A (existing dealer + casual/impossible days). Then Invoice B (new dealer form) → save. If short on time, fully verify A and quickly show B’s pending-dealer form.

### 1:50–3:25 — Cheques: options, batching, holiday loop, AI

> Now Cheques. I pick the dealer. Here are the bundling tools: set the **LKR ceiling**; tick invoices; **Compute bundles** or **One per invoice**; **drag** or **Move to** another cheque; **Add cheque**; **right-click Split** for part payments shown in red as invoice ·1, ·2; edit the **stated date**; run **Auto-optimize**; and chat with the **Bundling Assistant**.  
> Batching: Python packs invoices under the ceiling and proposes stated dates from due dates plus casual days, then rolls weekends and CBSL holidays to true settlement and funding dates. That’s why this is built for Sri Lanka—the **holiday loop** can give extra float days. On each cheque we show **Extra days gained**.  
> I’ll ask the assistant to improve liquidity—or open Auto-optimize. **Input** is the current bundles and context; **steps** are tool calls into our deterministic Python bundling and guardrails—no invented dates; **output** is a reply plus updated groups. If the reviewer suggests changes, I click **Apply suggestions**.  
> We’re also designing a **RAG vector store**—still in build—so past successful cheque groupings for this dealer can be retrieved next time to guide future batches.

**On screen:** Open dealer Cheques → Compute → point at Extra days → Auto-optimize or chat → Apply if shown → optional split.

### 3:25–3:55 — Bank section + report

> Back on Bank Balance, for this account we see **cheques from this account** and the liquidity timetable—fund-by dates and days gained—so the owner sees what’s about to clear. After we preview—choose the paying bank—and commit, the **Analyst** agent writes a report. On Reports we open the generated analysis. Today we print from the cheque preview; full cheque stationery print is still being finished.

**On screen:** Bank Balance → cheques list + timetable. Preview → select bank → Print or Commit. Open Reports.

### 3:55–4:25 — Dark mode, Guide, languages

> For local merchants: **dark mode** here; the **Zenith Guide** chatbot answers how-to questions; and languages—**English, Sinhala, and Tamil**—so the same workflow works for local business owners.

**On screen:** Toggle dark mode; open Guide (one short question); switch language briefly, then back to English.

### 4:25–4:50 — Improvements + close

> Next improvements: finish **cheque print layouts**; a **separate clearing tracker** for cheques about to go; and **WhatsApp notifications to the owner** when a clearing date is near. Plus the **RAG memory** for per-dealer history.  
> Zenith: WhatsApp capture, AI extraction, Sri Lanka holiday-aware bundling, and multi-bank cash timing—in one local app. Thank you.

**On screen:** Stay on a clean screen (Reports or Cheques). End recording.

---

## 8. If something fails mid-recording

> While live AI recovers, the same Python bundling still runs on Compute bundles—and demo mode can stand in for chat.

---

## 9. README reminder (submit with the repo)

Before upload, confirm `README.md` includes:

- Project purpose (Sri Lankan SME cheque / invoice liquidity)
- Tech stack matching the Idealize proposal (Flask, SQLite, Gemini, OpenAI, WhatsApp, etc.)
- Setup: copy `.env.example`, `APP_PASSWORD`, API keys, DB init, run app, Cloudflare/WhatsApp webhook
- Core features + AI agent workflow (Vision → verify → Bundling Assistant → Analyst)

---

## 10. Extra features (if you have 10–15 seconds spare)

- Duplicate protection: same dealer name reused; same invoice number blocked per dealer
- Multi-bank: pay-from account on dealer; bank select when writing cheques
- Deposit alerts / planned deposits on Bank Balance
- Interbank +1 business day when merchant bank ≠ supplier bank

---

*End of presenter guide — practice once with a timer before the final take.*
