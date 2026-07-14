---
title: "A Differential Test Harness for Native vs. Generic XDP: Methodology and Baseline"
description: Native and generic SKB-mode XDP are not semantic equivalents. This post publishes the harness methodology, corpus design, virtio baseline sweeps, and comparator validation — not a full divergence study.
tags: linux, networking, ebpf, security
published: false
canonical_url:
---

<!-- Blog essay mirrored from release; cite tag blog-x01-2026-07 -->

Native XDP and generic SKB-mode XDP are not the same thing in practice. The same BPF program can pass the verifier and still produce different dispositions, different post-hook frame bytes, or different metadata depending on which attach mode the kernel uses. This post ships an open differential test harness, a fixed eleven-packet corpus, and a simple way to classify differences. A tagged release lets anyone reproduce the virtio/veth smoke gate on Linux 6.8.

The operational risk is straightforward. A firewall or rate-limiter validated only under native XDP can fall back to generic mode on an unsupported driver, a veth port, or after a reload. You keep the same bytecode, but behaviour can change — often without a clear error line.

What this release includes:

1. A harness loop: corpus → inject on the RX path → native vs generic sweep → `xdpdump` capture → `compare.py` manifest, comparing both the captured frame bytes and the XDP verdict (`PASS`/`DROP`/`TX`/`REDIRECT`).
2. A deterministic corpus with eleven embedded test IDs (`0xA001`–`0xA005`, `0xA007`–`0xA00C`; `0xA006` is intentionally omitted as a reserved gap in the generator).
3. An operational divergence taxonomy (Class A / B / C).
4. A virtio/veth smoke gate on Linux 6.8 — now gating on frame bytes **and** verdict agreement — that shows the full path is reproducible end to end.

Scope for this post: native vs generic XDP on the `virtio_vm` profile only (five BPF programs, pinned manifests). This is part 1 of 2 — it establishes the harness and an instrument-validity baseline; a follow-up post covers bare-metal divergence results. Physical NIC results are not part of this baseline.

Ordinary conformance checks stop at “did the program load?” Differential testing asks a sharper question: given identical input packets, do the backends produce the same observable outcome at the hook?

## Background: native vs generic XDP

Both modes load the same BPF object. They diverge at the hook point and in how the packet is represented.

| Feature | Native XDP | Generic XDP (SKB) |
| --- | --- | --- |
| Hook point | Driver ingress (`ndo_xdp`, before `sk_buff`) | `netif_receive_skb()` path (`xdpgeneric`) |
| `sk_buff` | No — works on the driver frame / `xdp_buff` | Yes — packet is SKB-backed |
| `data_meta` | Depends on driver and headroom | Often NULL or reduced headroom |
| VLAN tags | As presented at driver ingress (unless RX VLAN offload strips early) | Same offload confounds; path still differs |
| Fragments | Driver-dependent layout | May be linearised or presented differently |
| Checksum | Hardware offload may apply before the hook | Software path is more common |
| Typical throughput | NIC-limited (tens of Mpps class) | Lower (single-digit Mpps class on the same hardware) |

Generic XDP exists so programs can run where drivers lack native support. That convenience costs the early-hook semantics people often assume when they test on one NIC and deploy on another.

Hardware SmartNIC signed offload is out of scope for this harness.

## Corpus (eleven packets)

Each frame carries a test ID in the TCP/UDP source port, ICMP id, or payload tail so `compare.py` can pair captures without relying on timing.

| Test ID | Packet | Exercises | `prog_pass_drop` expected |
| --- | --- | --- | --- |
| 0xA001 | IPv4 TCP SYN | Basic L3/L4 parse | PASS |
| 0xA002 | IPv6 TCP SYN | Non-IPv4 ethertype (program passes non-IPv4) | PASS |
| 0xA003 | 802.1Q VLAN | Single tag | PASS |
| 0xA004 | QinQ | Double VLAN | PASS |
| 0xA005 | IPv4 fragment | Fragment / incomplete L4 | PASS (a non-first fragment carries no TCP header, so the `sport == 0xA005` drop branch is never reached — the drop path is effectively dead against this corpus) |
| 0xA009 | ICMP echo | Non-TCP/UDP | PASS |
| 0xA008 | UDP zero checksum | UDP / checksum edge | PASS |
| 0xA007 | TCP FIN/ACK | TCP flags | PASS |
| 0xA00A | TCP zero payload | Empty payload | PASS |
| 0xA00B | MTU-sized fill | Large frame | PASS |
| 0xA00C | DSCP/ECN | IP TOS field | PASS |

Coverage spans L2 (VLAN/QinQ), L3 (IPv4/IPv6/frag/TOS), L4 (TCP/UDP/ICMP), a checksum edge, and an MTU fill. Companion programs isolate other behaviours: `prog_metadata_test` (`data_meta` headroom), `prog_vlan` (802.1Q rewrite), `prog_l3_modify` (TTL decrement), and `prog_redirect` (same-port `XDP_REDIRECT`).

