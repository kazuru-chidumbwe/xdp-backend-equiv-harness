---
title: "A Differential Test Harness for Native vs. Generic XDP"
description: Native and generic SKB-mode XDP are not semantic equivalents. This post publishes the harness methodology, corpus design, and a virtio smoke gate — not a full divergence study.
tags: linux, networking, ebpf, security
---

Native XDP and generic SKB-mode XDP are not semantic equivalents. The same BPF bytecode, accepted by the same verifier, can produce different packet dispositions, post-hook frame bytes, and metadata observations depending on which attach mode the kernel uses. This post is a **methodology publication**: we ship an open differential test harness, a deterministic eleven-packet corpus, and a divergence taxonomy. A tagged release lets anyone reproduce the virtio/veth smoke gate. A follow-up post will publish pinned manifests from bare-metal NIC profiles and additional programs.

**Problem.** A firewall or rate-limiter validated only under native XDP can silently fall back to generic mode on an unsupported driver, a veth port, or after reload — same bytecode, different behaviour, often no error line.

**Contributions.**

1. Harness loop: corpus → inject on RX path → native vs generic sweep → `xdpdump` capture → `compare.py` manifest.
2. Deterministic corpus with eleven embedded test IDs (non-contiguous: `0xA001`, `0xA002`, `0xA003`, `0xA004`, `0xA005`, `0xA007`, `0xA008`, `0xA009`, `0xA00A`, `0xA00B`, `0xA00C`).
3. Operational divergence taxonomy (Class A/B/C) for interpreting differences.
4. Virtio/veth smoke gate on Linux 6.8 (lab) demonstrating end-to-end reproduction.

**Scope.** This post compares **native vs generic XDP** only, on **`prog_pass_drop`** only, on the **virtio_vm** profile only. Bare-metal NIC results, multi-program sweeps, and AF_XDP observation are future work.

Conformance testing stops at verifier load time. **Differential testing** asks: given identical input packets, do backends produce the same observable outcome at the hook?

## Background: native vs generic XDP

Both modes load the same BPF object. They diverge at the hook point and packet representation.

| Feature | Native XDP | Generic XDP (SKB) |
| --- | --- | --- |
| Hook point | Driver ingress (`ndo_xdp`, before `sk_buff`) | `netif_receive_skb()` path (`xdpgeneric`) |
| `sk_buff` | No — operates on driver frame / xdp_buff | Yes — packet seen as SKB-backed |
| `data_meta` | Driver- and headroom-dependent | Often NULL or reduced headroom |
| VLAN tags | As presented at driver ingress (unless RX VLAN offload strips early) | Same offload confounds apply; path differs |
| Fragments | Driver-dependent layout | May be linearised or presented differently |
| Checksum | Hardware offload may apply before hook | Software path more common |
| Typical throughput | NIC-limited (tens of Mpps class) | Lower (single-digit Mpps class on same hardware) |

Generic XDP exists so programs can run where drivers lack native support. That convenience trades away the early-hook semantics operators often assume when they test on one NIC and deploy on another.

Hardware SmartNIC signed offload is **out of scope** for this harness.

## Corpus (eleven packets)

Each frame embeds a test ID in the TCP/UDP sport, ICMP id, or payload tail so `compare.py` can pair captures without timing alignment.

| Test ID | Packet | Exercises | `prog_pass_drop` expected |
| --- | --- | --- | --- |
| 0xA001 | IPv4 TCP SYN | Basic L3/L4 parse | PASS |
| 0xA002 | IPv6 TCP SYN | Non-IPv4 ethertype (program passes non-IPv4) | PASS |
| 0xA003 | 802.1Q VLAN | Single tag | PASS |
| 0xA004 | QinQ | Double VLAN | PASS |
| 0xA005 | IPv4 fragment | Fragment / incomplete L4 | DROP (IPv4 frag frame lacks parseable TCP header; `sport == 0xA005` path not reached — parse fails → DROP) |
| 0xA009 | ICMP echo | Non-TCP/UDP | PASS |
| 0xA008 | UDP zero checksum | UDP / checksum edge | PASS |
| 0xA007 | TCP FIN/ACK | TCP flags | PASS |
| 0xA00A | TCP zero payload | Empty payload | PASS |
| 0xA00B | MTU-sized fill | Large frame | PASS |
| 0xA00C | DSCP/ECN | IP TOS field | PASS |

