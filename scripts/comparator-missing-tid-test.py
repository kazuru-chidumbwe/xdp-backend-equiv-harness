#!/usr/bin/env python3
"""Unit test: missing test ID on one backend counts as divergence."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scapy.all import Ether, IP, TCP, Raw, wrpcap


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tid = 0xA098
    pkt = (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=443, flags="S")
        / Raw(load=b"XTPE" + tid.to_bytes(2, "big"))
    )
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        nat = td / "native.pcap"
        gen = td / "generic.pcap"
        out = td / "manifest.json"
        wrpcap(str(nat), [pkt])
        wrpcap(str(gen), [])  # generic backend saw nothing for this tid
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
        raise SystemExit(f"FAIL: missing-tid test expected >=1 divergence, got {div}")
    print(f"MISSING-TID OK — divergence_count={div}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
