from config import _env
from core.auth import verify_password
from db import repositories as repo
from db.connection import query


def main():
    tables = [r["name"] for r in query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("tables", tables)
    assert "app_settings" in tables
    assert "invoices" in tables
    print("default_bank", repo.get_setting("default_bank_acc_id", "1"))
    print("pending", len(repo.get_pending_verification_invoices()))
    print("dealers", len(repo.get_dealers()))
    print("accounts", repo.get_all_account_ids())
    print("holidays", len(repo.get_holidays()))
    assert verify_password(_env("APP_PASSWORD"))
    assert not verify_password("nope")
    print("auth_ok")


if __name__ == "__main__":
    main()
