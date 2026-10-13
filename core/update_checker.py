"""Compare the installed VERSION with the latest GitHub Release. Notify only."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

from config import Config

logger = logging.getLogger(__name__)

SETTING_LATEST = "update_latest_version"
SETTING_AVAILABLE = "update_available"
SETTING_CHECKED_AT = "update_checked_at"
SETTING_RELEASE_URL = "update_release_url"


def parse_version(text: str) -> tuple[int, ...]:
    raw = (text or "").strip().lstrip("vV")
    parts: list[int] = []
    for piece in raw.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    left = parse_version(latest)
    right = parse_version(current)
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    return left > right


def fetch_latest_release(repo: str | None = None, timeout: float = 8) -> dict | None:
    """Return GitHub release JSON, or None when offline or the repo has no release."""
    name = (repo or Config.github_repo()).strip()
    if not name or "/" not in name:
        return None
    url = f"https://api.github.com/repos/{name}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Zenith-Update-Check",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.info("Update check skipped: %s", exc)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def run_update_check() -> dict:
    """Store the latest release tag. Does not download or install anything."""
    from db import repositories as repo

    current = Config.app_version()
    result = {
        "current": current,
        "latest": "",
        "update_available": False,
        "html_url": "",
    }
    release = fetch_latest_release()
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        repo.set_setting(SETTING_CHECKED_AT, checked_at)
    except Exception:
        logger.exception("Could not record update check time")
        return result
    if not release:
        return result
    latest = str(release.get("tag_name") or "").strip()
    html_url = str(release.get("html_url") or "").strip()
    available = bool(latest) and is_newer(latest, current)
    result.update(
        {
            "latest": latest,
            "update_available": available,
            "html_url": html_url,
        }
    )
    try:
        repo.set_setting(SETTING_LATEST, latest)
        repo.set_setting(SETTING_AVAILABLE, "1" if available else "0")
        repo.set_setting(SETTING_RELEASE_URL, html_url)
    except Exception:
        logger.exception("Could not store update check result")
    if available:
        logger.info("Update available: installed %s, latest %s", current, latest)
    return result


def update_status() -> dict:
    """Read the last check for the settings menu. Safe when the DB is not ready."""
    current = Config.app_version()
    empty = {
        "current": current,
        "latest": "",
        "update_available": False,
        "html_url": "",
        "checked_at": "",
    }
    try:
        from db import repositories as repo

        available = repo.get_setting(SETTING_AVAILABLE, "0") == "1"
        return {
            "current": current,
            "latest": repo.get_setting(SETTING_LATEST, ""),
            "update_available": available,
            "html_url": repo.get_setting(SETTING_RELEASE_URL, ""),
            "checked_at": repo.get_setting(SETTING_CHECKED_AT, ""),
        }
    except Exception:
        return empty
