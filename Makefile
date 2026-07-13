SHELL := /bin/bash
PYTHON ?= python3

.PHONY: builder configure iso test test-static test-shell test-qemu qemu verify clean distclean

builder:
	@echo "TODO: Build the Debian 13 live-build container."

configure:
	@echo "TODO: Configure live-build."

iso:
	@echo "TODO: Build artifacts/sushida-os-amd64.iso."
	@exit 1

test: test-static test-shell
	@echo "TODO: Add QEMU tests when supported."

test-static:
	$(PYTHON) -m pytest tests/static/

test-shell:
	@echo "TODO: Run ShellCheck and BATS."

test-qemu:
	@echo "TODO: Run QEMU smoke tests."
	@exit 1

qemu:
	@echo "TODO: Boot the generated ISO in QEMU."
	@exit 1

verify:
	@echo "TODO: Verify ISO checksum and contents."
	@exit 1

clean:
	@echo "TODO: Remove disposable build state."

distclean: clean
	@echo "TODO: Remove all generated artifacts."
