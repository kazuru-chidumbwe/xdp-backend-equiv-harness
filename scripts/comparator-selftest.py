#!/usr/bin/env python3
"""Unit test: compare.py flags intentional fingerprint mismatch (no kernel required)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scapy.all import Ether, IP, TCP, Raw, wrpcap


def fp(pkt) -> str:
    return hashlib.sha256(bytes(pkt)).hexdigest()[:16]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tid = 0xA099
    base = (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=443, flags="S")
        / Raw(load=b"XTPE" + tid.to_bytes(2, "big"))
    )
    alt = (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1", ttl=63)
        / TCP(sport=tid, dport=443, flags="S")
        / Raw(load=b"XTPE" + tid.to_bytes(2, "big"))
    )
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        nat = td / "native.pcap"
        gen = td / "generic.pcap"
        out = td / "manifest.json"
        wrpcap(str(nat), [base])
        wrpcap(str(gen), [alt])
        subprocess.check_call(
            [
                sys.executable,
                str(root / "harness" / "compare.py"),
                str(out),
                f"native:{nat}",
                f"generic:{gen}",
            ],
            cwd=root,
        )
        data = json.loads(out.read_text())
    div = data.get("divergence_count", 0)
    if div < 1:
        raise SystemExit(f"FAIL: comparator self-test expected >=1 divergence, got {div}")
    print(f"SELFTEST OK — divergence_count={div}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
