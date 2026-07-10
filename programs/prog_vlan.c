// SPDX-License-Identifier: MIT
// prog_vlan: rewrite 802.1Q VLAN ID when tag is present (exercises L2 tag visibility).
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <bpf/bpf_endian.h>
#include <bpf/bpf_helpers.h>

struct vlan_hdr {
	__be16 h_vlan_TCI;
	__be16 h_vlan_encapsulated_proto;
};

SEC("xdp")
int xdp_vlan(struct xdp_md *ctx)
{
	void *data = (void *)(long)ctx->data;
	void *data_end = (void *)(long)ctx->data_end;
	struct ethhdr *eth = data;

	if ((void *)(eth + 1) > data_end)
		return XDP_DROP;
	if (eth->h_proto != bpf_htons(ETH_P_8021Q))
		return XDP_PASS;

	struct vlan_hdr *vh = (void *)(eth + 1);
	if ((void *)(vh + 1) > data_end)
		return XDP_DROP;

	/* Mark modified frames with VLAN ID 101 for capture fingerprint tests. */
	vh->h_vlan_TCI = bpf_htons(101);
	return XDP_PASS;
}

char _license[] SEC("license") = "MIT";
