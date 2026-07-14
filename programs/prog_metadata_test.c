// SPDX-License-Identifier: MIT
// prog_metadata_test: PASS when data_meta headroom exists; DROP otherwise.
// Generic SKB XDP on some drivers/NICs has data_meta == data (no headroom) → disposition
// divergence vs native. The frame fingerprint alone cannot see this: identical bytes with
// different PASS/DROP verdicts still compare equal. compare.py now also compares the verdict,
// parsed from xdpdump's -x text output (@exit[PASS]/@exit[DROP]) — the action is in that text,
// not in the -w pcapng frame. The data_meta value itself (in xdp_md) remains uncaptured.
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
