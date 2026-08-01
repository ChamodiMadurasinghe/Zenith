from __future__ import annotations

from db import repositories as repo


def build_onboarding_prompt(dealer_setup: dict) -> str:
    return (
        "New supplier detected.\n"
        f"Name: {dealer_setup.get('dealer_name') or '-'}\n"
        f"Phone: {dealer_setup.get('dealer_telno') or '-'}\n"
        f"Email: {dealer_setup.get('dealer_email') or '-'}\n"
        "Reply YES to register this dealer, or NO to keep as pending."
    )


def parse_onboarding_reply(text: str) -> str:
    value = (text or "").strip().lower()
    if value in {"yes", "y", "ok", "confirm", "register"}:
        return "confirm"
    if value in {"no", "n", "skip", "cancel"}:
        return "reject"
    return "unknown"


def register_dealer_from_setup(setup: dict) -> int:
    dealer_data = {
        "dealer_name": setup.get("dealer_name"),
        "dealer_email": setup.get("dealer_email"),
        "dealer_telno": setup.get("dealer_telno"),
        "dealer_address": setup.get("dealer_address"),
        "dealer_strictness": setup.get("dealer_strictness", "Medium"),
        "casual_days": setup.get("casual_days", 3),
        "impossible_days": setup.get("impossible_days", "Sunday"),
        "account_name": setup.get("account_name"),
        "bank_name": setup.get("bank_name"),
        "branch_name": setup.get("branch_name"),
        "default_user_bank_acc_id": setup.get("default_user_bank_acc_id"),
    }
    dealer_id = repo.create_dealer(dealer_data)
    save_err = repo.save_dealer_banking(dealer_id, dealer_data)
    if save_err:
        raise RuntimeError(save_err)
    return dealer_id
