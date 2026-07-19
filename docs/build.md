# Build and test

## Developer workflow

All development commands are available through `make` targets.  The
`scripts/container-run.sh` wrapper provides a unified entry point for
Docker and Podman so build instructions do not need to repeat engine-
specific `docker run` flags.

### Host prerequisites

```bash
make doctor           # check git, python3, pytest, shellcheck, bats
make doctor-build     # also check container engine and builder image
make doctor-qemu      # also check QEMU, OVMF, socat
```

### Local testing (no container)

```bash
make test-static      # 598+ pytest checks
make test-shell       # ShellCheck + 143+ BATS tests
make test             # both of the above
make ci               # test + git diff --check
```

### Container testing

```bash
make builder CONTAINER_ENGINE=docker    # build the builder image
make container-test                     # run make test inside container (non-privileged)
make container-shell                    # shell tests only
make container-configure                # stage live-build config
make container-iso                      # build release ISO (--privileged)
make container-verify                   # verify release artifacts
```

The `container-*` targets use `scripts/container-run.sh`, which:

- adds `--cgroup-manager=cgroupfs` automatically for Podman;
- adds `--privileged` only for the `iso` mode;
- maps the host UID/GID so test artifacts are not owned by root;
- sets `PYTHONDONTWRITEBYTECODE=1` to avoid left-over bytecode caches.

### Privilege boundary

| Operation | Privilege needed | Can harm host? |
|---|---|---|
| `make test`, `make ci` | None | No |
| `make container-test` | Container engine only | No |
| `make iso` (direct host) | Root | Yes — filesystem mounts |
| `make container-iso` | `--privileged` in container | No (container only) |
| `make test-qemu` | Container engine + KVM group | No |
| `scripts/flash.sh` | Root + explicit device confirmation | Yes — reads after write |

QEMU tests and ISO builds are never included in `make ci` or any
non-privileged target.

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
Release ISO builds require a clean Git worktree. Commit source and test changes
before `make iso`; the artifact verifier records and checks the exact source
commit and rejects dirty or stale metadata.
Each `make iso` attempt starts a fresh `build/iso-build.log`. A successful log
ends with `BUILD_RESULT=success`, the source commit, build timestamp, artifact
path, and the ISO SHA-256. A failed attempt therefore cannot leave an older
successful log beside newer or incomplete artifacts.

The builder image context is restricted to `builder/Dockerfile` and
`builder/entrypoint.sh` by `.dockerignore` and `.containerignore`; `.git`,
`build/`, `artifacts/`, and `local/` secrets are never sent to Docker or Podman.

## Docker on Linux

All container operations go through the `container-*` Make targets, which
are implemented by `scripts/container-run.sh`.  The wrapper adds
`--cgroup-manager=cgroupfs` automatically for Podman and `--privileged`
only for the `iso` mode:

```bash
make builder CONTAINER_ENGINE=docker
make container-test        # non-privileged
make container-iso         # --privileged
make container-verify      # non-privileged
```

Direct `docker run` is not needed for normal development; see
`scripts/container-run.sh` for the exact invocation used.

## Podman on Linux

Podman uses the same wrapper with `CONTAINER_ENGINE=podman`:

```bash
make builder CONTAINER_ENGINE=podman
make container-test        # adds --cgroup-manager=cgroupfs automatically
make container-iso         # adds --privileged + --cgroup-manager=cgroupfs
make container-verify
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
image contains no pre-provisioned Wi-Fi profile. Independently, `make iso`
appends a blank fixed-size ext4 partition labelled `SUSHIDA-CFG` for credentials
entered through the on-device setup screen. Artifact verification checks its
partition number, size, type, label, and filesystem type. See `local/README.md`
and `docs/networking.md`. Anyone who obtains an ISO or written medium can
extract stored credentials.

## Targets and evidence

| Target | Result |
|---|---|
| `make builder` | Build Debian 13 tool image |
| `make configure` | Generate live-build configuration |
| `make test` | Run static pytest, ShellCheck, and all BATS; no QEMU |
| `make test-static` | Run repository static tests |
| `make test-shell` | Run ShellCheck and all BATS |
| `make iso` | Build, validate, verify, publish four artifacts, and retain `build/iso-build.log` |
| `make verify` | Recheck checksum, metadata, manifest, ISO, and SquashFS paths |
| `make qemu` | Interactive BIOS boot of the release ISO |
| `make test-qemu` | Bounded offline BIOS and UEFI writable-copy runs with serial/PNG/PPM evidence |
| `make test-qemu-powerdown` | Bounded BIOS and UEFI monitor `system_powerdown` runs; requires natural guest exit and clean config unmount evidence |
| `make clean` | Remove disposable build/QEMU state |
| `make distclean` | Also remove the four known release artifacts |

QEMU evidence is written under `build/qemu/`. Offline runs attach no guest
network interface. The non-default QEMU entry forces the static local offline
page because Chromium's network service is not reliable enough under slow
TCG-only emulation to make the loopback setup UI a release gate. This marker is
paired with the QEMU-only renderer markers and is absent from the production
entry. `make test-qemu` copies the
release ISO to a repository-local `writable-media.img`, boots that copy as a
virtio disk, and never attaches a host block device. This permits the appended
`SUSHIDA-CFG` filesystem to mount read-write without modifying the release
artifact. It also explicitly
selects the non-default `QEMU smoke test` boot entry, which uses wlroots' pixman
renderer and serial logging only for emulation. The normal production entry
continues to require a hardware-capable renderer. Both smoke entries also
select Chromium's bundled ANGLE SwiftShader backend with Chromium's explicit
QEMU-only unsafe-SwiftShader opt-in because the capturable emulated adapters
have no accelerated render node; this marker is absent from the production
entry. Automated checks prove only
that the intended entry booted, QEMU remained alive for the observation
interval, the config mount, Wi-Fi setup, kiosk services, and graphical target
were reached, PNG and PPM
captures were created, the frame is neither blank white nor blank black, and no
normal serial login prompt appeared. The contrast check does not recognize UI
text, but it rejects bright foreground confined to a partial scanout and the
runner retries incomplete captures at low frequency. The reviewed PNG is
derived from the exact validated PPM frame so the two evidence files cannot
capture different display updates. The on-device Wi-Fi setup UI, scanning,
association, and recovery remain physical-hardware checks; QEMU only verifies
that their config mount and services start without a detected error.
Screenshots and hardware behavior still need explicit review. The
default observation interval is 300 seconds for both BIOS and UEFI. Slow
TCG-only builders need this bound for Chromium's first rendered frame; shorter
intervals have produced intermittent blank captures after the kiosk service
started. Set `SUSHIDA_QEMU_BIOS_DURATION` or
`SUSHIDA_QEMU_UEFI_DURATION` to override one path; the legacy
`SUSHIDA_QEMU_DURATION` override still applies to both.
The dedicated `make test-qemu-powerdown` path uses
`SUSHIDA_QEMU_POWERDOWN_TIMEOUT` (180 seconds by default), starts from a private
writable-media copy, and restricts the monitor socket to the selected
`build/qemu/*-powerdown` run directory. Its result is accepted only when
`build-info.json`, `SHA256SUMS`, the ISO hash, and the current clean Git HEAD
agree, and the serial log contains positive `Mounted` and `Unmounted` evidence
for `SUSHIDA-CFG`. It does not issue any power operation to the host.
