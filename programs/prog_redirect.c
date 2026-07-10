// SPDX-License-Identifier: MIT
// prog_redirect: XDP_REDIRECT to ingress ifindex (same-port reinject baseline).
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

SEC("xdp")
int xdp_redirect(struct xdp_md *ctx)
{
	return bpf_redirect(ctx->ingress_ifindex, 0);
}

char _license[] SEC("license") = "MIT";
