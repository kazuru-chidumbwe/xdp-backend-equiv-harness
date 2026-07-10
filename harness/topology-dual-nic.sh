#!/usr/bin/env bash
# Physical dual-port lab: inject in netns on NIC_INJ, XDP on NIC_XDP (loop cable between ports).
set -euo pipefail

NS_INJ="${NS_INJ:-xdpequiv-inj}"
NIC_XDP="${NIC_XDP:-${NIC:-ens16f0}}"
NIC_INJ="${NIC_INJ:-ens16f1}"

cleanup_veth() {
  ip link del veth-a 2>/dev/null || true
}

if ! ip link show "$NIC_XDP" >/dev/null 2>&1; then
  echo "XDP interface $NIC_XDP missing" >&2
  exit 1
fi
if ! ip link show "$NIC_INJ" >/dev/null 2>&1; then
  echo "Inject interface $NIC_INJ missing" >&2
  exit 1
fi

cleanup_veth
ip netns del "$NS_INJ" 2>/dev/null || true

ip link set "$NIC_XDP" up
ip netns add "$NS_INJ"
ip link set "$NIC_INJ" netns "$NS_INJ"
ip netns exec "$NS_INJ" ip link set "$NIC_INJ" up
ip netns exec "$NS_INJ" ip link set lo up

echo "Dual-NIC topology ready:"
echo "  XDP attach target: $NIC_XDP (host)"
echo "  Inject namespace:  $NS_INJ via $NIC_INJ"
echo "Cable $NIC_XDP <-> $NIC_INJ before sweep."
