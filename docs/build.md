# Build and test

## Builder privileges and isolation

The supported build environment is Debian 13 trixie. Debian live-build mounts
`proc`, `sysfs`, and device filesystems and creates bootable filesystem images,
so the container build runs with `--privileged`. That privilege applies to the
builder container; repository scripts do not change host GRUB, UEFI variables,
partitions, filesystems, network configuration, `/etc`, or users. The repository
is the only host path mounted for writing. Container-engine image/layer storage
is the normal additional engine-managed state.

Generated trees are below `build/`; release files are below `artifacts/`.
Machine-local Wi-Fi configuration is below ignored `local/`.

## Docker on Linux

```bash
make builder CONTAINER_ENGINE=docker
docker run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  sushida-os-builder:trixie make test
docker run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  sushida-os-builder:trixie make iso
docker run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  sushida-os-builder:trixie make verify
```

## Podman on Linux

Every Podman invocation uses the required cgroup manager explicitly:

```bash
make builder CONTAINER_ENGINE=podman
podman --cgroup-manager=cgroupfs run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  localhost/sushida-os-builder:trixie make test
podman --cgroup-manager=cgroupfs run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  localhost/sushida-os-builder:trixie make iso
podman --cgroup-manager=cgroupfs run --rm --privileged \
  -v "$PWD:/sushida-os" -w /sushida-os \
  localhost/sushida-os-builder:trixie make verify
```

Rootless Podman may still be unable to provide live-build mounts on some
hosts. Use an appropriately isolated rootful builder if the engine rejects the
required mount operations; do not weaken image validation to work around it.

## Docker Engine inside WSL2

Run from PowerShell with Docker or Podman already available inside the selected
WSL2 distribution:

```powershell
.\scripts\windows\Build-In-WSL.ps1 -Engine docker
.\scripts\windows\Build-In-WSL.ps1 -Engine podman
```

The wrapper translates the repository path with `wslpath`, builds the Debian
builder, and invokes `make iso` inside it. Docker Desktop filesystem sharing is
not required when the repository and engine both reside inside WSL2. Building
on a Windows-mounted filesystem can be slower and may not preserve Linux modes
as reliably as the WSL2 filesystem.

For the interactive QEMU PowerShell wrapper, install `qemu-system-x86`, the
QEMU GUI display module, `ovmf`, and `socat` in WSL2, then run:

```powershell
.\scripts\windows\Run-Qemu.ps1 -Firmware uefi -Offline
```

## Direct Debian 13 host

Install the packages listed in `builder/Dockerfile`, then run the privileged
image build directly:

```bash
make test
sudo make iso
sudo make verify
```

Direct live-build requires root for temporary mounts and device nodes. It does
not authorize writing a real disk. Because container/direct builds can leave
root-owned generated files, run cleanup in the same privileged environment:

```bash
sudo make clean
sudo make distclean
```

`clean` removes disposable `build/` state and preserves release artifacts.
`distclean` additionally removes only the four named release artifacts. Both
reject symlinked generated roots and preserve `local/` secrets.

## Configuration and optional Wi-Fi

`make configure` creates repeatable live-build state without producing an ISO.
If `local/wifi.nmconnection` exists, it is staged mode `0600`; otherwise the
image contains no Wi-Fi profile. See `local/README.md` and
`docs/networking.md`. Anyone who obtains an ISO can extract embedded Wi-Fi
credentials.

## Targets and evidence

| Target | Result |
|---|---|
| `make builder` | Build Debian 13 tool image |
| `make configure` | Generate live-build configuration |
| `make test` | Run static pytest, ShellCheck, and all BATS; no QEMU |
| `make test-static` | Run repository static tests |
| `make test-shell` | Run ShellCheck and all BATS |
| `make iso` | Build, validate, verify, and publish four artifacts |
| `make verify` | Recheck checksum, metadata, manifest, ISO, and SquashFS paths |
| `make qemu` | Interactive BIOS boot of the release ISO |
| `make test-qemu` | Bounded offline BIOS and UEFI runs with serial/PNG/PPM evidence |
| `make clean` | Remove disposable build/QEMU state |
| `make distclean` | Also remove the four known release artifacts |

QEMU evidence is written under `build/qemu/`. `make test-qemu` explicitly
selects the non-default `QEMU smoke test` boot entry, which uses wlroots' pixman
renderer and serial logging only for emulation. The normal production entry
continues to require a hardware-capable renderer. Both smoke entries also
select Chromium's bundled ANGLE SwiftShader backend because the capturable
emulated adapters have no accelerated render node; this marker is absent from
the production entry. Automated checks prove only
that the intended entry booted, QEMU remained alive for the observation
interval, the kiosk services and graphical target were reached, PNG and PPM
captures were created, the frame is neither blank white nor blank black, and no
normal serial login prompt appeared. The contrast check does not recognize UI
text, but it rejects bright foreground confined to a partial scanout and the
runner retries incomplete captures at low frequency. The reviewed PNG is
derived from the exact validated PPM frame so the two evidence files cannot
capture different display updates. Screenshots and hardware behavior still
need explicit review. The
default observation interval is 300 seconds for both BIOS and UEFI. Slow
TCG-only builders need this bound for Chromium's first rendered frame; shorter
intervals have produced intermittent blank captures after the kiosk service
started. Set `SUSHIDA_QEMU_BIOS_DURATION` or
`SUSHIDA_QEMU_UEFI_DURATION` to override one path; the legacy
`SUSHIDA_QEMU_DURATION` override still applies to both.
