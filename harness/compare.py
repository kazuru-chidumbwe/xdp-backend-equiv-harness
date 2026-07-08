#!/usr/bin/env python3
"""Pair captures by embedded test ID; emit divergence manifest."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scapy.all import rdpcap, Raw
except ImportError:
    print("scapy required", file=sys.stderr)
    sys.exit(1)


def extract_tid(pkt) -> int | None:
    if Raw in pkt:
        payload = bytes(pkt[Raw].load)
        if len(payload) >= 2:
            return int.from_bytes(payload[-2:], "big")
    return None


def packet_fingerprint(pkt) -> str:
    return hashlib.sha256(bytes(pkt)).hexdigest()[:16]


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
        ref = next(iter(fps.values()))
        equiv = all(v == ref for v in fps.values() if v is not None)
        rows.append({"test_id": tid, "fingerprints": fps, "equivalent": equiv})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backends": list(backends.keys()),
        "cases": rows,
        "divergence_count": sum(1 for r in rows if not r["equivalent"]),
    }


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
    print(f"Wrote {out} ({manifest['divergence_count']} divergences)")


if __name__ == "__main__":
    main()
