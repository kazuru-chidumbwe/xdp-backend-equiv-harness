# XDP Backend Equivalence Harness

Differential test harness for **native XDP**, **generic (SKB) XDP**, and (phase 2) **AF_XDP** redirect paths. Identical deterministic packet corpus, same BPF object, compare disposition + post-hook bytes + metadata across backends.

**Lab only** — no production traffic. Synthetic corpus via Scapy.

## Research question

> Does a fixed XDP program produce identical observable packet-processing outcomes across native XDP, generic XDP, and AF_XDP under identical input traffic?

## Reproduction strategy: VM + real NIC

| Profile | Purpose |
| --- | --- |
| **virtio VM** | Portable artifact — anyone with a laptop reproduces manifest structure |
| **Bare-metal NIC** | Primary findings — mlx5, i40e, igc, etc. |

See [`docs/VM-VS-BAREMETAL.md`](docs/VM-VS-BAREMETAL.md).

## Quick start (Linux lab host)

Requirements: Linux 6.6+ (6.8+ recommended), `clang`, `llvm`, `libbpf-dev`, `bpftool`, `python3`, `scapy`, `xdp-tools` (`xdpdump`).

```bash
make deps
make corpus
sudo make topology      # veth + netns injector
make build
sudo make sweep-virtio  # native + generic on lab veth/virtio
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

Dev.to essay: *Same XDP Program, Three Backends…* — pin tag **`blog-x01-2026-07`**.

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07
```

Full draft: [`docs/DEVTO-BLOG.md`](docs/DEVTO-BLOG.md)

Methodological ancestor: [emrtd-differential-harness](https://github.com/kazuru-chidumbwe/emrtd-differential-harness)

## License

MIT
