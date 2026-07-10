# Release tags

Annotated tags mark reproducible anchors. **`main` may advance** after a tag — always `git checkout <tag>` when reproducing a cited result.

| Tag | Commit | Purpose |
| --- | --- | --- |
| [`blog-x01-2026-07`](https://github.com/kazuru-chidumbwe/xdp-backend-equiv-harness/tree/blog-x01-2026-07) | `985df03` | **Dev.to X01a essay** — virtio smoke + harness blueprint |

## Quick checkout

```bash
git checkout blog-x01-2026-07
make corpus && make build
sudo make topology && sudo make sweep-virtio

# Bare-metal (loop cable required) — see docs/BAREMETAL-LAB.md
sudo NIC=ens16f0 INJ_IFACE=ens16f1 make baremetal-sweep
```

## Tag policy

- **Blog citations** → `blog-x01-2026-07` only (not `main`).
- New tags when reproducibility boundary changes — not on every doc commit.
