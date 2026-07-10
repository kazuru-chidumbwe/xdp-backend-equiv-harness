---
title: "Native vs. Generic XDP: A Differential Test Harness (AF_XDP Phase 2)"
published: false
description: Native and generic SKB XDP are not the same runtime. This post ships an open harness blueprint for comparing them on a deterministic corpus — virtio smoke gate today, wired NIC and AF_XDP observation in later phases.
tags: linux, networking, ebpf, security
canonical_url: https://dev.to/PLACEHOLDER
---

You load one `.o` file. You attach it with `ip link set dev eth0 xdp obj prog.o`. In our lab, the same program might run in **native XDP** on a loop-cabled wired port, in **generic (SKB) XDP** on a VM virtio link without driver offload, or behind **AF_XDP** after a redirect to userspace. The BPF bytecode is the same. The observable packet fate often is not.

**Scope of this post:** methodology and reproduction for **native vs. generic XDP** on one program (`prog_pass_drop`) and one profile (virtio/veth smoke gate). **AF_XDP** is described as phase-2 architecture only — not measured here. Bare-metal NIC manifests and multi-program sweeps are deferred to a follow-up results write-up.

A common operational assumption is: *if the verifier accepted it, behaviour is portable*. Conformance testing usually stops at load time. **Differential testing** asks a stricter question: given identical input packets, do all backends produce the same disposition, post-hook bytes, and metadata?

A firewall or rate-limiter program validated only under native XDP can silently fall back to generic mode on an unsupported driver, a veth port, or after reload — same bytecode, different disposition, often no error line. That silent-fallback shape is why we built this harness.

## Native, generic, and AF_XDP are not the same runtime

**Native XDP** runs at the driver ingress hook, before `sk_buff` allocation. Programs see early drops, frame layout as presented by the driver, and (when supported) the metadata surface the program expects.

**Generic XDP** (`xdpgeneric`, SKB mode) runs later on the `netif_receive_skb` path. No driver XDP support is required. That path uses a different packet representation: with **RX VLAN offload enabled**, tags may be stripped before the program sees the frame (native XDP on the same NIC can show the same behaviour — this is an offload confound, not a backend constant). Fragments and `data_meta` availability can also differ.

**AF_XDP** is not a parallel in-kernel backend. It is a **redirect target**: native XDP can send matching frames to an AF_XDP socket; userspace may complete policy there. We treat it as a third observation point because stacks such as Cilium, Katran, and custom filters routinely split work across kernel and userspace. Equivalence claims that ignore that boundary are incomplete — but this repository does not sweep AF_XDP yet.

Hardware SmartNIC offload is **out of scope** for this harness. Reproducing Netronome or signed-firmware offload across independent labs is not practical for a portable artifact.

## VM plus wired NIC — use both

| Layer | VM (virtio / veth) | Wired NIC (mlx5, i40e, igc, tg3, …) |
| --- | --- | --- |
| Native vs generic XDP | virtio_net on 6.8+ | driver-specific behaviour |
| Corpus + comparator + manifest | portable reproduce path | same harness |
| Driver-specific quirks | virtio only | mlx5, i40e, tg3, etc. |
| PCI passthrough to VM | real driver inside guest | supported |
| Hardware offload | out of scope | out of scope |

**VM profile:** pinned kernel (6.8.x), virtio or PCI-passthrough NIC, `make sweep-virtio` → manifest. Anyone with a Linux VM can reproduce the harness loop.

**Wired NIC profile:** VLAN edge cases, checksum handling, metadata differences visible on physical ports. Store **two manifest files**: `run_manifest_virtio_vm_*.json` and `run_manifest_baremetal_nic_*.json`. Do not merge them without labeling the profile.

Lab hardware that covers common splits: Mellanox ConnectX (`mlx5`) and Intel X710 (`i40e`). A single Intel I350-class port (`igb` / `igc`) is enough for an initial wired run. PCI passthrough into a VM preserves driver semantics with snapshot rollback.

## What we measure

For each corpus packet, paired by embedded test ID:

