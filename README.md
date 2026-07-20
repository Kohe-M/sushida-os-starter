# Sushi-da OS

Sushi-da OS builds a Debian 13 amd64 read-only live image that starts the
official Sushi-da website in an unprivileged Cage/Chromium kiosk session. It
does not contain or modify Sushi-da game content.

Default URL:

```text
https://sushida.net/play.html
```

## Implemented system

- Debian live-build hybrid ISO for legacy BIOS and UEFI
- systemd-managed `kiosk` account with no password, shell, sudo, or persistent home
- Cage single-application Wayland session and Debian Chromium managed policy
- default-deny navigation with only the official origin and constrained local pages
- NetworkManager wired DHCP and on-device Wi-Fi setup with low-frequency recovery
- PipeWire, WirePlumber, Mesa, DRM/GBM, Wayland, Intel/AMD firmware
- immutable SquashFS lower image, volatile browser state, and an isolated
  64 MiB credential partition
- image-internal validation plus checksum, manifest, and metadata verification
- bounded BIOS/UEFI QEMU evidence collection and guarded removable-media writing

Hardware audio, GPU/WebGL acceleration, physical shortcut resistance, power
loss, and representative device compatibility require manual acceptance. Do
not infer those results from static tests or package presence.

## Quick start (host tools)

```bash
make doctor           # check host prerequisites
make test             # run static tests, contract tests, shell tests
make check-contracts  # verify contracts against current source
make ci               # non-destructive checks (test + check-contracts + git diff)
```

## Quick start (Docker/Podman)

```bash
make builder CONTAINER_ENGINE=docker
make container-test   # or: make test  inside the builder container
make container-iso    # --privileged; builds the release ISO
```

Normal tests (`make test`, `make container-test`) never use `--privileged`.
ISO builds require `--privileged` for loopback mounts (container mode only).
QEMU and flash are separate, manually invoked operations.
See [docs/build.md](docs/build.md) for Podman, WSL2, and direct Debian commands.

A successful build publishes:

```text
artifacts/sushida-os-amd64.iso
artifacts/SHA256SUMS
artifacts/package-manifest.txt
artifacts/build-info.json
```

On first boot, wired networking is tried automatically. If no connection is
available after 15 seconds, the kiosk displays a local Wi-Fi selection screen.
Only the Wi-Fi credential persists; obtaining the ISO or USB device permits
credential extraction. See [Networking](docs/networking.md) for the exact
security and hardware-support boundary.

Verify with `make verify` inside the builder. Never run the flash script until
you have read [docs/installation.md](docs/installation.md), identified the
exact `/dev/disk/by-id/usb-*` symlink for a supported USB flash drive, and
accepted that all data on it will be destroyed. Raw `/dev/sdX` paths and USB
SSDs are not supported. Codex and automated tests must not flash a real device.

## Documentation

- [Architecture](docs/architecture.md)
- [Build and test](docs/build.md)
- [Installation](docs/installation.md)
- [Networking](docs/networking.md)
- [Maintenance and diagnostics](docs/maintenance.md)
- [Threat model](docs/threat-model.md)
- [Hardware compatibility](docs/hardware-compatibility.md)
- [Acceptance tests](docs/acceptance-tests.md)

`AGENTS.md` is the authoritative project and safety contract.
