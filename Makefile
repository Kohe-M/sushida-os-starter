SHELL := /bin/bash
PYTHON ?= python3
CONTAINER_ENGINE ?= docker
BUILDER_IMAGE ?= sushida-os-builder
BUILDER_TAG ?= trixie

.PHONY: builder configure iso test test-static test-shell test-qemu qemu verify clean distclean

builder:
	$(CONTAINER_ENGINE) build -t $(BUILDER_IMAGE):$(BUILDER_TAG) -f builder/Dockerfile .

configure:
	./live-build/auto/config

iso:
	./scripts/build.sh

test: test-static test-shell
	@echo "TODO: Add QEMU tests when supported."

test-static:
	$(PYTHON) -m pytest tests/static/

test-shell:
	@echo "TODO: Run ShellCheck and BATS."

test-qemu:
	./scripts/smoke-test.sh

qemu:
	./scripts/run-qemu.sh

verify:
	./scripts/verify-iso.sh

clean:
	./scripts/clean.sh clean

distclean:
	./scripts/clean.sh distclean
