---
title: "Same XDP Program, Three Backends: Building a Differential Tester for Native, Generic, and AF_XDP"
published: false
description: XDP is marketed as run-anywhere kernel bypass. Native, generic SKB, and AF_XDP paths disagree more often than operators admit. Here's the harness we're open-sourcing — VM for reproducibility, real NIC for truth.
tags: linux, networking, ebpf, devops, security
canonical_url: https://dev.to/PLACEHOLDER
---

You load one `.o` file. You attach it with `ip link set dev eth0 xdp obj prog.o`. In production, that program might run in **native XDP** on a Mellanox uplink, in **generic (SKB) XDP** on a VM NIC that has no driver offload, or behind **AF_XDP** after a redirect to userspace. The BPF bytecode is the same. The observable packet fate often is not.

I have shipped both layers on sovereign bare-metal platforms — TC microsegmentation on guest interfaces and custom XDP on bonded uplinks — and the operational assumption is always the same: *if the verifier accepted it, behaviour is portable*. That assumption is rarely tested systematically. Conformance means the program loads. Differential testing means: **given identical input packets, do all backends produce identical disposition, post-hook bytes, and metadata?**

After a differential harness for open-source eMRTD readers ([case study](https://dev.to/kazuru_73322ef9a7d6ed2b18/differential-testing-revealed-what-conformance-testing-missed-a-case-study-with-open-source-emrtd-1nie)), the next obvious move was kernel datapath: fix the program, fix the corpus, swap "library" for "XDP backend," swap APDU traces for packet captures. This post is Part 1 — the blueprint, the artifact, and the VM-plus-NIC reproduction strategy — before the divergence taxonomy table is frozen.

## Native, generic, and AF_XDP are not the same runtime

**Native XDP** runs at the driver ingress hook, before `sk_buff` allocation. You get early drops, real frame layout, and (when the driver supports it) the metadata surface your program expects.

**Generic XDP** (`xdpgeneric`, SKB mode) runs later — on the `netif_receive_skb` path. No driver XDP support required. That convenience buys you a different packet representation: VLAN tags may already be stripped, fragments may look different, `data_meta` may be NULL when your native run had headroom.

**AF_XDP** is not a fourth execution engine in parallel to those two. It is a **redirect target**: native XDP sends matching frames to an AF_XDP socket; userspace completes the policy. We include it as a third *observation point* because production stacks (Cilium, Katran, custom filters) routinely split work across kernel and userspace. Any equivalence claim that ignores that boundary is incomplete.

We are **not** claiming hardware SmartNIC offload in this study. Reproducing Netronome or signed-firmware offload across labs is a reproducibility dead end. That stays future work.

## VM plus real NIC — use both

**A VM is enough for the reproducible artifact. A real NIC is enough for production-grade claims.**

| Layer | VM (virtio / veth) | Real NIC (mlx5, i40e, igc) |
| --- | --- | --- |
| Native vs generic XDP | virtio_net on 6.8+ | primary findings |
| Corpus + comparator | bit-exact for strangers | same harness |
| Driver quirks | virtio only | mlx5 vs i40e divergence |
| PCI passthrough | real mlx5/i40e inside VM | recommended lab setup |

**VM role:** pinned kernel, virtio or passthrough NIC, `make sweep` → `run_manifest.json`.

**Real NIC role:** VLAN, checksum, and metadata divergences operators hit on uplinks. Publish separate manifests: `results_virtio_vm.json` and `results_baremetal_<driver>.json`.

Recommended hardware: **Mellanox ConnectX-4/5** (`mlx5`) + **Intel X710** (`i40e`). Minimum: one **Intel I350** (`igb`). See [`docs/VM-VS-BAREMETAL.md`](VM-VS-BAREMETAL.md).

## What we measure

For each corpus packet (paired by embedded test ID):

| Check | Equivalent when |
| --- | --- |
| Disposition | PASS / DROP / TX / REDIRECT match |
| Post-XDP bytes | Bitwise match on masked regions |
| Metadata | Match where defined; Class A if SKB NULL is expected |
| Checksums | Flag divergence (offload disabled on measure iface) |

**Class A** — documented backend difference. **Class B** — operator-surprising gap. **Class C** — harness bug.

## Corpus and programs

Eleven deterministic Scapy-generated cases: IPv4/IPv6 SYN, VLAN, QinQ, fragment, ICMP, UDP zero-checksum, FIN/ACK, zero payload, MTU fill, DSCP/ECN.

Program family (phase 1 ships `prog_pass_drop`):

- `prog_pass_drop.o` — disposition baseline  
- `prog_l3_modify.o`, `prog_vlan.o`, `prog_redirect.o` — coming next  

## Harness sketch

```text
corpus.pcap → inject on peer veth (RX!) → XDP native|generic → xdpdump → compare.py
```

Pitfalls: capture at hook (not egress-only tcpdump), disable checksum offload, detach XDP between runs.

## Run it yourself

https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07
make deps
make corpus
sudo make topology
sudo make sweep-virtio
```

Bare metal or PCI-passthrough NIC:

```bash
export NIC=eth0
sudo ethtool -K $NIC rx off tx off
sudo make sweep-nic
```

Phase 1 is **native vs generic** only. AF_XDP is phase 2.

## Closing

XDP sold us compile once, attach anywhere. Fleet reality is mixed kernels, mixed NICs, and generic fallback on VMs. A differential tester with a provenance manifest is how you learn where anywhere ends.

VM gets strangers a green reproduce button. A real NIC — including one passed through to a VM — gets you divergences that matter on uplinks.

---

*Synthetic lab traffic only. Tag `blog-x01-2026-07` pins this post.*