| Check | Capture | Equivalent when |
| --- | --- | --- |
| Disposition | `xdpdump` / BPF action trace | `PASS` / `DROP` / `TX` / `REDIRECT` match |
| Post-XDP bytes | `xdpdump` at the hook | Bitwise match on masked regions |
| Metadata | `ingress_ifindex`, `data_meta` | Match where defined; Class A if generic NULL is documented |
| Checksums | L3/L4 in captured frame | Divergence flagged — offload disabled for measurement |

Divergence classes:

- **Class A** — documented backend difference  
- **Class B** — operator-surprising gap  
- **Class C** — harness or capture artifact (uncontrolled offload, wrong inject path, etc.)

## Corpus and programs

Eleven deterministic Scapy cases: IPv4/IPv6 SYN, VLAN, QinQ, IPv4 fragment, ICMP, UDP zero-checksum, FIN/ACK, zero payload, MTU fill, DSCP/ECN. Each frame embeds a test ID in the payload or L4 header field.

The repository currently ships `prog_pass_drop.o` (disposition baseline). Additional programs (`prog_l3_modify`, `prog_vlan`, `prog_redirect`) are planned so each test isolates one behaviour.

## Harness architecture

```text
corpus.pcap
    │
injector (peer veth / second netns)   ← RX path; not tcpreplay TX on same iface
    │
ingress + XDP (native | generic)
    │
xdpdump → output_<backend>.pcap
    │
compare.py → run_manifest.json
```

Documented pitfalls: capture at the hook; on measurement NICs disable checksum and VLAN RX offload (`ethtool -K $NIC rx off tx off rx-vlan-offload off`); detach XDP between backend runs; include a negative-control packet that must agree on all backends.

## AF_XDP (phase 2 — not in the sweep)

The current sweep compares **native vs generic** in-kernel only. AF_XDP support will add a redirect path plus userspace observation; checksum-sensitive operations stay out of that path until the comparator can treat them consistently.

## Run it yourself

https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness

Checkout tag **`blog-x01-2026-07`** — that pin matches this post.

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07   # commit a50bf63

sudo apt-get install -y clang llvm libbpf-dev python3-scapy xdp-tools make \
  linux-tools-common linux-headers-$(uname -r)
# bpftool: linux-tools-common on Ubuntu/Debian; use package bpftool if your distro splits it

make corpus
make build
sudo make topology
sudo make sweep-virtio
```

Virtio smoke gate (same sweep, explicit pass/fail):

```bash
bash scripts/smoke.sh
```

Wired NIC when loop-cabled (single entry point — topology, carrier check, offload disable, sweep):

```bash
export NIC=ens16f0
export INJ_IFACE=ens16f1
sudo make baremetal-sweep
```

Equivalent: `sudo bash scripts/baremetal-sweep.sh` with the same env vars. `make sweep-nic` is an alias to `baremetal-sweep`.

See [`docs/BAREMETAL-LAB.md`](https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness/blob/main/docs/BAREMETAL-LAB.md) for PCI passthrough, default lab IPs (`192.168.0.5` / `192.168.0.6`), and carrier checks.

Outputs: `manifests/run_manifest_<profile>_<prog>.json`.

## Harness validation (smoke gate — not a results claim)

| Check | Outcome |
| --- | --- |
| **virtio_vm** smoke (`prog_pass_drop`, veth topology) | Harness loop completes on kernel 6.8 (lab); comparator runs end-to-end |
| **baremetal_nic** | Not run yet — requires loop-cabled wired ports; WiFi out of scope |

The virtio run is a **reproducibility gate** (n=1 program × 1 profile). It does not establish that native and generic XDP agree in general, on bare metal, or for programs beyond `prog_pass_drop`. Pinned divergence manifests for additional profiles and programs will ship in a separate results post.

WiFi interfaces are not supported as an observation point in this harness; wired ethernet is required for the bare-metal profile.

---

Further reading: [xdp-tools / xdpdump](https://github.com/xdp-project/xdp-tools) · [AF_XDP](https://www.kernel.org/doc/html/latest/networking/af_xdp.html)

*Synthetic lab traffic only. No production traffic. Results tagged per NIC model and kernel version.*
