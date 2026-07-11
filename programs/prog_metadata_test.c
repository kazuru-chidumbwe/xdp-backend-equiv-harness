// SPDX-License-Identifier: MIT
// prog_metadata_test: PASS when data_meta headroom exists; DROP otherwise.
// Generic SKB XDP on some drivers/NICs has data_meta == data (no headroom) → disposition
// divergence vs native. v1 compare.py fingerprints exit-capture bytes only; identical
// bytes with different PASS/DROP verdicts still show equivalent: true (verdict is pcapng metadata).
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
