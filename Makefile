.PHONY: deps corpus build topology sweep-virtio sweep-nic clean

CLANG ?= clang
LLVM_STRIP ?= llvm-strip
BPF_TARGET ?= bpf
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
	$(CLANG) -g -O2 -target $(BPF_TARGET) -c $< -o $@
	$(LLVM_STRIP) -g $@

topology:
	bash harness/topology-veth.sh

sweep-virtio:
	sudo PROFILE=virtio_vm bash harness/sweep.sh

sweep-nic:
	@test -n "$$NIC" || (echo "Set NIC=eth0" && exit 1)
	sudo NIC=$$NIC PROFILE=baremetal_nic bash harness/sweep.sh

clean:
	rm -rf build captures manifests/*.json
