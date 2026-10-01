from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _parse_int_set(value: str) -> frozenset[int]:
    result: set[int] = set()
    for raw in value.split(","):
        raw = raw.strip()
        if raw:
            result.add(int(raw))
    return frozenset(result)


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_user_ids: frozenset[int]
    config_dir: Path
    recipients_file: Path
    registrations_file: Path
    delivery_state_file: Path
    announcement_chat_id: int | None
    skip_unchanged: bool
    send_delay_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        admin_ids = _parse_int_set(os.getenv("ADMIN_USER_IDS", ""))

        announcement = os.getenv("ANNOUNCEMENT_CHAT_ID", "").strip()
        return cls(
            bot_token=_required("TELEGRAM_BOT_TOKEN"),
            admin_user_ids=admin_ids,
            config_dir=Path(os.getenv("CONFIG_DIR", "/data/configs")),
            recipients_file=Path(os.getenv("RECIPIENTS_FILE", "/data/recipients.yml")),
            registrations_file=Path(os.getenv("REGISTRATIONS_FILE", "/data/registrations.yml")),
            delivery_state_file=Path(os.getenv("DELIVERY_STATE_FILE", "/data/delivery_state.json")),
            announcement_chat_id=int(announcement) if announcement else None,
            skip_unchanged=_parse_bool("SKIP_UNCHANGED", True),
            send_delay_seconds=float(os.getenv("SEND_DELAY_SECONDS", "0.1")),
        )
