SHELL := /bin/bash
PYTHON ?= python3
CONTAINER_ENGINE ?= docker
BUILDER_IMAGE ?= sushida-os-builder
BUILDER_TAG ?= trixie
CONTAINER_ENGINE_NAME := $(notdir $(CONTAINER_ENGINE))
CONTAINER_ENGINE_ARGS := $(if $(filter podman,$(CONTAINER_ENGINE_NAME)),--cgroup-manager=cgroupfs,)

.PHONY: builder configure iso test test-static test-shell test-contracts check-contracts test-qemu test-qemu-boot test-qemu-runtime test-qemu-powerdown qemu verify clean distclean help doctor doctor-build doctor-qemu ci container-test container-shell container-configure container-iso container-verify

help:
	@echo 'Sushi-da OS development targets'
	@echo ''
	@echo '  Common (no container required):'
	@echo '    make test          Run static tests then shell tests'
	@echo '    make test-static   Python/pytest static tests'
	@echo '    make test-shell    ShellCheck + BATS'
	@echo '    make test-contracts Contract schema + fixture tests'
	@echo '    make check-contracts  Check contracts against current source'
	@echo '    make doctor        Check host prerequisites (profile: test)'
	@echo '    make doctor-build  Check prerequisites for ISO build'
	@echo '    make doctor-qemu   Check prerequisites for QEMU tests'
	@echo '    make ci            Contracts + test + git diff'
	@echo ''
	@echo '  Container (Docker or Podman):'
	@echo '    make builder             Build the container image'
	@echo '    make container-test      Run make test inside container'
	@echo '    make container-shell     Run shell tests inside container'
	@echo '    make container-configure Configure live-build inside container'
	@echo '    make container-iso       Build release ISO (--privileged)'
	@echo '    make container-verify    Verify release artifacts in container'
	@echo ''
	@echo '  QEMU (requires KVM):'
	@echo '    make test-qemu-boot      Bootloader production test'
	@echo '    make test-qemu-runtime   Direct-kernel software-renderer test'
	@echo '    make test-qemu           Both QEMU tests'
	@echo '    make test-qemu-powerdown QEMU powerdown test'
	@echo ''
	@echo '  ISO release:'
	@echo '    make configure  Stage live-build config'
	@echo '    make iso        Build release ISO'
	@echo '    make verify     Verify release artifacts'
	@echo ''
	@echo '  Maintenance:'
	@echo '    make clean      Remove build artefacts'
	@echo '    make distclean  Full cleanup'

builder:
	$(CONTAINER_ENGINE) $(CONTAINER_ENGINE_ARGS) build -t $(BUILDER_IMAGE):$(BUILDER_TAG) -f builder/Dockerfile .

configure:
	./live-build/auto/config

iso:
	./scripts/build.sh

test: test-static test-contracts test-shell

test-static:
	$(PYTHON) -m pytest tests/static/ --strict-markers -ra

test-contracts:
	$(PYTHON) -m pytest tests/contracts/ --strict-markers -ra

check-contracts:
	$(PYTHON) tools/check-contracts.py

test-shell:
	shellcheck -S warning $$(./scripts/shellcheck-targets.sh)
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

doctor:
	./scripts/doctor.sh test

doctor-build:
	./scripts/doctor.sh build

doctor-qemu:
	./scripts/doctor.sh qemu

ci: test check-contracts
	git diff --check

container-test:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) BUILDER_IMAGE=$(BUILDER_IMAGE):$(BUILDER_TAG) ./scripts/container-run.sh test

container-shell:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) BUILDER_IMAGE=$(BUILDER_IMAGE):$(BUILDER_TAG) ./scripts/container-run.sh shell

container-configure:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) BUILDER_IMAGE=$(BUILDER_IMAGE):$(BUILDER_TAG) ./scripts/container-run.sh configure

container-iso:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) BUILDER_IMAGE=$(BUILDER_IMAGE):$(BUILDER_TAG) ./scripts/container-run.sh iso

container-verify:
	CONTAINER_ENGINE=$(CONTAINER_ENGINE) BUILDER_IMAGE=$(BUILDER_IMAGE):$(BUILDER_TAG) ./scripts/container-run.sh verify
