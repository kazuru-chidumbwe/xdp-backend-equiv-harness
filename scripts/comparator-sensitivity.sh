#!/usr/bin/env bash
# Comparator validation: self-test (required) + live backend probes (informational).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PATH="/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

echo "=== comparator self-test (synthetic pcaps) ==="
python3 scripts/comparator-selftest.py
python3 scripts/comparator-missing-tid-test.py
python3 scripts/comparator-blindspot-demo.py

if ! command -v xdpdump >/dev/null; then
  echo "SKIP live probes: xdpdump not installed"
  exit 0
fi

for probe in metadata_test vlan_probe; do
  echo "=== live backend probe: prog_${probe} ==="
  make corpus
  make build PROG="$probe"
  sudo make topology
  sudo PROG="$probe" PROFILE=virtio_vm bash harness/sweep.sh
  python3 - <<PY
import json
from pathlib import Path
p = Path("manifests/run_manifest_virtio_vm_${probe}.json")
d = json.loads(p.read_text())
print(f"  {p.name}: cases={len(d.get('cases',[]))} divergences={d.get('divergence_count')}")
PY
done

echo "VALIDATE OK — comparator self-test passed; live probe manifests written"
