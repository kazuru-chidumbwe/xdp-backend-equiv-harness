// SPDX-License-Identifier: MIT
// prog_pass_drop: disposition-only baseline + negative control.
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>

#define TEST_MAGIC 0x58545045u /* XTPE */

static __always_inline int parse_ipv4(void *data, void *data_end, __u16 *sport)
{
    struct iphdr *iph = data;
    if ((void *)(iph + 1) > data_end)
        return -1;
    if (iph->protocol != IPPROTO_TCP)
        return 0;
    struct tcphdr *tcph = (void *)iph + (iph->ihl * 4);
    if ((void *)(tcph + 1) > data_end)
        return -1;
    *sport = bpf_ntohs(tcph->source);
    return 1;
}

SEC("xdp")
int xdp_pass_drop(struct xdp_md *ctx)
{
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;

    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end)
        return XDP_DROP;

    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return XDP_PASS;

    __u16 sport = 0;
    int tcp = parse_ipv4((void *)(eth + 1), data_end, &sport);
    if (tcp < 0)
        return XDP_DROP;

    /* Drop test IDs ending in 0x..05 (frag case) */
    if (sport == 0xA005)
        return XDP_DROP;

  return XDP_PASS;
}

char _license[] SEC("license") = "MIT";
