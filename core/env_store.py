"""Read and update the .env file the running app actually uses."""

from __future__ import annotations

from pathlib import Path

from config import secrets_env_path


def _format_value(value: str) -> str:
    if any(ch in value for ch in (' ', '#', '"', "'", "\n", "\r")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def update_keys(updates: dict[str, str], path: Path | None = None) -> Path:
    """Upsert KEY=value lines. Existing comments and unrelated keys are kept."""
    target = path or secrets_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    written: set[str] = set()
    out: list[str] = []
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={_format_value(updates[key])}")
            written.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in written:
            out.append(f"{key}={_format_value(value)}")
    target.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    return target
