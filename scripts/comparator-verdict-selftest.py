#!/usr/bin/env python3
"""Unit test: the verdict axis flags a PASS/DROP disagreement even when the
captured frame bytes are identical (no kernel required).

xdpdump reports the XDP action in its text output as `<prog>()@exit[PASS]` /
`@exit[DROP]`, not in the pcapng frame. This test synthesises two xdpdump `-x`
style logs for the same test id with identical frame bytes but opposite
verdicts, feeds them to compare.py via --verdict, and asserts:

  divergence_count          == 0   (frame bytes are identical — byte diff is blind)
  verdict_divergence_count  >= 1   (verdict diff catches the disposition mismatch)

This proves the verdict-parsing/diff logic has teeth without needing a corpus
packet that actually triggers a program's DROP branch.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from scapy.all import Ether, IP, TCP, Raw, wrpcap


def xdpdump_hex_record(prog: str, hook: str, action: str | None, frame: bytes, rid: int) -> str:
    """Render one xdpdump `-x` record (header + hex dump) matching the observed
    xdpdump 1.4.x text format closely enough for compare.parse_verdict_log()."""
    tag = f"[{action}]" if action else ""
    n = len(frame)
    lines = [
        f"1700000000.000000000: {prog}()@{hook}{tag}: "
        f"packet size {n} bytes, captured {n} bytes on if_index 1, rx queue 0, id {rid}"
    ]
    for off in range(0, n, 16):
        chunk = frame[off : off + 16]
        hexs = " ".join(f"{b:02x}" for b in chunk)
        lines.append(f"  0x{off:04x}:  {hexs}")
    return "\n".join(lines) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tid = 0xA0F0
    pkt = (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=443, flags="S")
        / Raw(load=b"XTPE" + tid.to_bytes(2, "big"))
    )
    frame = bytes(pkt)

    def verdict_log(action: str) -> str:
        return (
            xdpdump_hex_record("xdp_verdict_selftest", "entry", None, frame, 1)
            + xdpdump_hex_record("xdp_verdict_selftest", "exit", action, frame, 1)
        )

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        nat_pcap = td / "native.pcap"
        gen_pcap = td / "generic.pcap"
        nat_v = td / "native_verdict.txt"
        gen_v = td / "generic_verdict.txt"
        out = td / "manifest.json"

        # Identical bytes on both backends — byte comparator must see equivalence.
        wrpcap(str(nat_pcap), [pkt])
        wrpcap(str(gen_pcap), [pkt])
        # Opposite verdicts — verdict comparator must flag a divergence.
        nat_v.write_text(verdict_log("PASS"))
        gen_v.write_text(verdict_log("DROP"))

        subprocess.check_call(
            [
                sys.executable,
                str(root / "harness" / "compare.py"),
                str(out),
                f"native:{nat_pcap}",
                f"generic:{gen_pcap}",
                "--verdict",
                f"native:{nat_v}",
                "--verdict",
                f"generic:{gen_v}",
            ],
            cwd=root,
        )
        data = json.loads(out.read_text())

    byte_div = data.get("divergence_count")
    verdict_div = data.get("verdict_divergence_count")
    if byte_div != 0:
        raise SystemExit(f"FAIL: expected 0 byte divergences (identical frames), got {byte_div}")
    if not verdict_div or verdict_div < 1:
        raise SystemExit(
            f"FAIL: verdict self-test expected >=1 verdict divergence, got {verdict_div}"
        )
    case = data["cases"][0]
    if case.get("verdict_match") is not False:
        raise SystemExit(f"FAIL: expected verdict_match=False on the case, got {case.get('verdict_match')}")
    print(
        f"VERDICT SELFTEST OK — byte_divergences={byte_div}, "
        f"verdict_divergences={verdict_div} (PASS vs DROP on identical bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
