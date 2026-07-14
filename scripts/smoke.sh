#!/usr/bin/env bash
# Virtio/veth reproduction smoke (X01a publish gate).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v xdpdump >/dev/null || { echo "xdpdump required (xdp-tools package)" >&2; exit 1; }
command -v clang >/dev/null || { echo "clang required" >&2; exit 1; }

make corpus
make build
sudo make topology
sudo PROFILE=virtio_vm bash harness/sweep.sh

python3 - <<'PY'
import json
from pathlib import Path

p = Path("manifests/run_manifest_virtio_vm_pass_drop.json")
d = json.loads(p.read_text())
n = len(d.get("cases", []))
if n < 10:
    raise SystemExit(f"FAIL: expected >=10 cases, got {n}")

byte_div = d.get("divergence_count")
if byte_div != 0:
    raise SystemExit(f"FAIL: byte divergences on pass_drop smoke, got {byte_div}")

# Verdict agreement is required: the byte check alone is blind to DROP vs PASS
# on a non-mutating program, so the smoke gate would otherwise pass even if the
# backends disagreed on disposition.
vdiv = d.get("verdict_divergence_count")
if vdiv is None:
    raise SystemExit("FAIL: verdict not instrumented (run sweep.sh with --verdict logs)")
if vdiv != 0:
    raise SystemExit(f"FAIL: native/generic verdict mismatch on pass_drop, got {vdiv}")

verdicts = sorted({v for c in d["cases"] for v in (c.get("verdict") or {}).values() if v})
print(
    f"SMOKE OK — {n} cases, byte_divergences={byte_div}, "
    f"verdict_divergences={vdiv}, verdicts_seen={verdicts}"
)
PY
