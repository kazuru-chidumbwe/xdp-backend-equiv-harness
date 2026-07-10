#!/usr/bin/env python3
"""Pair captures by embedded test ID; emit divergence manifest."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scapy.all import ICMP, Raw, TCP, UDP, rdpcap
except ImportError:
    print("scapy required", file=sys.stderr)
    sys.exit(1)


def extract_tid(pkt) -> int | None:
    if Raw in pkt:
        payload = bytes(pkt[Raw].load)
        if len(payload) >= 2:
            tid = int.from_bytes(payload[-2:], "big")
            if 0xA000 <= tid <= 0xA0FF:
                return tid
    if pkt.haslayer(TCP):
        sport = int(pkt[TCP].sport)
        if 0xA000 <= sport <= 0xA0FF:
            return sport
    if pkt.haslayer(UDP):
        sport = int(pkt[UDP].sport)
        if 0xA000 <= sport <= 0xA0FF:
            return sport
    if pkt.haslayer(ICMP):
        icmp_id = int(pkt[ICMP].id)
        if 0xA000 <= icmp_id <= 0xA0FF:
            return icmp_id
    return None


def packet_fingerprint(pkt) -> str:
    return hashlib.sha256(bytes(pkt)).hexdigest()[:16]


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index(path: Path) -> dict[int, str]:
    idx = {}
    for pkt in rdpcap(str(path)):
        tid = extract_tid(pkt)
        if tid is not None:
            idx[tid] = packet_fingerprint(pkt)
    return idx


def compare(backends: dict[str, Path]) -> dict:
    indices = {name: load_index(p) for name, p in backends.items()}
    all_tids = sorted(set().union(*[set(v.keys()) for v in indices.values()]))
    rows = []
    for tid in all_tids:
        fps = {b: indices[b].get(tid) for b in backends}
        present = [fps[b] for b in backends if fps[b] is not None]
        if len(present) != len(backends):
            equiv = False
        elif not present:
            equiv = True
        else:
            equiv = len(set(present)) == 1
        rows.append({"test_id": tid, "fingerprints": fps, "equivalent": equiv})
    root = Path.cwd()
    corpus_path = root / "corpus" / "corpus.pcap"
    prog = os.environ.get("PROG", "pass_drop")
    obj_path = root / "build" / f"prog_{prog}.o"
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backends": list(backends.keys()),
        "cases": rows,
        "divergence_count": sum(1 for r in rows if not r["equivalent"]),
    }
    cs = file_sha256(corpus_path)
    ps = file_sha256(obj_path)
    if cs:
        manifest["corpus_sha256"] = cs
    if ps:
        manifest["program_sha256"] = ps
    return manifest


def main() -> None:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <out.json> <backend>:<pcap> ...", file=sys.stderr)
        sys.exit(2)
    out = Path(sys.argv[1])
    backends = {}
    for spec in sys.argv[2:]:
        name, p = spec.split(":", 1)
        backends[name] = Path(p)
    manifest = compare(backends)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {out} ({manifest['divergence_count']} divergences, {len(manifest['cases'])} cases)")


if __name__ == "__main__":
    main()
