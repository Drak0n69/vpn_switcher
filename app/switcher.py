from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.vpn_config import PatchResult, normalize_host, patch_file


@dataclass(frozen=True)
class SwitchSummary:
    host: str
    files: int
    changes: int
    outputs: tuple[str, ...]


def switch_all(config_dir: Path, output_dir: Path, new_host: str) -> tuple[SwitchSummary, list[PatchResult]]:
    new_host = normalize_host(new_host)
    sources = sorted(Path(config_dir).glob("*.vpn"))
    if not sources:
        raise FileNotFoundError(f"No .vpn files found in {config_dir}")

    results: list[PatchResult] = []
    for source in sources:
        output = Path(output_dir) / source.name
        results.append(patch_file(source, output, new_host))

    summary = SwitchSummary(
        host=new_host,
        files=len(results),
        changes=sum(item.changes for item in results),
        outputs=tuple(str(item.output) for item in results),
    )
    return summary, results


def save_state(path: Path, summary: SwitchSummary) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **asdict(summary),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_state(path: Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
