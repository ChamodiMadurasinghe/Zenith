"""Sidebar and mobile dock items for the simple UI."""

from __future__ import annotations

from dataclasses import dataclass

from flask import url_for
from werkzeug.routing import BuildError


@dataclass(frozen=True)
class NavItem:
    key: str
    endpoint: str
    icon: str
    label_key: str
    sub_key: str
    # Endpoint prefixes that also mark this item active (sub-pages).
    active_prefixes: tuple[str, ...] = ()


MAIN_ITEMS = (
    NavItem("today", "simple.today", "home", "s_nav_today", "s_nav_today_sub"),
    NavItem("invoices", "simple.invoices", "invoice", "s_nav_invoices", "s_nav_invoices_sub", ("simple.invoice",)),
    NavItem("cheques", "simple.cheques", "cheque", "s_nav_cheques", "s_nav_cheques_sub", ("simple.cheque", "simple.supplier")),
    NavItem("money", "simple.money", "bank", "s_nav_money", "s_nav_money_sub", ("simple.money_",)),
)

SETTINGS_ITEM = NavItem(
    "settings", "simple.settings", "settings", "s_nav_settings", "s_nav_settings_sub", ("simple.settings_",)
)


def _url(endpoint: str) -> str | None:
    """URL for an endpoint, or None while that screen is not built yet."""
    try:
        return url_for(endpoint)
    except BuildError:
        return None


def is_active(item: NavItem, endpoint: str | None) -> bool:
    if not endpoint:
        return False
    return endpoint == item.endpoint or endpoint.startswith(item.active_prefixes or ("\0",))


def nav_context(endpoint: str | None) -> dict:
    """Template-ready nav entries: label keys, icon, url (None if unavailable), active flag."""

    def entry(item: NavItem) -> dict:
        return {
            "key": item.key,
            "icon": item.icon,
            "label_key": item.label_key,
            "sub_key": item.sub_key,
            "url": _url(item.endpoint),
            "active": is_active(item, endpoint),
        }

    return {
        "main": [entry(i) for i in MAIN_ITEMS],
        "settings": entry(SETTINGS_ITEM),
    }
