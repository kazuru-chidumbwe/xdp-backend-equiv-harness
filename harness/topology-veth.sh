#!/usr/bin/env bash
# veth lab topology: inject on veth-a peer, XDP on veth-b
set -euo pipefail

NS_INJ="xdpequiv-inj"
VETH_A="veth-a"
VETH_B="veth-b"
ADDR_A="10.200.0.1/24"
ADDR_B="10.200.0.2/24"

cleanup() {
  ip link del "$VETH_A" 2>/dev/null || true
  ip netns del "$NS_INJ" 2>/dev/null || true
}
trap cleanup EXIT

cleanup
ip link add "$VETH_A" type veth peer name "$VETH_B"
ip addr add "$ADDR_B" dev "$VETH_B"
ip link set "$VETH_B" up
ip link set "$VETH_A" up

ip netns add "$NS_INJ"
ip link set "$VETH_A" netns "$NS_INJ"
ip netns exec "$NS_INJ" ip addr add "$ADDR_A" dev "$VETH_A"
ip netns exec "$NS_INJ" ip link set "$VETH_A" up
ip netns exec "$NS_INJ" ip link set lo up

echo "Topology ready:"
echo "  XDP attach target: $VETH_B (host)"
echo "  Inject namespace:  $NS_INJ via $VETH_A"
echo "Run: ip netns exec $NS_INJ python3 harness/inject.py corpus/corpus.pcap"
