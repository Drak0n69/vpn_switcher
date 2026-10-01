from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.models import Recipient


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_recipients(path: Path) -> list[Recipient]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("recipients", [])
    if not isinstance(entries, list):
        raise ValueError("recipients.yml: 'recipients' must be a list")

    recipients: list[Recipient] = []
    seen_users: set[int] = set()
    seen_chats: set[int] = set()
    file_owners: dict[str, str] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"recipients.yml: item #{index} must be an object")
        name = str(entry.get("name", "")).strip()
        user_id = int(entry["user_id"])
        chat_id = int(entry.get("chat_id", user_id))
        files_raw = entry.get("files", [])
        if not name:
            raise ValueError(f"recipients.yml: item #{index} has empty name")
        if user_id in seen_users:
            raise ValueError(f"recipients.yml: duplicate user_id {user_id}")
        if chat_id in seen_chats:
            raise ValueError(f"recipients.yml: duplicate chat_id {chat_id}")
        if not isinstance(files_raw, list) or not files_raw:
            raise ValueError(f"recipients.yml: {name} must have at least one file")
        files = tuple(str(v).strip() for v in files_raw if str(v).strip())
        if not files:
            raise ValueError(f"recipients.yml: {name} must have at least one non-empty file")
        for file_name in files:
            normalized = file_name.replace("\\", "/")
            previous_owner = file_owners.get(normalized)
            if previous_owner is not None:
                raise ValueError(
                    f"recipients.yml: config '{file_name}' is assigned to both "
                    f"{previous_owner} and {name}"
                )
            file_owners[normalized] = name
        recipients.append(Recipient(name=name, user_id=user_id, chat_id=chat_id, files=files))
        seen_users.add(user_id)
        seen_chats.add(chat_id)
    return recipients


def load_yaml_mapping(path: Path, root_key: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    value = raw.get(root_key, {})
    return value if isinstance(value, dict) else {}


def save_registration(path: Path, *, user_id: int, chat_id: int, username: str | None,
                      first_name: str | None, last_name: str | None) -> None:
    registrations = load_yaml_mapping(path, "registrations")
    registrations[str(user_id)] = {
        "chat_id": chat_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = yaml.safe_dump(
        {"registrations": registrations},
        allow_unicode=True,
        sort_keys=True,
    )
    _atomic_write(path, payload)


def load_delivery_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}


def save_delivery_state(path: Path, state: dict[str, str]) -> None:
    _atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
