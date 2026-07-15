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
- default-deny navigation with only the official origin and local offline page
- NetworkManager wired DHCP, optional build-time Wi-Fi, and offline recovery
- PipeWire, WirePlumber, Mesa, DRM/GBM, Wayland, Intel/AMD firmware
- immutable SquashFS lower image with volatile runtime state and logs
- image-internal validation plus checksum, manifest, and metadata verification
- bounded BIOS/UEFI QEMU evidence collection and guarded removable-media writing

Hardware audio, GPU/WebGL acceleration, physical shortcut resistance, power
loss, and representative device compatibility require manual acceptance. Do
not infer those results from static tests or package presence.

## Quick start with Docker

```bash
make builder CONTAINER_ENGINE=docker
docker run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  sushida-os-builder:trixie make test
docker run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  sushida-os-builder:trixie make iso
```

Podman must use `--cgroup-manager=cgroupfs`; see [docs/build.md](docs/build.md)
for exact Linux, Podman, WSL2, and direct Debian commands.

A successful build publishes:

```text
artifacts/sushida-os-amd64.iso
artifacts/SHA256SUMS
artifacts/package-manifest.txt
artifacts/build-info.json
```

Verify with `make verify` inside the builder. Never run the flash script until
you have read [docs/installation.md](docs/installation.md), identified the
exact removable whole disk, and accepted that all data on it will be destroyed.
Codex and automated tests must not flash a real device.

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
