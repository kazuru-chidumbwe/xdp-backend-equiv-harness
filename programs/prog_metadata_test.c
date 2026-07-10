// SPDX-License-Identifier: MIT
// prog_metadata_test: PASS when data_meta headroom exists; DROP otherwise.
// Generic SKB XDP often has data_meta == data (no headroom) → systematic divergence vs native.
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

SEC("xdp")
int xdp_metadata_test(struct xdp_md *ctx)
{
	void *data_meta = (void *)(long)ctx->data_meta;
	void *data = (void *)(long)ctx->data;

	if (data_meta < data)
		return XDP_PASS;
	return XDP_DROP;
}

char _license[] SEC("license") = "MIT";
