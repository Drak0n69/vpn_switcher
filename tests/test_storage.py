from pathlib import Path

from app.storage import load_recipients


def test_load_recipients(tmp_path: Path) -> None:
    path = tmp_path / "recipients.yml"
    path.write_text(
        """
recipients:
  - name: Denis
    user_id: 100
    chat_id: 100
    files:
      - denis.vpn
      - denis-phone.vpn
""".strip(),
        encoding="utf-8",
    )
    recipients = load_recipients(path)
    assert len(recipients) == 1
    assert recipients[0].files == ("denis.vpn", "denis-phone.vpn")


def test_duplicate_config_assignment_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "recipients.yml"
    path.write_text(
        """
recipients:
  - name: Denis
    user_id: 100
    chat_id: 100
    files: [same.vpn]
  - name: Ivan
    user_id: 200
    chat_id: 200
    files: [same.vpn]
""".strip(),
        encoding="utf-8",
    )
    try:
        load_recipients(path)
    except ValueError as exc:
        assert "assigned to both" in str(exc)
    else:
        raise AssertionError("duplicate config assignment must fail")
