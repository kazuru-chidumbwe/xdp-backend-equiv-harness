.PHONY: deps corpus build topology topology-nic sweep-virtio sweep-nic smoke clean

CLANG ?= clang
LLVM_STRIP ?= llvm-strip
BPF_TARGET ?= bpf
ARCH ?= $(shell uname -m | sed 's/x86_64/x86/' | sed 's/aarch64/arm64/')
BPF_CFLAGS := -g -O2 -target $(BPF_TARGET) -D__TARGET_ARCH_$(ARCH) \
	-I/usr/include/$(shell uname -m)-linux-gnu
VETH_B ?= veth-b
NS_INJ ?= xdpequiv-inj
PROG ?= pass_drop
OBJ := build/prog_$(PROG).o

deps:
	@echo "Install: clang llvm libbpf-dev bpftool python3-scapy xdp-tools"

corpus:
	python3 corpus/generate_corpus.py

build: $(OBJ)

$(OBJ): programs/prog_$(PROG).c
	mkdir -p build
	$(CLANG) $(BPF_CFLAGS) -c $< -o $@
	$(LLVM_STRIP) -g $@

topology:
	bash harness/topology-veth.sh

topology-nic:
	bash harness/topology-dual-nic.sh

sweep-virtio:
	sudo PROFILE=virtio_vm bash harness/sweep.sh

sweep-nic:
	@test -n "$$NIC" || (echo "Set NIC=ens16f0 (XDP target)" && exit 1)
	sudo NIC=$$NIC INJ_IFACE=$${INJ_IFACE:-ens16f1} NS_INJ=xdpequiv-inj PROFILE=baremetal_nic bash harness/sweep.sh

smoke:
	bash scripts/smoke.sh

clean:
	rm -rf build captures manifests/*.json
