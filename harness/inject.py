#!/usr/bin/env python3
"""Inject corpus packets on peer veth (RX path toward XDP-attached iface)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from scapy.all import rdpcap, sendp

if len(sys.argv) != 3:
    print(f"usage: {sys.argv[0]} <corpus.pcap> <iface>", file=sys.stderr)
    sys.exit(2)

pcap = Path(sys.argv[1])
iface = sys.argv[2]
pkts = rdpcap(str(pcap))
for i, pkt in enumerate(pkts):
    sendp(pkt, iface=iface, verbose=False)
    time.sleep(0.01)
print(f"Injected {len(pkts)} packets on {iface}")
