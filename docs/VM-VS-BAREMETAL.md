# Experimental profiles

This repository ships two measurement profiles. Label manifests by `profile`; never merge results across profiles.

## virtio_vm

- **Topology:** `veth-a` / `veth-b` + netns `xdpequiv-inj` (`make topology`)
- **Hardware:** Any Linux host or VM with `virtio_net` or veth
- **Entry point:** `bash scripts/smoke.sh` or `bash scripts/sweep-all-virtio.sh`
- **Pinned results:** `manifests/run_manifest_virtio_vm_*.json`

## baremetal_nic

- **Topology:** loop-cabled dual wired port — XDP on `NIC`, inject on `INJ_IFACE` in netns (`make baremetal-sweep`)
- **Hardware:** Wired Ethernet only (`igc`, `i40e`, `mlx5`, `tg3`, …). **802.11 / `wlan0` is not supported.**
- **Entry point:** `sudo NIC=… INJ_IFACE=… make baremetal-sweep`
- **Runbook:** [`BAREMETAL-LAB.md`](BAREMETAL-LAB.md)
- **Output:** `manifests/run_manifest_baremetal_nic_<program>.json` when carrier is up

## VM setup

See [`vm/README.md`](../vm/README.md). Pin kernel in the Vagrant box; manifest `profile` must be `virtio_vm`.
