from __future__ import annotations

import argparse
from pathlib import Path

from app.switcher import save_state, switch_all
from app.vpn_config import collect_hosts, decode_vpn


def cmd_inspect(config_dir: Path) -> None:
    files = sorted(config_dir.glob("*.vpn"))
    if not files:
        raise SystemExit(f"No .vpn files found in {config_dir}")
    for path in files:
        data = decode_vpn(path.read_text(encoding="utf-8"))
        hosts = ", ".join(collect_hosts(data)) or "<not found>"
        print(f"{path.name}: host(s)={hosts}")


def cmd_switch(config_dir: Path, output_dir: Path, state_file: Path, host: str) -> None:
    summary, results = switch_all(config_dir, output_dir, host)
    save_state(state_file, summary)
    for result in results:
        print(f"{result.source.name}: {result.changes} field(s) -> {result.output}")
    print(f"Done: endpoint={summary.host}, files={summary.files}, changes={summary.changes}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Amnezia VPN endpoint switcher")
    parser.add_argument("--config-dir", type=Path, default=Path("data/configs"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/output"))
    parser.add_argument("--state-file", type=Path, default=Path("data/state.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    switch = sub.add_parser("switch")
    switch.add_argument("host")
    args = parser.parse_args()

    if args.command == "inspect":
        cmd_inspect(args.config_dir)
    else:
        cmd_switch(args.config_dir, args.output_dir, args.state_file, args.host)


if __name__ == "__main__":
    main()
