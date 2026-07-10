#!/usr/bin/env bash
# Native vs generic XDP sweep on veth-b (or NIC= override).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IFACE="${NIC:-veth-b}"
NS_INJ="${NS_INJ:-xdpequiv-inj}"
INJ_IFACE="${INJ_IFACE:-veth-a}"
PROG="${PROG:-pass_drop}"
OBJ="build/prog_${PROG}.o"
SECTION="xdp"
PROFILE="${PROFILE:-virtio_vm}"
CAPTURE_DIR="captures"
MANIFEST_DIR="manifests"

mkdir -p "$CAPTURE_DIR" "$MANIFEST_DIR"

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

detach_xdp() {
  ip link set dev "$IFACE" xdp off 2>/dev/null || true
  ip link set dev "$IFACE" xdpgeneric off 2>/dev/null || true
}

load_backend() {
  local mode="$1"
  detach_xdp
  if [[ "$mode" == "native" ]]; then
    ip link set dev "$IFACE" xdp obj "$OBJ" sec "$SECTION"
  else
    ip link set dev "$IFACE" xdpgeneric obj "$OBJ" sec "$SECTION"
  fi
}

capture_backend() {
  local mode="$1"
  local out="$CAPTURE_DIR/output_${mode}_${PROG}.pcap"
  load_backend "$mode"
  if ! command -v xdpdump >/dev/null 2>&1; then
    echo "xdpdump not found — install xdp-tools" >&2
    exit 1
  fi
  timeout 8 xdpdump -i "$IFACE" -w "$out" &
  local xdppid=$!
  sleep 0.5
  ip netns exec "$NS_INJ" python3 harness/inject.py corpus/corpus.pcap "$INJ_IFACE"
  sleep 1.5
  kill "$xdppid" 2>/dev/null || true
  wait "$xdppid" 2>/dev/null || true
  detach_xdp
}

export PROG="${PROG:-pass_drop}"
make corpus
make build PROG="$PROG"

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "Interface $IFACE missing — run: sudo make topology" >&2
  exit 1
fi

if [[ -n "${NIC:-}" ]]; then
  ethtool -K "$IFACE" rx off tx off rx-vlan-offload off 2>/dev/null || true
  PROFILE="baremetal_nic"
fi

capture_backend native
capture_backend generic

MANIFEST="$MANIFEST_DIR/run_manifest_${PROFILE}_${PROG}.json"
PROG="$PROG" python3 harness/compare.py "$MANIFEST" \
  "native:$CAPTURE_DIR/output_native_${PROG}.pcap" \
  "generic:$CAPTURE_DIR/output_generic_${PROG}.pcap"

COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
python3 - "$MANIFEST" "$PROFILE" "$COMMIT" "$IFACE" <<'PY'
import json, platform, subprocess, sys
from pathlib import Path

path = Path(sys.argv[1])
profile = sys.argv[2]
commit = sys.argv[3]
iface = sys.argv[4]
data = json.loads(path.read_text())
data["profile"] = profile
data["kernel"] = platform.release()
data["harness_commit"] = commit
try:
    out = subprocess.check_output(["ethtool", "-i", iface], text=True)
    for line in out.splitlines():
        if line.startswith("driver:"):
            data["driver"] = line.split(":", 1)[1].strip()
        if line.startswith("bus-info:"):
            data["nic_model"] = line.split(":", 1)[1].strip()
except Exception:
    data["driver"] = "unknown"
path.write_text(json.dumps(data, indent=2) + "\n")
PY

echo "Sweep complete: $MANIFEST"
