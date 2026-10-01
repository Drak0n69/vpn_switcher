from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.models import Recipient, ResolvedRecipient


def _safe_relative_path(root: Path, relative: str) -> Path:
    posix = PurePosixPath(relative.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"Unsafe config path: {relative}")
    candidate = (root / Path(*posix.parts)).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ValueError(f"Config path escapes CONFIG_DIR: {relative}")
    return candidate


def resolve_recipient(root: Path, recipient: Recipient) -> ResolvedRecipient:
    found: list[Path] = []
    missing: list[str] = []
    for relative in recipient.files:
        path = _safe_relative_path(root, relative)
        if path.is_file() and path.suffix.lower() == ".vpn":
            found.append(path)
        else:
            missing.append(relative)
    return ResolvedRecipient(recipient=recipient, files=tuple(found), missing=tuple(missing))


def list_unassigned_vpn_files(root: Path, recipients: list[Recipient]) -> list[Path]:
    assigned: set[Path] = set()
    for recipient in recipients:
        for relative in recipient.files:
            try:
                assigned.add(_safe_relative_path(root, relative))
            except ValueError:
                continue
    if not root.exists():
        return []
    assigned_resolved = {a.resolve() for a in assigned}
    return sorted(
        p for p in root.rglob("*.vpn")
        if p.is_file() and p.resolve() not in assigned_resolved
    )
