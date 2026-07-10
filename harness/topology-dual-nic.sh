#!/usr/bin/env bash
# Physical dual-port lab: inject in netns on NIC_INJ, XDP on NIC_XDP (loop cable between ports).
set -euo pipefail

NS_INJ="${NS_INJ:-xdpequiv-inj}"
NIC_XDP="${NIC_XDP:-${NIC:-ens16f0}}"
NIC_INJ="${NIC_INJ:-ens16f1}"
NIC_XDP_IP="${NIC_XDP_IP:-192.168.0.5/24}"
NIC_INJ_IP="${NIC_INJ_IP:-192.168.0.6/24}"

cleanup_veth() {
  ip link del veth-a 2>/dev/null || true
}

# Return inject NIC to host if a prior netns run left it there.
ip netns del "$NS_INJ" 2>/dev/null || true

if ! ip link show "$NIC_XDP" >/dev/null 2>&1; then
  echo "XDP interface $NIC_XDP missing" >&2
  exit 1
fi
if ! ip link show "$NIC_INJ" >/dev/null 2>&1; then
  echo "Inject interface $NIC_INJ missing on host (already in netns?)" >&2
  exit 1
fi

cleanup_veth

ip link set "$NIC_XDP" up
ip link set "$NIC_INJ" up
sleep 1

ip addr flush dev "$NIC_XDP" 2>/dev/null || true
ip addr add "$NIC_XDP_IP" dev "$NIC_XDP" 2>/dev/null || true

ip netns add "$NS_INJ"
ip link set "$NIC_INJ" netns "$NS_INJ"
ip netns exec "$NS_INJ" ip link set "$NIC_INJ" up
ip netns exec "$NS_INJ" ip link set lo up
ip netns exec "$NS_INJ" ip addr flush dev "$NIC_INJ" 2>/dev/null || true
ip netns exec "$NS_INJ" ip addr add "$NIC_INJ_IP" dev "$NIC_INJ" 2>/dev/null || true

carrier_ok() {
  local dev="$1"
  local ns="${2:-}"
  local c
  if [[ -n "$ns" ]]; then
    c="$(ip netns exec "$ns" cat "/sys/class/net/$dev/carrier" 2>/dev/null || echo 0)"
  else
    c="$(cat "/sys/class/net/$dev/carrier" 2>/dev/null || echo 0)"
  fi
  [[ "$c" == "1" ]]
}

echo "Dual-NIC topology ready:"
echo "  XDP attach target: $NIC_XDP (host) $NIC_XDP_IP"
echo "  Inject namespace:  $NS_INJ via $NIC_INJ $NIC_INJ_IP"
if carrier_ok "$NIC_XDP" && carrier_ok "$NIC_INJ" "$NS_INJ"; then
  echo "  Link: carrier detected on both ports."
else
  echo "  Link: NO-CARRIER on one or both ports — loop-cable $NIC_XDP <-> $NIC_INJ (IPs alone do not create link)."
fi
