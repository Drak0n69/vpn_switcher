from pathlib import Path

from app.models import Recipient
from app.scanner import list_unassigned_vpn_files, resolve_recipient


def test_resolve_recipient(tmp_path: Path) -> None:
    (tmp_path / "denis.vpn").write_bytes(b"test")
    recipient = Recipient("Denis", 1, 1, ("denis.vpn", "phone.vpn"))
    resolved = resolve_recipient(tmp_path, recipient)
    assert [p.name for p in resolved.files] == ["denis.vpn"]
    assert resolved.missing == ("phone.vpn",)


def test_unassigned(tmp_path: Path) -> None:
    (tmp_path / "a.vpn").write_bytes(b"a")
    (tmp_path / "b.vpn").write_bytes(b"b")
    recipient = Recipient("A", 1, 1, ("a.vpn",))
    assert [p.name for p in list_unassigned_vpn_files(tmp_path, [recipient])] == ["b.vpn"]