Coverage map: L2 (VLAN/QinQ), L3 (IPv4/IPv6/frag/TOS), L4 (TCP/UDP/ICMP), checksum edge, MTU fill. Additional programs (`prog_l3_modify`, `prog_vlan`, `prog_redirect`) are planned so each behaviour is isolated.

## What the comparator measures (v1)

The current `compare.py` implements **capture-level equivalence**:

1. **Pairing:** extract test ID from each `xdpdump` frame (payload tail, TCP/UDP sport, or ICMP id in range `0xA000`–`0xA0FF`).
2. **Fingerprint:** SHA-256 of the full post-hook frame bytes captured by `xdpdump` (truncated to 16 hex chars in the manifest).
3. **Verdict:** for each test ID, `equivalent: true` when native and generic fingerprints match; otherwise count as one divergence.

This encodes disposition and visible byte changes together — if one backend drops and the other passes, captures differ and the case flags non-equivalent. The manifest schema reserves `disposition`, `class`, and per-field metadata for a v2 comparator; v1 does not populate them yet.

**Non-deterministic fields:** `prog_pass_drop` does not modify headers. Packets traverse ingress RX only (no routing), checksum offload is disabled on bare-metal runs, and veth injection does not rewrite TTL or IP ID. For future programs that modify headers (`prog_l3_modify`), comparator v2 will support mask files to exclude timestamps, IDs, and checksum fields. Until then, pass/drop-only programs treat full-frame SHA-256 as a valid equivalence proxy on this topology.

**Measurement controls (bare-metal profile):** disable RX/TX checksum and RX VLAN offload before sweep:

```bash
ethtool -K $NIC rx off tx off rx-vlan-offload off
```

**Pitfalls:** inject on a **peer** interface (RX path), not `tcpreplay` on the XDP attach NIC; detach XDP between backend runs; do not merge manifests across profiles.

## Divergence taxonomy

| Class | Definition | Action |
| --- | --- | --- |
| **A** | Difference described in kernel docs or known backend semantics (e.g. documented `data_meta` absence in generic mode). | Record; do not treat as harness bug. |
| **B** | Same corpus and controlled NIC config; difference not documented but reproducible on standard hardware. | Investigate; consider kernel/driver report. |
| **C** | Caused by uncontrolled setup (offload left on, wrong inject path, capture race, mixed profiles). | Fix environment; exclude from analysis. |

## Harness architecture

**Topology (virtio_vm profile).** `topology-veth.sh` creates `veth-a` / `veth-b`, moves `veth-a` into netns `xdpequiv-inj`, attaches XDP on `veth-b` in the host namespace. Injection on `veth-a` guarantees packets **enter** `veth-b` on the RX path — the same guarantee a loop cable provides between two physical ports.

```text
generate_corpus.py → corpus.pcap
        │
        ▼
inject.py (netns xdpequiv-inj, iface veth-a)
        │
        ▼
veth peer → veth-b [XDP: native | generic]
        │
        ▼
xdpdump → captures/output_<backend>_pass_drop.pcap
        │
        ▼
compare.py → manifests/run_manifest_virtio_vm_pass_drop.json
```

**Bare-metal profile (blueprint).** Second physical port (or netns-moved inject port) + loop cable; same sweep script with `PROFILE=baremetal_nic`. Entry point: `make baremetal-sweep` (topology, carrier check, offload disable, sweep). Not yet run to completion in our lab (no loop-cabled pair).

## Experimental profiles

| Profile | Topology | Hardware | Entry point |
| --- | --- | --- | --- |
| **virtio_vm** | veth + netns inject | Any Linux VM / host | `sudo make topology && sudo make sweep-virtio` or `bash scripts/smoke.sh` |
| **baremetal_nic** | dual-port + loop cable | Wired NIC (`mlx5`, `i40e`, `igc`, `tg3`, …) | `export NIC=… INJ_IFACE=…; sudo make baremetal-sweep` |

