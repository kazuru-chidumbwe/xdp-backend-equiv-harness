---
title: "A Differential Test Harness for Native vs. Generic XDP: Methodology and Baseline"
description: Native and generic SKB-mode XDP are not semantic equivalents. This post publishes the harness methodology, corpus design, virtio baseline sweeps, and comparator validation — not a full divergence study.
tags: linux, networking, ebpf, security
---

Native XDP and generic SKB-mode XDP are not semantic equivalents. The same BPF bytecode, accepted by the same verifier, can produce different packet dispositions, post-hook frame bytes, and metadata observations depending on which attach mode the kernel uses. This post is a **methodology publication**: we ship an open differential test harness, a deterministic eleven-packet corpus, and a divergence taxonomy. A tagged release lets anyone reproduce the virtio/veth smoke gate. A follow-up post will publish pinned manifests from bare-metal NIC profiles and additional programs.

**Problem.** A firewall or rate-limiter validated only under native XDP can silently fall back to generic mode on an unsupported driver, a veth port, or after reload — same bytecode, different behaviour, often no error line.

**Contributions.**

1. Harness loop: corpus → inject on RX path → native vs generic sweep → `xdpdump` capture → `compare.py` manifest.
2. Deterministic corpus with eleven embedded test IDs (non-contiguous: `0xA001`–`0xA005`, `0xA007`–`0xA00C`; **`0xA006` omitted** — reserved gap in the generator's ID assignment).
3. Operational divergence taxonomy (Class A/B/C) for interpreting differences.
4. Virtio/veth smoke gate on Linux 6.8 (lab) demonstrating end-to-end reproduction.

**Scope.** This post publishes the harness methodology and **virtio/veth results for five BPF programs** (today's lab run). Bare-metal NIC sweeps require a loop-cabled dual-port pair — not yet completed in our lab (passthrough ports show `NO-CARRIER`). AF_XDP as a third observation point is future work.

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

Coverage map: L2 (VLAN/QinQ), L3 (IPv4/IPv6/frag/TOS), L4 (TCP/UDP/ICMP), checksum edge, MTU fill. Additional programs isolate behaviours: `prog_metadata_test` (`data_meta` headroom), `prog_vlan` (802.1Q rewrite), `prog_l3_modify` (TTL decrement), `prog_redirect` (same-port `XDP_REDIRECT`).

## What the comparator measures (v1)

The current `compare.py` implements **capture-level equivalence** (v1):

1. **Pairing:** extract test ID from each `xdpdump` frame (payload tail, TCP/UDP sport, or ICMP id in range `0xA000`–`0xA0FF`).
2. **Capture point:** sweeps use `xdpdump --rx-capture=exit` (post-program frame bytes; default `xdpdump` is entry-only).
3. **Fingerprint:** SHA-256 of the captured frame bytes (truncated to 16 hex chars in the manifest).
4. **Verdict:** for each test ID, `equivalent: true` only when **both** backends captured the ID **and** fingerprints match. A test ID present in one backend but missing in the other counts as a divergence.

**What v1 does not measure (two separate blind spots):**

1. **Disposition-only differences** — On a byte-preserving program, DROP and PASS produce identical exit-capture frame bytes. xdpdump records the verdict as separate **pcapng metadata** (e.g. `@exit[DROP]:`), not in the frame. v1 hashes frames only.
2. **Context-metadata differences** — `ingress_ifindex`, `data_meta`, and `rx_queue_index` live in `xdp_md`; they are not part of the captured frame at all.

A backend pair can disagree on either axis while v1 reports `equivalent: true`. v2 will parse pcapng action extensions and read context fields (bpftool / trace) to close both gaps.

**Non-deterministic fields:** `prog_pass_drop` does not modify headers. Packets traverse ingress RX only (no routing), checksum offload is disabled on bare-metal runs, and veth injection does not rewrite TTL or IP ID. For header-mutating programs (`prog_l3_modify`, `prog_vlan`), exit capture reflects modifications; comparator v2 will add mask files for checksum/IP-ID fields where needed.

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

`scripts/smoke.sh` wraps corpus + build + topology + sweep + a minimum case-count check — use it as the **pass/fail gate**. `make sweep-virtio` runs one program; `bash scripts/sweep-all-virtio.sh` sweeps all five blog programs on veth.

**Why a loop cable on bare metal?** XDP is an ingress hook. Injecting on the same NIC you attach to hits the TX path; a peer port (physical or veth) puts traffic on RX where native vs generic semantics differ.

**NIC families we plan to profile (lab roadmap):**

- **mlx5** (ConnectX): mature native XDP; common in high-throughput lab setups.
- **i40e** (X710 class): different driver architecture; VLAN/metadata edge cases.
- **igb/igc** (I350 class): accessible hardware; exercises generic fallback on ports without full native XDP.

## Results

We evaluated the harness on the **virtio_vm** profile (Linux **6.8.0-134-generic**, veth + netns inject) across five programs:

| Program | Cases paired | Divergences (native vs generic) |
| --- | --- | --- |
| `prog_pass_drop` | 11 / 11 | **0** |
| `prog_metadata_test` | 11 / 11 | **0** |
| `prog_vlan` | 11 / 11 | **0** |
| `prog_l3_modify` | 11 / 11 | **0** |
| `prog_redirect` | 11 / 11 | **0** |

Pinned manifests: `manifests/run_manifest_virtio_vm_<program>.json` in the repository.

**What this means.** Zero divergences on veth means native and generic **presented identical exit-capture frame bytes** for these programs on this topology — not that backends always agree on every NIC.

**Why `prog_metadata_test` shows 0 on veth (not a bug).** The program returns `XDP_PASS` when `data_meta < data` (headroom exists), else `XDP_DROP`. On our **6.8 veth** run, both backends likely agreed on headroom **and** exit-capture bytes. Even when backends disagree on disposition or `data_meta`, v1 may still show 0 — disposition lives in pcapng metadata; `data_meta` is never in the frame (see blind spots above). Bare-metal sweeps are where Class A context gaps are expected; the paper hook is v2 + physical NIC profiles.

**Bare-metal (pending).** PCI passthrough ports (`ens16f0` / `ens16f1`, BCM5720 class) in our VM show `NO-CARRIER` without a loop cable — we have not published bare-metal manifests yet. When loop-cabled, run `sudo NIC=… INJ_IFACE=… PROG=metadata_test make baremetal-sweep` (or `scripts/sweep-all-virtio.sh` on veth) — that is the path to Class A/B findings (e.g. VLAN tag visibility under RX offload).

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

`scripts/comparator-selftest.py` feeds `compare.py` two pcaps with the same test ID (`0xA099`) and intentionally different post-hook bytes (TTL change). Result: **`divergence_count: 1`**. `scripts/comparator-missing-tid-test.py` verifies that a test ID present on only one backend also counts as a divergence. Together these prove the comparator flags differences when they exist — it is not a tautology locked to zero.

Run the full validation bundle:

```bash
bash scripts/comparator-sensitivity.sh   # self-test + optional live probes
# or: make validate-comparator
bash scripts/sweep-all-virtio.sh         # all five programs on veth
```

### Live backend probes (informational)

The repository ships `prog_metadata_test`, `prog_vlan`, `prog_l3_modify`, and `prog_redirect` alongside `prog_vlan_probe` (802.1Q visibility probe). On our **6.8 veth lab run**, all five sweeps above reported **0 capture divergences**. We keep these programs for bare-metal and driver-specific profiles where backend differences are more likely. The self-test above is the publish gate for comparator teeth.

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

(`test_id` 40961 = 0xA001.) Full manifests for all five virtio programs are in the repository. Bare-metal profiles ship when loop-cabled hardware is available.

## Run it yourself

https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness

```bash
git clone https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness.git
cd xdp-backend-equiv-harness
git checkout blog-x01-2026-07

sudo apt-get install -y clang llvm libbpf-dev python3-scapy xdp-tools make \
  linux-tools-common linux-headers-$(uname -r)
# xdpdump ships in xdp-tools (Ubuntu/Debian). If missing: build from https://github.com/xdp-project/xdp-tools

bash scripts/smoke.sh
bash scripts/comparator-sensitivity.sh
bash scripts/sweep-all-virtio.sh
```

**Troubleshooting:** `smoke.sh` exits non-zero if `xdpdump` or `clang` is missing, topology cannot create veth/netns (often stale `veth-a` — rerun `sudo make topology`), fewer than 11 paired test IDs in the manifest, or sweep/comparator failure. If you see `Native and generic XDP can't be active at the same time`, ensure both `xdp off` and `xdpgeneric off` ran between backend captures (fixed in current `harness/sweep.sh`). Run with `sudo` where shown; kernel **6.8+** matches the tagged lab gate.

Outputs: `manifests/run_manifest_virtio_vm_*.json`.

Bare-metal (when loop-cabled): see [`docs/BAREMETAL-LAB.md`](https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness/blob/main/docs/BAREMETAL-LAB.md).

## Future work

- Bare-metal NIC manifests (loop-cabled `mlx5` / `i40e` / `igc` / BCM5720 profiles) — Class B divergence hunting.
- Comparator v2 fields (disposition, metadata class, field masks for `prog_l3_modify`).
- DEVMAP-based redirect to a peer interface (current `prog_redirect` uses same-port reinject).
- AF_XDP redirect path as a third observation point.
- Related-work comparison with kernel BPF selftests and `xdp-tools` (this harness targets cross-backend **equivalence**, not single-backend correctness).

---

Further reading: [xdp-tools / xdpdump](https://github.com/xdp-project/xdp-tools)

*Synthetic lab traffic only. No production traffic.*
