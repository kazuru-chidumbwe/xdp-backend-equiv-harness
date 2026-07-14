#!/usr/bin/env python3
"""Pair captures by embedded test ID; emit divergence manifest."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from scapy.all import ICMP, Ether, Raw, TCP, UDP, rdpcap
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


# xdpdump 1.4.x reports the XDP action in its stdout text (e.g.
# `xdp_prog()@exit[PASS]`), NOT in the pcapng frame written by `-w`. To recover
# the verdict we parse `xdpdump -x` text: a header line per capture point,
# followed by a hex dump of the frame. We pair the verdict from each @exit
# record with the test id embedded in the frame bytes.
_VERDICT_HDR_RE = re.compile(
    r"^\d+\.\d+:\s+\S+?\(\)@(entry|exit)(?:\[([A-Z_]+)\])?:.*\bid (\d+)\b"
)
_VERDICT_HEX_RE = re.compile(r"^\s*0x[0-9a-fA-F]+:\s+(.*)$")


def parse_verdict_log(path: Path) -> dict[int, str]:
    """Parse `xdpdump -x` text output into {test_id: exit_verdict}.

    Returns only records that carry an in-range test id and an @exit verdict.
    Frame bytes are recovered from the hex dump; the test id is read with the
    same extract_tid() used for byte pairing, so verdict rows key identically to
    fingerprint rows.
    """
    records: dict[int, dict[str, tuple]] = {}
    cur = None
    hexbuf: list[str] = []

    def flush() -> None:
        if cur is not None:
            rid, hook, action = cur
            frame = bytes.fromhex("".join(hexbuf)) if hexbuf else b""
            records.setdefault(rid, {})[hook] = (action, frame)

    with path.open("r", errors="replace") as fh:
        for line in fh:
            m = _VERDICT_HDR_RE.match(line)
            if m:
                flush()
                hexbuf = []
                cur = (int(m.group(3)), m.group(1), m.group(2))
                continue
            hm = _VERDICT_HEX_RE.match(line)
            if hm and cur is not None:
                # hex column is separated from the ASCII column by 2+ spaces
                hexpart = re.split(r"\s{2,}", hm.group(1).rstrip(), maxsplit=1)[0]
                hexbuf.append(re.sub(r"[^0-9a-fA-F]", "", hexpart))
        flush()

    verdicts: dict[int, str] = {}
    for _rid, hooks in records.items():
        entry = hooks.get("entry")
        exit_ = hooks.get("exit")
        if exit_ is None or exit_[0] is None:
            continue
        frame = (entry or exit_)[1]
        if len(frame) < 14:
            continue
        try:
            tid = extract_tid(Ether(frame))
        except Exception:
            tid = None
        if tid is not None:
            verdicts[tid] = exit_[0]
    return verdicts


def compare(
    backends: dict[str, Path],
    verdicts: dict[str, dict[int, str]] | None = None,
) -> dict:
    indices = {name: load_index(p) for name, p in backends.items()}
    all_tids = sorted(set().union(*[set(v.keys()) for v in indices.values()]))
    have_verdicts = bool(verdicts)
    rows = []
    verdict_div = 0
    for tid in all_tids:
        fps = {b: indices[b].get(tid) for b in backends}
        present = [fps[b] for b in backends if fps[b] is not None]
        if len(present) != len(backends):
            equiv = False
        elif not present:
            equiv = True
        else:
            equiv = len(set(present)) == 1
        row = {"test_id": tid, "fingerprints": fps, "equivalent": equiv}
        if have_verdicts:
            vd = {b: verdicts.get(b, {}).get(tid) for b in backends}
            present_v = [v for v in vd.values() if v is not None]
            vmatch = len(present_v) == len(backends) and len(set(present_v)) == 1
            row["verdict"] = vd
            row["verdict_match"] = vmatch
            if not vmatch:
                verdict_div += 1
        rows.append(row)
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
    if have_verdicts:
        # Independent of divergence_count (frame bytes); verdict is the XDP action.
        manifest["verdict_divergence_count"] = verdict_div
    cs = file_sha256(corpus_path)
    ps = file_sha256(obj_path)
    if cs:
        manifest["corpus_sha256"] = cs
    if ps:
        manifest["program_sha256"] = ps
    return manifest


def main() -> None:
    args = sys.argv[1:]
    positional: list[str] = []
    verdict_specs: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--verdict":
            i += 1
            if i >= len(args):
                print("--verdict requires <backend>:<xdpdump-x-log>", file=sys.stderr)
                sys.exit(2)
            verdict_specs.append(args[i])
        else:
            positional.append(args[i])
        i += 1
    if len(positional) < 2:
        print(
            f"usage: {sys.argv[0]} <out.json> <backend>:<pcap> ... "
            f"[--verdict <backend>:<xdpdump-x-log> ...]",
            file=sys.stderr,
        )
        sys.exit(2)
    out = Path(positional[0])
    backends = {}
    for spec in positional[1:]:
        name, p = spec.split(":", 1)
        backends[name] = Path(p)
    verdicts: dict[str, dict[int, str]] | None = None
    if verdict_specs:
        verdicts = {}
        for spec in verdict_specs:
            name, p = spec.split(":", 1)
            verdicts[name] = parse_verdict_log(Path(p))
    manifest = compare(backends, verdicts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    summary = f"{manifest['divergence_count']} divergences, {len(manifest['cases'])} cases"
    if "verdict_divergence_count" in manifest:
        summary += f", {manifest['verdict_divergence_count']} verdict divergences"
    print(f"Wrote {out} ({summary})")


if __name__ == "__main__":
    main()