## What the comparator measures

`compare.py` compares two axes per test ID:

1. Pairing — extract the test ID from each `xdpdump` frame (payload tail, TCP/UDP source port, or ICMP id in `0xA000`–`0xA0FF`).
2. Capture point — sweeps use `xdpdump --rx-capture=exit` (post-program frame bytes; default `xdpdump` is entry-only).
3. Frame fingerprint — SHA-256 of the captured frame bytes (truncated to 16 hex characters). `equivalent: true` for a test ID only when both backends captured it and the fingerprints match; an ID present on one backend but missing on the other is a divergence.
4. Verdict — the XDP action (`PASS` / `DROP` / `TX` / `REDIRECT`). `xdpdump` reports this in its text output (`xdp_prog()@exit[DROP]`), not in the `-w` pcapng frame, so the sweep runs a second `xdpdump -x` pass and `compare.py` records a `verdict` and `verdict_match` per test ID plus a top-level `verdict_divergence_count`. This axis is independent of the frame bytes: a byte-preserving DROP-vs-PASS disagreement is invisible to the fingerprint but caught here.

The one axis still not measured:

- Context-metadata differences — `ingress_ifindex`, `data_meta`, and `rx_queue_index` live in `xdp_md` and never appear in the captured frame or in xdpdump's per-packet text. Two backends can still disagree here while both fingerprint and verdict match. This is a Class C observation limit; capturing it needs a metadata-echo BPF program, planned for the bare-metal follow-up.

On non-determinism: `prog_pass_drop` does not modify headers. Packets traverse ingress RX only (no routing), and veth injection does not rewrite TTL or IP ID. For header-mutating programs (`prog_l3_modify`, `prog_vlan`), the exit capture reflects those modifications.

Pitfalls worth naming once: inject on a peer interface (RX path), not `tcpreplay` onto the XDP attach NIC; detach XDP between backend runs; keep manifests labeled by profile.

## Divergence taxonomy

| Class | Definition | Action |
| --- | --- | --- |
| A | Difference described in kernel docs or known backend semantics (for example documented `data_meta` absence in generic mode). | Record it; do not treat it as a harness bug. |
| B | Same corpus and controlled NIC config; difference is not documented but reproducible on standard hardware. | Investigate; consider a kernel/driver report. |
| C | Caused by uncontrolled setup (offload left on, wrong inject path, capture race, mixed profiles) — or by a measurement limit of the harness. | Fix the environment or document the limit; exclude from “surprise” analysis. |

## Harness architecture

On the `virtio_vm` profile, `topology-veth.sh` creates `veth-a` / `veth-b`, moves `veth-a` into netns `xdpequiv-inj`, and attaches XDP on `veth-b` in the host namespace. Injection on `veth-a` puts packets onto `veth-b` on the RX path — where native vs generic semantics actually differ.

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

## Lab profile for this post

| Profile | Topology | Hardware | Entry point |
| --- | --- | --- | --- |
| `virtio_vm` | veth + netns inject | Any Linux VM / host | `sudo make topology && sudo make sweep-virtio` or `bash scripts/smoke.sh` |

`scripts/smoke.sh` wraps corpus + build + topology + sweep and checks a minimum case count — treat it as the pass/fail gate. `make sweep-virtio` runs one program; `bash scripts/sweep-all-virtio.sh` sweeps all five blog programs on veth.

## Results

We ran the harness on the `virtio_vm` profile (Linux 6.8.0-134-generic, veth + netns inject) across five programs:

| Program | Cases paired | Byte divergences | Verdict (both backends) | Verdict divergences |
| --- | --- | --- | --- | --- |
| `prog_pass_drop` | 11 / 11 | 0 | PASS | 0 |
| `prog_metadata_test` | 11 / 11 | 0 | DROP | 0 |
| `prog_vlan` | 11 / 11 | 0 | PASS | 0 |
| `prog_l3_modify` | 11 / 11 | 0 | PASS | 0 |
| `prog_redirect` | 11 / 11 | 0 | REDIRECT | 0 |

Pinned manifests live in the repository as `manifests/run_manifest_virtio_vm_<program>.json`.

Zero byte divergences on veth means native and generic presented identical exit-capture frame bytes for these programs on this topology. Zero verdict divergences means they also returned the same XDP action for every test ID. Agreement therefore holds on both axes here — but only for this topology; it does not mean backends always agree on every NIC, and the context axis (`data_meta`, `ingress_ifindex`, `rx_queue_index`) is still unmeasured.

