SHELL := /bin/bash
PYTHON ?= python3
CONTAINER_ENGINE ?= docker
BUILDER_IMAGE ?= sushida-os-builder
BUILDER_TAG ?= trixie
CONTAINER_ENGINE_NAME := $(notdir $(CONTAINER_ENGINE))
CONTAINER_ENGINE_ARGS := $(if $(filter podman,$(CONTAINER_ENGINE_NAME)),--cgroup-manager=cgroupfs,)
# Only pass files whose shebang is a POSIX shell to ShellCheck.  Some
# extensionless production helpers (notably the Python Wi-Fi backend) are
# executable too, but ShellCheck must not parse them as shell.
EXECUTABLE_SHELL_FILES := $(shell \
	git ls-files --stage | awk '$$1 == "100755" {print $$4}' | \
	xargs -r grep -lE '^(#!/bin/(ba)?sh|#!/usr/bin/(env )?(ba)?sh|#!/usr/bin/dash)' 2>/dev/null)

.PHONY: builder configure iso test test-static test-shell test-qemu qemu verify clean distclean

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
	shellcheck -S warning $(EXECUTABLE_SHELL_FILES) tests/shell/*.bats
	bats tests/shell/*.bats

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
