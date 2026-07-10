#!/usr/bin/env bash
# Run native vs generic sweeps for all five blog programs on virtio/veth.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROGRAMS=(pass_drop metadata_test vlan l3_modify redirect)

make corpus
make build-all
sudo make topology

for prog in "${PROGRAMS[@]}"; do
  echo "=== sweep: $prog ==="
  sudo PROFILE=virtio_vm PROG="$prog" bash harness/sweep.sh
done

echo "=== manifests ==="
python3 - <<'PY'
import glob
import json

for path in sorted(glob.glob("manifests/run_manifest_virtio_vm_*.json")):
    data = json.load(open(path))
    name = path.split("_")[-1].replace(".json", "")
    cases = len(data.get("cases", []))
    div = data.get("divergence_count", "?")
    print(f"{name:16} cases={cases:2} divergences={div}")
PY
