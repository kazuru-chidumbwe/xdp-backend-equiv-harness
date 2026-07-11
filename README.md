# XDP Backend Equivalence Harness

Differential test harness for **native XDP** and **generic (SKB) XDP**. Identical deterministic packet corpus, same BPF object, compare post-hook frame fingerprints across backends.

**Lab only** — no production traffic. Synthetic corpus via Scapy.

## Research question

> Does a fixed XDP program produce identical observable post-hook frame bytes across native XDP and generic XDP under identical input traffic?

## Profiles

| Profile | Purpose |
| --- | --- |
| **virtio_vm** | Portable artifact — reproducible on any Linux VM / veth lab |
| **baremetal_nic** | Physical wired NIC pair — see [`docs/BAREMETAL-LAB.md`](docs/BAREMETAL-LAB.md) |

See [`docs/VM-VS-BAREMETAL.md`](docs/VM-VS-BAREMETAL.md).

## Quick start (Linux lab host)

Requirements: Linux 6.6+ (6.8+ recommended), `clang`, `llvm`, `libbpf-dev`, `bpftool`, `python3`, `scapy`, `xdp-tools` (`xdpdump`).

```bash
make deps
make corpus
sudo make topology      # veth + netns injector
make build
sudo make sweep-virtio  # native + generic on lab veth/virtio (one program)
bash scripts/sweep-all-virtio.sh  # all five blog programs
```

Outputs: `manifests/run_manifest_*.json`, `captures/output_*.pcap`.

**Bare-metal rerun** (loop-cabled PCI passthrough): [`docs/BAREMETAL-LAB.md`](docs/BAREMETAL-LAB.md) · `sudo NIC=ens16f0 make baremetal-sweep`

For bare metal with a real NIC (after loop cable — see [`docs/BAREMETAL-LAB.md`](docs/BAREMETAL-LAB.md)):

```bash
export NIC=eth0 INJ_IFACE=eth1
sudo make baremetal-sweep
```

## Layout

```
corpus/           generate_corpus.py → corpus.pcap
programs/         BPF C sources (pass_drop, l3_modify, vlan, redirect)
harness/          topology, inject, compare
schemas/          manifest JSON schema
docs/             architecture, VM vs bare metal, pitfalls
vm/               Vagrant box (pinned kernel, virtio)
manifests/        run output (gitignored except examples)
```

## Blog reproduction anchor (X01)

Dev.to essay: *A Differential Test Harness for Native vs. Generic XDP* — pin tag **`blog-x01-2026-07`**.

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07
```

Full draft: [`docs/DEVTO-BLOG.md`](docs/DEVTO-BLOG.md)

Methodological ancestor: [emrtd-differential-harness](https://github.com/kazuru-chidumbwe/emrtd-differential-harness)

## License

MIT
