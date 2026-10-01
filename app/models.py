from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Recipient:
    name: str
    user_id: int
    chat_id: int
    files: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedRecipient:
    recipient: Recipient
    files: tuple[Path, ...]
    missing: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DeliveryItem:
    recipient: Recipient
    path: Path
    sha256: str
    unchanged: bool
