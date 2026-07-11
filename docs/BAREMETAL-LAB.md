# Bare-metal lab rerun (BCM5720 / dual-port)

Use this when the virtio smoke passed but **physical ports had NO-CARRIER** (no loop cable). Clone on a host or VM that has **link** on both passed-through ports.

## Prerequisites

- Linux **6.6+** (6.8+ tested)
- Packages: `clang llvm libbpf-dev python3-scapy xdp-tools make`
- Kernel headers: `linux-headers-$(uname -r)`
- Two-port wired NIC passed through (lab: Broadcom BCM5720 `tg3` as `ens16f0` + `ens16f1`)
- **Loop cable** between the two RJ45 ports (or switch hairpin)

## Quick run

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07   # or main

sudo apt-get install -y clang llvm libbpf-dev python3-scapy xdp-tools make \
  linux-tools-common linux-headers-$(uname -r)

# Virtio / veth gate (always run first)
bash scripts/smoke.sh

# Bare-metal (adjust NIC names if different)
export NIC=ens16f0
export INJ_IFACE=ens16f1
export NIC_XDP_IP=192.168.0.5/24
export NIC_INJ_IP=192.168.0.6/24

sudo bash scripts/baremetal-sweep.sh
```

Or one Makefile target after cable + carrier check:

```bash
sudo NIC=ens16f0 INJ_IFACE=ens16f1 make baremetal-sweep
```

(`make sweep-nic` is an alias to the same target.)

## Verify link before sweep

```bash
ip link set ens16f0 up
ip link set ens16f1 up
cat /sys/class/net/ens16f0/carrier    # must be 1
# after topology-dual-nic.sh:
sudo ip netns exec xdpequiv-inj cat /sys/class/net/ens16f1/carrier   # must be 1
```

**IPs do not create carrier.** `192.168.0.5/24` (XDP port) and `192.168.0.6/24` (inject port) are assigned by `topology-dual-nic.sh` for lab convenience; you still need a physical link.

## Expected output

- `manifests/run_manifest_baremetal_nic_pass_drop.json`
- `cases` length **> 0** when carrier is up (target: 11 like virtio)
- `driver`: e.g. `tg3`, `igc`, `i40e`, `mlx5_core`

Never merge bare-metal and virtio manifests without labeling `profile`.

## WiFi

802.11 / `wlan0` is not supported — use a wired NIC pair (see [`BAREMETAL-LAB.md`](BAREMETAL-LAB.md)).
