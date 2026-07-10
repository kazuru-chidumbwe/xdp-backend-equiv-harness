#!/usr/bin/env bash
# Bare-metal native vs generic sweep on loop-cabled dual-port NIC.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

NIC="${NIC:-ens16f0}"
INJ_IFACE="${INJ_IFACE:-ens16f1}"
export NIC INJ_IFACE
export NIC_XDP_IP="${NIC_XDP_IP:-192.168.0.5/24}"
export NIC_INJ_IP="${NIC_INJ_IP:-192.168.0.6/24}"

command -v xdpdump >/dev/null || { echo "install xdp-tools" >&2; exit 1; }

carrier() {
  local dev="$1" ns="${2:-}"
  if [[ -n "$ns" ]]; then
    ip netns exec "$ns" cat "/sys/class/net/$dev/carrier" 2>/dev/null || echo 0
  else
    cat "/sys/class/net/$dev/carrier" 2>/dev/null || echo 0
  fi
}

make corpus
make build

bash harness/topology-dual-nic.sh

c0="$(carrier "$NIC")"
c1="$(carrier "$INJ_IFACE" xdpequiv-inj)"
if [[ "$c0" != "1" || "$c1" != "1" ]]; then
  echo "NO-CARRIER: $NIC=$c0 $INJ_IFACE(in netns)=$c1 — loop-cable ports before sweep" >&2
  exit 1
fi

ethtool -K "$NIC" rx off tx off rx-vlan-offload off 2>/dev/null || true
PROFILE=baremetal_nic bash harness/sweep.sh

python3 - <<'PY'
import json
from pathlib import Path

p = Path("manifests/run_manifest_baremetal_nic_pass_drop.json")
d = json.loads(p.read_text())
n = len(d.get("cases", []))
if n < 1:
    raise SystemExit(f"FAIL: baremetal manifest has {n} cases")
print(f"BAREMETAL OK — {n} cases, divergences={d.get('divergence_count')}, driver={d.get('driver')}")
PY