`scripts/smoke.sh` wraps corpus + build + topology + sweep + a minimum case-count check — use it as the **pass/fail gate**. `make sweep-virtio` is the same sweep without the exit-code wrapper.

**Why a loop cable on bare metal?** XDP is an ingress hook. Injecting on the same NIC you attach to hits the TX path; a peer port (physical or veth) puts traffic on RX where native vs generic semantics differ.

**NIC families we plan to profile (lab roadmap):**

- **mlx5** (ConnectX): mature native XDP; common in high-throughput lab setups.
- **i40e** (X710 class): different driver architecture; VLAN/metadata edge cases.
- **igb/igc** (I350 class): accessible hardware; exercises generic fallback on ports without full native XDP.

## Validation

### Smoke gate (`prog_pass_drop`)

On Linux **6.8.0-134-generic** (lab VM, virtio/veth profile):

| Metric | Result |
| --- | --- |
| Corpus cases paired | 11 / 11 |
| Capture fingerprint mismatches (native vs generic) | **0** |
| `scripts/smoke.sh` | PASS |

Zero mismatches here means native and generic **agreed on captured frames** for this trivial pass/drop program on veth — not that backends always agree everywhere.

### Comparator sensitivity (synthetic)

`scripts/comparator-selftest.py` feeds `compare.py` two pcaps with the same test ID (`0xA099`) and intentionally different post-hook bytes (TTL change). Result: **`divergence_count: 1`**. This proves the comparator flags differences when they exist — it is not a tautology locked to zero.

Run the full validation bundle:

```bash
bash scripts/comparator-sensitivity.sh   # self-test + optional live probes
# or: make validate-comparator
```

### Live backend probes (informational)

The repository also ships `prog_metadata_test` (checks `data_meta` headroom) and `prog_vlan_probe` (PASS when 802.1Q is visible at L2). On our **6.8 veth lab run**, both probes still reported **0 capture divergences** — native and generic presented identical frames to `xdpdump`. We keep these programs for bare-metal and driver-specific profiles where backend differences are more likely. The self-test above is the publish gate for comparator teeth.

Example manifest excerpt (`prog_pass_drop`, smoke gate):

```json
{
  "profile": "virtio_vm",
  "kernel": "6.8.0-134-generic",
  "backends": ["native", "generic"],
  "corpus_sha256": "…",
  "program_sha256": "…",
  "divergence_count": 0,
  "cases": [
    {
      "test_id": 40961,
      "fingerprints": { "native": "a1b2c3…", "generic": "a1b2c3…" },
      "equivalent": true
    }
  ]
}
```

(`test_id` 40961 = 0xA001.) This validates end-to-end harness operation. Pinned manifests for bare-metal profiles ship in a follow-up post.

## Run it yourself

https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07

sudo apt-get install -y clang llvm libbpf-dev python3-scapy xdp-tools make \
  linux-tools-common linux-headers-$(uname -r)
# bpftool: from linux-tools-common on Ubuntu/Debian (package name may be bpftool on others)

bash scripts/smoke.sh
bash scripts/comparator-sensitivity.sh
```

**Troubleshooting:** `smoke.sh` exits non-zero if `xdpdump` or `clang` is missing, topology cannot create veth/netns (often stale `veth-a` — rerun `sudo make topology`), fewer than 11 paired test IDs in the manifest, or sweep/comparator failure. Run with `sudo` where shown; kernel **6.8+** matches the tagged lab gate.

Outputs: `manifests/run_manifest_virtio_vm_pass_drop.json`.

Bare-metal (when loop-cabled): see [`docs/BAREMETAL-LAB.md`](https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness/blob/main/docs/BAREMETAL-LAB.md).

## Future work

- Bare-metal NIC manifests (loop-cabled `mlx5` / `i40e` / `igc` profiles).
- Additional BPF programs (modify, VLAN, redirect) and v2 comparator fields (disposition, metadata class).
- AF_XDP redirect path as a third observation point.
- Related-work comparison with kernel BPF selftests and `xdp-tools` (this harness targets cross-backend **equivalence**, not single-backend correctness).

---

Further reading: [xdp-tools / xdpdump](https://github.com/xdp-project/xdp-tools)

*Synthetic lab traffic only. No production traffic.*
