.PHONY: deps corpus build topology topology-nic sweep-virtio sweep-nic smoke baremetal-sweep validate-comparator clean

PROGS := pass_drop metadata_test vlan_probe

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

build-all:
	@for p in $(PROGS); do $(MAKE) build PROG=$$p; done

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

sweep-nic: baremetal-sweep

smoke:
	bash scripts/smoke.sh

validate-comparator:
	bash scripts/comparator-sensitivity.sh

baremetal-sweep:
	@test -n "$$NIC" || (echo "Set NIC=ens16f0" && exit 1)
	sudo NIC=$$NIC INJ_IFACE=$${INJ_IFACE:-ens16f1} bash scripts/baremetal-sweep.sh

clean:
	rm -rf build captures manifests/*.json
