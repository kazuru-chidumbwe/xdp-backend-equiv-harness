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
print(f"SMOKE OK — {n} cases, divergences={d.get('divergence_count')}")
PY
