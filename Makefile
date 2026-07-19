SHELL := /bin/bash
PYTHON ?= python3
CONTAINER_ENGINE ?= docker
BUILDER_IMAGE ?= sushida-os-builder
BUILDER_TAG ?= trixie
CONTAINER_ENGINE_NAME := $(notdir $(CONTAINER_ENGINE))
CONTAINER_ENGINE_ARGS := $(if $(filter podman,$(CONTAINER_ENGINE_NAME)),--cgroup-manager=cgroupfs,)

.PHONY: builder configure iso test test-static test-shell test-qemu test-qemu-boot test-qemu-runtime test-qemu-powerdown qemu verify clean distclean

builder:
	$(CONTAINER_ENGINE) $(CONTAINER_ENGINE_ARGS) build -t $(BUILDER_IMAGE):$(BUILDER_TAG) -f builder/Dockerfile .

configure:
	./live-build/auto/config

iso:
	./scripts/build.sh

test: test-static test-shell

test-static:
	$(PYTHON) -m pytest tests/static/

test-shell:
	shellcheck -S warning $$(./scripts/shellcheck-targets.sh) tests/shell/*.bats
	bats tests/shell/*.bats

test-qemu: test-qemu-boot test-qemu-runtime

test-qemu-boot:
	./scripts/boot-test.sh

test-qemu-runtime:
	./scripts/smoke-test.sh

test-qemu-powerdown:
	./scripts/powerdown-test.sh

qemu:
	./scripts/run-qemu.sh

verify:
	./scripts/verify-iso.sh

clean:
	./scripts/clean.sh clean

distclean:
	./scripts/clean.sh distclean
