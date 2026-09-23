import copy
import json

from app.vpn_config import collect_hosts, decode_vpn, encode_vpn, patch_host


SAMPLE = {
    "hostName": "192.0.2.10",
    "containers": [
        {
            "container": "amnezia-awg2",
            "awg": {
                "protocol_version": "3.1",
                "last_config": json.dumps(
                    {
                        "hostName": "192.0.2.10",
                        "client_priv_key": "CLIENT_PRIVATE_SECRET",
                        "psk_key": "PSK_SECRET",
                        "config": (
                            "[Interface]\n"
                            "PrivateKey = CLIENT_PRIVATE_SECRET\n\n"
                            "[Peer]\n"
                            "PresharedKey = PSK_SECRET\n"
                            "Endpoint = 192.0.2.10:42844\n"
                        ),
                    },
                    separators=(",", ":"),
                ),
            },
        }
    ],
}


def test_roundtrip_qcompress_format():
    encoded = encode_vpn(SAMPLE)
    assert encoded.startswith("vpn://")
    assert decode_vpn(encoded) == SAMPLE


def test_patch_changes_only_host_fields():
    original = copy.deepcopy(SAMPLE)
    patched, changes = patch_host(SAMPLE, "198.51.100.20")
    assert changes == 3
    assert collect_hosts(patched) == ("198.51.100.20",)

    last_before = json.loads(original["containers"][0]["awg"]["last_config"])
    last_after = json.loads(patched["containers"][0]["awg"]["last_config"])
    assert last_after["client_priv_key"] == last_before["client_priv_key"]
    assert last_after["psk_key"] == last_before["psk_key"]
    assert "PrivateKey = CLIENT_PRIVATE_SECRET" in last_after["config"]
    assert "PresharedKey = PSK_SECRET" in last_after["config"]
    assert "Endpoint = 198.51.100.20:42844" in last_after["config"]


def test_ipv6_endpoint_is_bracketed():
    patched, _ = patch_host(SAMPLE, "2001:db8::123")
    last_after = json.loads(patched["containers"][0]["awg"]["last_config"])
    assert "Endpoint = [2001:db8::123]:42844" in last_after["config"]
