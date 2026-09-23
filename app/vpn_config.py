from __future__ import annotations

import base64
import copy
import ipaddress
import json
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


class VpnConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PatchResult:
    source: Path
    output: Path
    old_hosts: tuple[str, ...]
    new_host: str
    changes: int


def _b64url_decode(value: str) -> bytes:
    value = value.strip()
    value += "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(value)
    except Exception as exc:  # noqa: BLE001
        raise VpnConfigError("Invalid base64url payload") from exc


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_vpn(text: str) -> dict:
    text = text.strip()
    if not text.startswith("vpn://"):
        raise VpnConfigError("Expected vpn:// payload")

    packed = _b64url_decode(text[6:])

    # Amnezia export uses Qt qCompress():
    # 4-byte big-endian uncompressed length + zlib stream.
    if len(packed) >= 6:
        expected_len = struct.unpack(">I", packed[:4])[0]
        try:
            raw = zlib.decompress(packed[4:])
            if expected_len and len(raw) != expected_len:
                raise VpnConfigError(
                    f"Unexpected uncompressed length: expected {expected_len}, got {len(raw)}"
                )
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise VpnConfigError("VPN payload is not a JSON object")
            return value
        except zlib.error:
            pass
        except json.JSONDecodeError as exc:
            raise VpnConfigError("Invalid JSON in compressed payload") from exc

    # Fallback for an uncompressed base64 JSON payload.
    try:
        value = json.loads(packed.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VpnConfigError("Unable to decode VPN payload") from exc
    if not isinstance(value, dict):
        raise VpnConfigError("VPN payload is not a JSON object")
    return value


def encode_vpn(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = struct.pack(">I", len(raw)) + zlib.compress(raw)
    return "vpn://" + _b64url_encode(packed)


def normalize_host(host: str) -> str:
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass

    # Conservative DNS-name validation. Allows single-label hosts for local testing.
    if len(host) > 253 or not host:
        raise VpnConfigError("Invalid IP address or DNS hostname")
    labels = host.rstrip(".").split(".")
    label_re = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
    if not all(label_re.fullmatch(label) for label in labels):
        raise VpnConfigError("Invalid IP address or DNS hostname")
    return host.rstrip(".").lower()


def _endpoint_host(host: str) -> str:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{addr}]" if addr.version == 6 else str(addr)


def _replace_endpoint_host(config: str, new_host: str) -> tuple[str, int]:
    # Keep the existing port intact. Supports hostnames, IPv4 and [IPv6].
    pattern = re.compile(r"(?m)^(\s*Endpoint\s*=\s*)(\[[^\]]+\]|[^:\s]+)(:\d+\s*)$")
    replacement = _endpoint_host(new_host)
    return pattern.subn(lambda m: f"{m.group(1)}{replacement}{m.group(3)}", config)


def collect_hosts(data: dict) -> tuple[str, ...]:
    hosts: set[str] = set()
    top = data.get("hostName")
    if isinstance(top, str) and top:
        hosts.add(top)

    for container in data.get("containers", []):
        if not isinstance(container, dict):
            continue
        for proto_name in ("awg", "wireguard"):
            proto = container.get(proto_name)
            if not isinstance(proto, dict):
                continue
            direct = proto.get("hostName")
            if isinstance(direct, str) and direct:
                hosts.add(direct)
            last_raw = proto.get("last_config")
            if not last_raw:
                continue
            try:
                last = json.loads(last_raw) if isinstance(last_raw, str) else last_raw
            except json.JSONDecodeError:
                continue
            if isinstance(last, dict):
                nested = last.get("hostName")
                if isinstance(nested, str) and nested:
                    hosts.add(nested)
                config_text = last.get("config")
                if isinstance(config_text, str):
                    match = re.search(
                        r"(?m)^\s*Endpoint\s*=\s*(\[[^\]]+\]|[^:\s]+):\d+\s*$",
                        config_text,
                    )
                    if match:
                        hosts.add(match.group(1).strip("[]"))
    return tuple(sorted(hosts))


def patch_host(data: dict, new_host: str) -> tuple[dict, int]:
    new_host = normalize_host(new_host)
    patched = copy.deepcopy(data)
    changes = 0

    if "hostName" in patched and patched.get("hostName") != new_host:
        patched["hostName"] = new_host
        changes += 1

    for container in patched.get("containers", []):
        if not isinstance(container, dict):
            continue
        for proto_name in ("awg", "wireguard"):
            proto = container.get(proto_name)
            if not isinstance(proto, dict):
                continue

            if "hostName" in proto and proto.get("hostName") != new_host:
                proto["hostName"] = new_host
                changes += 1

            last_config_raw = proto.get("last_config")
            if not last_config_raw:
                continue

            try:
                last_config = (
                    json.loads(last_config_raw)
                    if isinstance(last_config_raw, str)
                    else copy.deepcopy(last_config_raw)
                )
            except json.JSONDecodeError as exc:
                raise VpnConfigError("Invalid JSON in last_config") from exc

            if not isinstance(last_config, dict):
                raise VpnConfigError("last_config must be a JSON object")

            if "hostName" in last_config and last_config.get("hostName") != new_host:
                last_config["hostName"] = new_host
                changes += 1

            config_text = last_config.get("config")
            if isinstance(config_text, str):
                patched_config, count = _replace_endpoint_host(config_text, new_host)
                if count:
                    last_config["config"] = patched_config
                    changes += count

            proto["last_config"] = (
                json.dumps(last_config, ensure_ascii=False, separators=(",", ":"))
                if isinstance(last_config_raw, str)
                else last_config
            )

    return patched, changes


def patch_file(source: Path, output: Path, new_host: str) -> PatchResult:
    source = Path(source)
    output = Path(output)
    data = decode_vpn(source.read_text(encoding="utf-8"))
    old_hosts = collect_hosts(data)
    patched, changes = patch_host(data, new_host)
    if changes == 0:
        raise VpnConfigError(f"No host/Endpoint fields changed in {source.name}")

    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    tmp.write_text(encode_vpn(patched), encoding="utf-8")
    tmp.replace(output)

    return PatchResult(
        source=source,
        output=output,
        old_hosts=old_hosts,
        new_host=normalize_host(new_host),
        changes=changes,
    )
