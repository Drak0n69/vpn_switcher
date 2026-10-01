from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Bot

from app.models import DeliveryItem, Recipient, ResolvedRecipient
from app.scanner import list_unassigned_vpn_files, resolve_recipient
from app.storage import load_delivery_state, save_delivery_state


@dataclass(frozen=True)
class Plan:
    resolved: tuple[ResolvedRecipient, ...]
    items: tuple[DeliveryItem, ...]
    unassigned: tuple[Path, ...]

    @property
    def missing_count(self) -> int:
        return sum(len(item.missing) for item in self.resolved)

    @property
    def sendable_count(self) -> int:
        return sum(1 for item in self.items if not item.unchanged)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for item in self.items if item.unchanged)


@dataclass(frozen=True)
class DeliveryResult:
    sent: int
    failed: tuple[str, ...]
    skipped_unchanged: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_key(recipient: Recipient, path: Path, config_dir: Path) -> str:
    relative = path.resolve().relative_to(config_dir.resolve()).as_posix()
    return f"{recipient.user_id}:{relative}"


def build_plan(config_dir: Path, recipients: list[Recipient], delivery_state_file: Path,
               skip_unchanged: bool) -> Plan:
    state = load_delivery_state(delivery_state_file)
    resolved = tuple(resolve_recipient(config_dir, recipient) for recipient in recipients)
    items: list[DeliveryItem] = []
    for entry in resolved:
        for path in entry.files:
            file_hash = sha256_file(path)
            key = _state_key(entry.recipient, path, config_dir)
            unchanged = bool(skip_unchanged and state.get(key) == file_hash)
            items.append(
                DeliveryItem(
                    recipient=entry.recipient,
                    path=path,
                    sha256=file_hash,
                    unchanged=unchanged,
                )
            )
    return Plan(
        resolved=resolved,
        items=tuple(items),
        unassigned=tuple(list_unassigned_vpn_files(config_dir, recipients)),
    )


def format_plan(plan: Plan, config_dir: Path) -> str:
    lines = [
        "Проверка рассылки:",
        f"• получателей: {len(plan.resolved)}",
        f"• файлов к отправке: {plan.sendable_count}",
        f"• без изменений: {plan.unchanged_count}",
        f"• отсутствующих файлов: {plan.missing_count}",
        f"• файлов без владельца: {len(plan.unassigned)}",
    ]
    missing_lines: list[str] = []
    for entry in plan.resolved:
        for missing in entry.missing:
            missing_lines.append(f"  - {entry.recipient.name}: {missing}")
    if missing_lines:
        lines.append("\nНе найдены:")
        lines.extend(missing_lines[:20])
        if len(missing_lines) > 20:
            lines.append(f"  ... ещё {len(missing_lines) - 20}")
    if plan.unassigned:
        lines.append("\nБез владельца:")
        for path in plan.unassigned[:20]:
            lines.append(f"  - {path.resolve().relative_to(config_dir.resolve()).as_posix()}")
        if len(plan.unassigned) > 20:
            lines.append(f"  ... ещё {len(plan.unassigned) - 20}")
    return "\n".join(lines)


async def distribute(bot: "Bot", plan: Plan, *, config_dir: Path, delivery_state_file: Path,
                     send_delay_seconds: float) -> DeliveryResult:
    state = load_delivery_state(delivery_state_file)
    sent = 0
    failed: list[str] = []
    skipped = 0

    for item in plan.items:
        if item.unchanged:
            skipped += 1
            continue
        relative = item.path.resolve().relative_to(config_dir.resolve()).as_posix()
        try:
            with item.path.open("rb") as document:
                await bot.send_document(
                    chat_id=item.recipient.chat_id,
                    document=document,
                    filename=item.path.name,
                    caption=(
                        "Обновлённая конфигурация VPN.\n"
                        f"Файл: {item.path.name}\n\n"
                        "Импортируйте файл в Amnezia VPN."
                    ),
                )
            state[_state_key(item.recipient, item.path, config_dir)] = item.sha256
            save_delivery_state(delivery_state_file, state)
            sent += 1
        except Exception as exc:  # Telegram/network errors must not stop the entire batch.
            failed.append(f"{item.recipient.name} / {relative}: {type(exc).__name__}: {exc}")
        if send_delay_seconds > 0:
            await asyncio.sleep(send_delay_seconds)

    return DeliveryResult(sent=sent, failed=tuple(failed), skipped_unchanged=skipped)
