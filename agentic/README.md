# Agentic AI Integration (Sithil)

Multi-agent orchestration layer for ChequeMate. **Sits alongside** existing Zenith code — does not replace `routes/ingestion.py`, the local WhatsApp bridge, or `agents/*`.

## Entry points

```python
from agentic import handle_event, get_session_trace
from agentic.contracts.events import EventType, InboundEvent

event = InboundEvent(
    event_type=EventType.INVOICE_IMAGE,
    session_id="demo-1",
    payload={"image_path": "/path/to/invoice.jpg", "lang": "en"},
    source="web",
)
actions = handle_event(event)
```

## HTTP routes (new)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/orchestrate` | Send `InboundEvent` JSON |
| GET | `/api/sessions/<id>/trace` | Agent activity trace for UI/video |
| GET | `/api/agentic/health` | Health check |

## Integration with Zenith (no changes to their modules)

| Your layer | Calls existing |
|------------|----------------|
| `adapters/zenith_tools.py` | `agents.ingestion`, `agents.anomaly`, `core.liquidity_engine` |
| `adapters/zenith_repository.py` | `db.repositories.get_holidays()` for CBSL dates |
| `orchestrator/pipeline.py` | PER loop + FSM across 4 agents |

Existing upload flows continue unchanged unless `USE_AGENTIC_ORCHESTRATOR=true` in `.env`.

## WhatsApp integration (Meta Cloud API)

WhatsApp intake uses **Meta webhooks** → `/webhook/whatsapp` → `whatsapp_inbox` (see root `README.md`). User taps **Send to AI** on the web app to run Gemini OCR.

Optional: Node.js bridge → `POST /api/invoices/ingest` for dev. Optional Twilio when `WHATSAPP_PROVIDER=twilio`.

## Tests

```bash
cd "the project/Zenith"
pytest agentic/tests -v
```