On `prog_pass_drop`: verdict capture is now instrumented, and on this corpus every test ID resolves to `PASS` on both backends. That is because the corpus does not yet include a packet that triggers the program's `DROP` branch — the drop rule fires on `TCP sport == 0xA005`, but case 05 (`0xA005`) is a non-first IP fragment with no TCP header, so the source port read at the L4 offset is never `0xA005`. The `DROP` path is effectively dead against this corpus. A packet that genuinely triggers the drop is deferred to the bare-metal follow-up, where the corpus pipeline is rebuilt and re-verified anyway.

On `prog_metadata_test`: the verdict axis now shows both backends return `DROP` for every case — something the frame fingerprint alone could never have told us (the program does not mutate the payload, so the bytes are trivially identical either way). The backends agree on the disposition. Note this is still not evidence that they agree on `data_meta` headroom itself, which lives in `xdp_md` and is never captured; treat headroom agreement as unmeasured.

Two observation limits remain for this baseline:

- `prog_redirect`: both backends return `REDIRECT` and the exit-capture bytes match, but the harness captures on the attach interface only. Full equivalence would also require confirming the packet reached the redirect destination with matching bytes — a Class C limit for this program.
- VLAN offload: the corpus includes 802.1Q and QinQ, but the harness does not yet verify whether RX VLAN offload strips tags before XDP sees them (more likely under generic mode). `prog_vlan_probe` ships for this check, but its output is not part of this baseline.

## Validation

### Smoke gate (`prog_pass_drop`)

On Linux 6.8.0-134-generic (lab VM, virtio/veth profile):

| Metric | Result |
| --- | --- |
| Corpus cases paired | 11 / 11 |
| Capture fingerprint mismatches (native vs generic) | 0 |
| Verdict mismatches (native vs generic) | 0 (all PASS) |
| `scripts/smoke.sh` | PASS |

The gate now requires agreement on both axes: the frame fingerprints must match **and** `verdict_divergence_count` must be 0. This closes the earlier hole where a byte-only check would pass even if one backend dropped a packet the other passed — for a non-mutating program like `prog_pass_drop`, the frame bytes are identical regardless of the action, so without the verdict check the gate was blind to the single most operationally important difference. It is still a backstop on a trivial topology, not a claim of universal equivalence.

### Comparator sensitivity (synthetic)

`scripts/comparator-selftest.py` feeds `compare.py` two pcaps with the same test ID (`0xA099`) and intentionally different post-hook bytes (TTL change). Result: `divergence_count: 1`. `scripts/comparator-missing-tid-test.py` checks that a test ID present on only one backend also counts as a divergence. `scripts/comparator-blindspot-demo.py` feeds identical frame bytes to both backends and correctly gets `divergence_count: 0` — byte agreement alone does not prove context agreement. `scripts/comparator-verdict-selftest.py` synthesises two `xdpdump -x` logs for the same test ID with identical frame bytes but opposite verdicts (`PASS` vs `DROP`); the comparator reports `divergence_count: 0` (bytes match) and `verdict_divergence_count: 1` (verdict caught) — confirming the verdict axis flags a deliberate disposition mismatch that the byte fingerprint cannot see. Together these show the comparator flags both byte and verdict differences when they exist, and document the one axis (context) it still cannot see.

Run the full validation bundle:

```bash
bash scripts/comparator-sensitivity.sh   # self-test + optional live probes
# or: make validate-comparator
bash scripts/sweep-all-virtio.sh         # all five programs on veth
```

### Live backend probes (informational)

The repository ships `prog_metadata_test`, `prog_vlan`, `prog_l3_modify`, and `prog_redirect`, plus `prog_vlan_probe` (an 802.1Q visibility probe). On our 6.8 veth lab run, all five sweeps reported 0 capture-byte divergences and 0 verdict divergences (dispositions: `pass_drop` PASS, `metadata_test` DROP, `vlan` PASS, `l3_modify` PASS, `redirect` REDIRECT — identical on both backends). The synthetic self-tests confirm the comparator flags both byte and verdict differences when they exist; the context axis (`xdp_md` metadata) remains unmeasured until the bare-metal follow-up.

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

(`test_id` 40961 = 0xA001.) Full manifests for all five virtio programs are in the repository.

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

Troubleshooting: `smoke.sh` exits non-zero if `xdpdump` or `clang` is missing, if topology cannot create veth/netns (often a stale `veth-a` — rerun `sudo make topology`), if fewer than 11 paired test IDs land in the manifest, or if the sweep/comparator fails. If you see `Native and generic XDP can't be active at the same time`, make sure both `xdp off` and `xdpgeneric off` ran between backend captures (handled in current `harness/sweep.sh`). Use `sudo` where shown; kernel 6.8+ matches the tagged lab gate.

Outputs: `manifests/run_manifest_virtio_vm_*.json`.

---

Further reading: [xdp-tools / xdpdump](https://github.com/xdp-project/xdp-tools)

*Synthetic lab traffic only. No production traffic.*
