# Harness architecture

```text
corpus.pcap (deterministic, test IDs in payload)
        │
inject.py / raw socket on PEER veth (RX path — not tcpreplay TX on same iface)
        │
┌───────┴───────┐
│  ingress dev  │  XDP program loaded: native | xdpgeneric
└───────┬───────┘
        │
xdpdump + action log  →  captures/output_<backend>_<prog>.pcap
        │
compare.py  →  manifests/run_manifest.json
```

## Backend matrix (phase 1)

| ID | Load | Capture |
| --- | --- | --- |
| `native` | `ip link set dev $IF xdp obj $OBJ sec $SEC` | xdpdump |
| `generic` | `ip link set dev $IF xdpgeneric obj $OBJ sec $SEC` | xdpdump |

Phase 2: `native` + `XDP_REDIRECT` to AF_XDP socket + userspace echo (checksum-agnostic ops only).

## Equivalence classes

- **Class A** — Spec-defined backend difference (document, do not count as failure)
- **Class B** — Operator-surprising divergence (primary findings)
- **Class C** — Harness bug (offload, wrong capture point, stale maps)

## Pitfalls (mandatory checklist)

- [ ] Checksum offload disabled on measurement NIC
- [ ] Capture at XDP hook (drops visible)
- [ ] XDP detached between backend runs
- [ ] BPF maps reset between runs
- [ ] Negative control packet agrees on all backends
