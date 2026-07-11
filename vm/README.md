# Vagrant lab (virtio native + generic XDP)

Pinned kernel box for virtio_vm profile reproduction.

## Requirements

- VirtualBox or libvirt
- Vagrant 2.4+
- 4 GB RAM for guest

## Usage

```bash
vagrant up
vagrant ssh
cd /opt/xdp-equiv
make corpus build
sudo make topology
# attach native/generic, inject, xdpdump — see main README
```

## Box notes

- Use `generic/ubuntu2404` or custom box with kernel 6.8.x
- Enable virtio-net; confirm native XDP: `ethtool -i eth0` then load test program
- Manifest profile field must be `virtio_vm`

Bare-metal sweep on host with real NIC is documented in `docs/VM-VS-BAREMETAL.md`.
