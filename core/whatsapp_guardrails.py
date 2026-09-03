"""WhatsApp inbound guardrails — approved-sender checks (parameterized SQLite).

Zenith stores approved numbers in ``whatsapp_allowed_senders`` (phone_e164,
display_name, is_active) inside the main app database — same role as an
``approved_senders`` table. Prefer that table over a second DB file.
"""

from __future__ import annotations

from config import Config
from core.whatsapp_utils import normalize_whatsapp_phone
from db import repositories as repo


def ensure_approved_senders_schema() -> None:
    """Idempotent: creates whatsapp_allowed_senders if missing (legacy DBs)."""
    repo.ensure_whatsapp_allowed_senders_schema()


def list_active_approved_phones() -> list[str]:
    """Return normalized E.164 phones with is_active=1 (bound query via repo)."""
    ensure_approved_senders_schema()
    rows = repo.list_allowed_senders()
    return [
        normalize_whatsapp_phone(r["phone_e164"])
        for r in rows
        if int(r.get("is_active") or 0) == 1
    ]


def is_approved_sender(phone: str) -> bool:
    """True if sender may send invoice photos into Zenith.

    Policy:
    - If the DB has any *active* approved senders → phone must match one
      (parameterized lookup in ``is_sender_allowed``).
    - Else if ``WHATSAPP_ALLOWED_NUMBERS`` env is set → must match that list.
    - Else (empty whitelist, testing) → allow all numbers.
    """
    ensure_approved_senders_schema()
    active = list_active_approved_phones()
    if active:
        return repo.is_sender_allowed(phone)

    env_allowed = Config.whatsapp_allowed_numbers()
    if not env_allowed:
        return True

    normalized = normalize_whatsapp_phone(phone)
    allowed_norm = {normalize_whatsapp_phone(n) for n in env_allowed}
    return normalized in allowed_norm


def log_unauthorized_sender(phone: str, *, message_type: str | None = None) -> None:
    """Console security alert for Meta/ops dashboards (stdout → Render logs)."""
    print(
        "[whatsapp][SECURITY] unauthorized_number "
        f"from={normalize_whatsapp_phone(phone)!r} "
        f"type={message_type!r} — ignored (HTTP 200 so Meta will not retry)",
        flush=True,
    )
