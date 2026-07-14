#!/usr/bin/env python3
"""Demo: identical frame bytes give divergence_count 0, even though v1 cannot
see the two axes on which backends most often actually disagree.

This is not a pass/fail unit test. It documents a known limitation: the v1
comparator fingerprints frame bytes only. Two backends can differ in
disposition (DROP vs PASS on a byte-preserving program) or in xdp_md context
(data_meta, ingress_ifindex, rx_queue_index) while producing identical exit
frames. Those differences live in pcapng metadata or in xdp_md, neither of
which is part of bytes(pkt), so this run reports 0 divergences by construction.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scapy.all import Ether, IP, TCP, Raw, wrpcap


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tid = 0xA097
    # Same bytes on both backends. Imagine native PASSed and generic DROPped,
    # or that data_meta headroom differed — none of that is in the frame, so
    # the comparator sees identical fingerprints and reports equivalence.
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
        wrpcap(str(gen), [pkt])
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
    if div != 0:
        raise SystemExit(f"FAIL: blind-spot demo expected 0 divergences, got {div}")
    print(f"BLINDSPOT OK — divergence_count={div} on identical frame bytes")
    print(
        "  v1 byte fingerprints see frame bytes only. Disposition (xdpdump text "
        "@exit[DROP]/@exit[PASS]) is now compared via --verdict; xdp_md context "
        "(data_meta, ingress_ifindex, rx_queue_index) is still not captured."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
