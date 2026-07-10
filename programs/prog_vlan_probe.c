// SPDX-License-Identifier: MIT
// prog_vlan_probe: PASS when 802.1Q ethertype is visible at L2.
// Generic SKB XDP may present untagged frames → diverges from native on VLAN corpus cases.
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <bpf/bpf_endian.h>
#include <bpf/bpf_helpers.h>

SEC("xdp")
int xdp_vlan_probe(struct xdp_md *ctx)
{
	void *data = (void *)(long)ctx->data;
	void *data_end = (void *)(long)ctx->data_end;
	struct ethhdr *eth = data;

	if ((void *)(eth + 1) > data_end)
		return XDP_DROP;
	if (eth->h_proto == bpf_htons(ETH_P_8021Q))
		return XDP_PASS;
	return XDP_DROP;
}

char _license[] SEC("license") = "MIT";
