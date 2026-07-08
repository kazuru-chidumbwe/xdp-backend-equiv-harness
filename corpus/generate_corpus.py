#!/usr/bin/env python3
"""Deterministic XDP equivalence corpus. Seed-fixed; embed test_id in payload."""

from __future__ import annotations

import struct
from pathlib import Path

from scapy.all import Ether, IP, IPv6, TCP, UDP, ICMP, Dot1Q, Raw, wrpcap

SEED = 0x58545045  # 'XTPE'
CORPUS_PATH = Path(__file__).resolve().parent / "corpus.pcap"

# test_id: 2-byte big-endian in TCP/UDP sport or ICMP id field where possible
CASES: list[tuple[str, callable]] = []


def _tid(n: int) -> int:
    return 0xA000 + n


def case_01_ipv4_syn() -> Ether:
    tid = _tid(1)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1", ttl=64)
        / TCP(sport=tid, dport=443, flags="S", seq=1000)
        / Raw(load=bytes([0x58, 0x44, 0x50, 0x45]) + struct.pack(">H", tid))
    )


def case_02_ipv6_syn() -> Ether:
    tid = _tid(2)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IPv6(dst="fd00::2", src="fd00::1", hlim=64)
        / TCP(sport=tid, dport=443, flags="S", seq=2000)
        / Raw(load=bytes([0x58, 0x44, 0x50, 0x45]) + struct.pack(">H", tid))
    )


def case_03_vlan_single() -> Ether:
    tid = _tid(3)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / Dot1Q(vlan=100)
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=80, flags="S")
        / Raw(load=struct.pack(">H", tid))
    )


def case_04_vlan_qinq() -> Ether:
    tid = _tid(4)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / Dot1Q(vlan=100)
        / Dot1Q(vlan=200)
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=80, flags="S")
        / Raw(load=struct.pack(">H", tid))
    )


def case_05_ipv4_frag() -> Ether:
    tid = _tid(5)
    # Second fragment style: more fragments, offset > 0 — no TCP header in this frame
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1", flags="MF", frag=185, proto=6)
        / Raw(load=b"\x00" * 100 + struct.pack(">H", tid))
    )


def case_06_icmp_echo() -> Ether:
    tid = _tid(9)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / ICMP(type=8, code=0, id=tid)
        / Raw(load=b"xdpequiv")
    )


def case_07_udp_zero_csum() -> Ether:
    tid = _tid(8)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / UDP(sport=tid, dport=53, chksum=0)
        / Raw(load=b"\x00" * 8)
    )


def case_08_tcp_fin_ack() -> Ether:
    tid = _tid(7)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=443, flags="FA", seq=3000, ack=3001)
        / Raw(load=struct.pack(">H", tid))
    )


def case_09_zero_payload() -> Ether:
    tid = _tid(10)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=9, flags="S")
    )


def case_10_mtu_fill() -> Ether:
    tid = _tid(11)
    payload = b"X" * (1500 - 14 - 20 - 20)  # eth + ip + tcp headers approx
    payload = payload[: len(payload) - 2] + struct.pack(">H", tid)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1")
        / TCP(sport=tid, dport=80, flags="P")
        / Raw(load=payload)
    )


def case_11_dscp_ecn() -> Ether:
    tid = _tid(12)
    return (
        Ether(dst="02:00:00:00:00:02", src="02:00:00:00:00:01")
        / IP(dst="10.0.0.2", src="10.0.0.1", tos=0x2E)
        / TCP(sport=tid, dport=443, flags="S")
        / Raw(load=struct.pack(">H", tid))
    )


BUILDERS = [
    ("TC-01-ipv4-syn", case_01_ipv4_syn),
    ("TC-02-ipv6-syn", case_02_ipv6_syn),
    ("TC-03-vlan-single", case_03_vlan_single),
    ("TC-04-vlan-qinq", case_04_vlan_qinq),
    ("TC-05-ipv4-frag", case_05_ipv4_frag),
    ("TC-06-icmp-echo", case_06_icmp_echo),
    ("TC-07-udp-zero-csum", case_07_udp_zero_csum),
    ("TC-08-tcp-fin-ack", case_08_tcp_fin_ack),
    ("TC-09-zero-payload", case_09_zero_payload),
    ("TC-10-mtu-fill", case_10_mtu_fill),
    ("TC-11-dscp-ecn", case_11_dscp_ecn),
]


def main() -> None:
    packets = [fn() for _name, fn in BUILDERS]
    wrpcap(str(CORPUS_PATH), packets)
    print(f"Wrote {len(packets)} packets to {CORPUS_PATH}")


if __name__ == "__main__":
    main()
