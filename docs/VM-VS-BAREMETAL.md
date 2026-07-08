# VM vs bare-metal NIC

## What a VM can simulate

- **Native XDP vs generic XDP** on `virtio_net` (kernel 5.10+, better on 6.x)
- Full harness loop: corpus → inject on peer veth → capture at XDP hook → compare
- AF_XDP phase-2 path with veth redirect + minimal userspace echo
- Bit-exact **artifact evaluation** for reviewers and dev.to readers

## What a VM cannot simulate

- Mellanox mlx5 vs Intel i40e driver-specific metadata behaviour
- Hardware XDP offload or SmartNIC programming
- Bond/team upper-device edge cases on physical uplinks
- NIC firmware checksum behaviour under load

## Recommended dual-track workflow

1. **Develop** on VM or veth — fast iteration, CI-friendly.
2. **Publish primary results** from bare-metal NIC with pinned `uname -r`, driver version, `ethtool -i`.
3. **Ship both manifests:**
   - `manifests/results_virtio_vm.json`
   - `manifests/results_baremetal_<driver>_<kernel>.json`
4. Never merge into one equivalence claim without labeling the profile.

## Suggested real NICs (lab)

| NIC family | Driver | Notes |
| --- | --- | --- |
| Intel I350/I210 | `igc` / `igb` | Cheap, common |
| Intel X710 | `i40e` | Data-center staple |
| Mellanox ConnectX-4/5 | `mlx5` | Native XDP mature |

One Intel + one Mellanox covers most operator fleet splits. A single $50 Intel NIC is enough for v1 blog tag.

## VM setup

See [`vm/README.md`](../vm/README.md). Pin kernel in Vagrant box; enable nested virt if testing native XDP in QEMU.
