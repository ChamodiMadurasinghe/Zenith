# Zenith

Local cheque & invoice management for Sri Lankan businesses. Python (Flask) backend with multi-provider AI:

- **Gemini** — invoice vision (ingestion / agentic Agent 1)
- **Bundling Assistant** — OpenAI + LangChain tool-calling over `core/bundling.py` (not the same as agentic Agents 2–3)
- **Analyst** — OpenAI reports
- **agentic/** pipeline — Agents 1–4 (Vision → Anomaly → Liquidity → Dealer liaison)

## Setup

```bash
pip install -r requirements.txt
copy .env.example .env    # or cp on Linux/Mac
```

Edit `.env`:
- `APP_PASSWORD` — your login password
- `GEMINI_API_KEY` + `GEMINI_VISION_MODEL` — invoice vision
- `OPENAI_API_KEY` + `OPENAI_CHAT_MODEL` / `OPENAI_ANALYST_MODEL` — Bundling Assistant + analyst
- `USE_BUNDLING_TOOL_AGENT=true` — LangChain tools (set `false` for legacy JSON `proposed_actions`)
- `USE_FAKE_AI=true` — demo chat mode (zero API quota while designing UI)

Initialize the database:

```bash
python scripts/init_db.py
```

## Run

```bash
python app.py
```

Open http://127.0.0.1:5000 and sign in with `APP_PASSWORD`.

## WhatsApp invoice agent (Meta Cloud API)

Cashiers can snap invoice/cheque photos on WhatsApp instead of using the web upload form. Default provider is **Meta WhatsApp Cloud API** (`WHATSAPP_PROVIDER=meta`).

1. Create a Meta app with WhatsApp → copy **Temporary/permanent access token** and **Phone number ID** into `.env`:
   - `META_WHATSAPP_TOKEN`
   - `META_PHONE_NUMBER_ID`
   - `META_VERIFY_TOKEN` (any secret string you choose)
2. Keep `USE_WHATSAPP_MOCK=true` for local testing; set a sample invoice at `MOCK_IMAGE_PATH=storage/invoices/your-sample.jpg`
3. Run the mock pipeline: `python whatsapp_agent.py` (prints the reply text)
4. Live webhook:
   - Run `python app.py` and expose with [ngrok](https://ngrok.com/) (`ngrok http 5000`) or Cloudflare tunnel
   - In Meta → WhatsApp → Configuration, set callback URL to `https://YOUR-HOST/webhook/whatsapp`
   - Use the same `META_VERIFY_TOKEN` for Verify Token
   - Subscribe to `messages`
5. Set `USE_WHATSAPP_MOCK=false` and optionally restrict senders with `WHATSAPP_ALLOWED_NUMBERS=+9477...`

Photos land in the **WhatsApp inbox** first; Gemini (Agent 1) runs when you tap **Send to AI**.

Optional legacy Twilio: set `WHATSAPP_PROVIDER=twilio` and fill `TWILIO_*` vars.

The webhook downloads the image, runs Gemini extraction, computes CBSL holiday liquidity, replies on WhatsApp, and saves intakes as pending verification in the web app.

## Database

See [database/DATABASE.md](database/DATABASE.md) for full schema reference.

Rebuild anytime: `python scripts/init_db.py`

## Features

- **Login** — single-user password gate
- **Invoice upload** — Gemini vision extraction + human verification
- **Cheque bundling** — LKR ceiling grouping with guardrails + chat assistant
- **Cash flow** — when to deposit money into the bank
- **Analytics** — Agent 3 markdown reports after cheque commits
