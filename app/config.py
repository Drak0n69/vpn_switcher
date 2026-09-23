from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _csv_ints(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()
    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return frozenset(result)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: int | None
    telegram_admin_user_ids: frozenset[int]
    vpn_config_dir: Path
    vpn_output_dir: Path
    state_file: Path
    healthcheck_mode: str
    healthcheck_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        chat_id_raw = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        chat_id = int(chat_id_raw) if chat_id_raw else None

        mode = os.getenv("HEALTHCHECK_MODE", "none").strip().lower()
        if mode not in {"none", "ping"}:
            raise ValueError("HEALTHCHECK_MODE must be 'none' or 'ping'")

        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=chat_id,
            telegram_admin_user_ids=_csv_ints(os.getenv("TELEGRAM_ADMIN_USER_IDS")),
            vpn_config_dir=Path(os.getenv("VPN_CONFIG_DIR", "/data/configs")),
            vpn_output_dir=Path(os.getenv("VPN_OUTPUT_DIR", "/data/output")),
            state_file=Path(os.getenv("STATE_FILE", "/data/state.json")),
            healthcheck_mode=mode,
            healthcheck_timeout_seconds=float(os.getenv("HEALTHCHECK_TIMEOUT_SECONDS", "3")),
        )
