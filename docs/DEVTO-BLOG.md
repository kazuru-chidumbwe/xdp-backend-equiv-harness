---
title: "Same XDP Program, Three Backends: Building a Differential Tester for Native, Generic, and AF_XDP"
published: false
description: XDP is marketed as run-anywhere kernel bypass. Native, generic SKB, and AF_XDP paths disagree more often than operators admit. This post describes an open harness — VM for reproducibility, wired NIC for driver-level checks.
tags: linux, networking, ebpf, security
canonical_url: https://dev.to/PLACEHOLDER
---

You load one `.o` file. You attach it with `ip link set dev eth0 xdp obj prog.o`. In production, that program might run in **native XDP** on a datacenter uplink, in **generic (SKB) XDP** on a VM NIC without driver offload, or behind **AF_XDP** after a redirect to userspace. The BPF bytecode is the same. The observable packet fate often is not.

A common operational assumption is: *if the verifier accepted it, behaviour is portable*. Conformance testing usually stops at load time. **Differential testing** asks a stricter question: given identical input packets, do all backends produce the same disposition, post-hook bytes, and metadata?

This post documents the harness blueprint, reproduction layout, and measurement model. A separate results write-up will publish pinned divergence manifests once bare-metal lab runs complete.

## Native, generic, and AF_XDP are not the same runtime

**Native XDP** runs at the driver ingress hook, before `sk_buff` allocation. Programs see early drops, frame layout as presented by the driver, and (when supported) the metadata surface the program expects.

**Generic XDP** (`xdpgeneric`, SKB mode) runs later on the `netif_receive_skb` path. No driver XDP support is required. That path uses a different packet representation: VLAN tags may already be stripped, fragments may differ, and `data_meta` may be NULL where native mode had headroom.

**AF_XDP** is not a parallel in-kernel backend. It is a **redirect target**: native XDP can send matching frames to an AF_XDP socket; userspace may complete policy there. We treat it as a third observation point because stacks such as Cilium, Katran, and custom filters routinely split work across kernel and userspace. Equivalence claims that ignore that boundary are incomplete.

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
- **Class C** — harness or capture artifact  

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

Documented pitfalls: capture at the hook, disable checksum offload on measurement NICs, detach XDP between backend runs, and include a negative-control packet that must agree on all backends.

## AF_XDP (not yet in the sweep)

The current sweep compares **native vs generic** in-kernel only. AF_XDP support will add a redirect path plus userspace observation; checksum-sensitive operations stay out of that path until the comparator can treat them consistently.

## Run it yourself

https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness

Checkout tag **`blog-x01-2026-07`** — that pin matches this post.

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07   # commit 6e6a92d

sudo apt-get install -y clang llvm libbpf-dev python3-scapy xdp-tools make linux-headers-$(uname -r)

make corpus
make build
sudo make topology
sudo make sweep-virtio
```

Virtio smoke gate:

```bash
bash scripts/smoke.sh
```

Wired NIC (loop-cable ports, carrier up on both):

```bash
export NIC=ens16f0
export INJ_IFACE=ens16f1
sudo bash scripts/baremetal-sweep.sh
```

See [`docs/BAREMETAL-LAB.md`](https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness/blob/main/docs/BAREMETAL-LAB.md) for PCI passthrough, default lab IPs (`192.168.0.5` / `192.168.0.6`), and carrier checks.

Outputs: `manifests/run_manifest_<profile>_<prog>.json`.

## Status

| Profile | State |
| --- | --- |
| **virtio_vm** | Verified — 11 corpus cases, 0 divergences on kernel 6.8 (lab) |
| **baremetal_nic** | Pending — requires loop-cabled wired ports; WiFi out of scope |

WiFi interfaces are not supported as an observation point in this harness; wired ethernet is required for the bare-metal profile.

---

Further reading: [xdp-tools / xdpdump](https://github.com/xdp-project/xdp-tools) · [AF_XDP](https://www.kernel.org/doc/html/latest/networking/af_xdp.html)

*Synthetic lab traffic only. No production traffic. Results tagged per NIC model and kernel version.*
