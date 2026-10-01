from pathlib import Path

from app.distributor import build_plan
from app.models import Recipient


def test_build_plan_marks_unchanged(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config = config_dir / "denis.vpn"
    config.write_bytes(b"same")
    state = tmp_path / "state.json"
    recipient = Recipient("Denis", 1, 1, ("denis.vpn",))

    first = build_plan(config_dir, [recipient], state, skip_unchanged=True)
    assert first.sendable_count == 1
    assert first.unchanged_count == 0
