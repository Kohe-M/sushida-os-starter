# Maintenance

## Update and rebuild

The production image has no in-place persistent package update path. Update the
repository, review the diff and dependency changes, run `make test`, commit the
release source, rebuild
with `make iso`, and retain all four artifacts together. Compare
`package-manifest.txt` and `build-info.json` with the deployed release before
installation. A successful static suite is not a substitute for QEMU and
hardware acceptance after Chromium, kernel, Mesa, firmware, Cage, or PipeWire
changes.
The build masks `apt-daily.timer`, `apt-daily-upgrade.timer`, and their service
units in the production image. Package updates are made by rebuilding the ISO;
the live system does not perform background APT refreshes after boot.

Retain `build/iso-build.log` with the four artifacts. Its successful footer
records the build commit, timestamp, artifact path, and ISO SHA-256.

Build-time Wi-Fi changes can use the ignored `local/wifi.nmconnection` and a
rebuild. On-device credentials can instead be replaced from the setup screen
when the saved network cannot connect. Credentials in either the ISO or
`SUSHIDA-CFG` partition are extractable. Never commit a real profile.

## Rollback

Archive a previously accepted four-file artifact set by checksum. Rollback is
a fresh guarded write of that already verified ISO to the kiosk medium; there
is no mutable root state to revert. Repeat the relevant acceptance tests after
rollback. Do not overwrite the only known-good artifact set during a rebuild.

## Recovery

The read-only SquashFS lower image and volatile overlay normally restore a
known image state at reboot. If boot or kiosk startup fails, collect serial/QEMU
or physical-console evidence, verify the ISO checksum, and rebuild or reinstall
from a known-good artifact set. Production intentionally has no SSH server,
normal getty, terminal emulator, or debug shell. Do not add one merely for
recovery; use a separately controlled administrator maintenance medium and
respect the physical-security policy.

Runtime journal data is volatile. Collect it before reboot when an authorized
maintenance environment is available:

```bash
journalctl -b --no-pager
systemctl status sushida-kiosk.service sushida-network-watch.service \
  sushida-wifi-setup.service sushida-config-prepare.service \
  'var-lib-sushida\x2dconfig.mount' --no-pager
```

These commands are not reachable from the kiosk UI.

For a shutdown warning, collect the current-boot journal before reboot and look
for the exact unit or mount path. Warnings about the live root/overlay do not by
themselves prove corruption. A failure to unmount `/var/lib/sushida-config` is
material because it is the only writable persistent filesystem. Verify its
mount state and run clean reboot plus credential-survival acceptance before
redeployment; do not run filesystem repair from the production kiosk UI.

The production power-button path is handled by `systemd-logind`:
`HandlePowerKey=poweroff`, `HandlePowerKeyLongPress=ignore`, and
`PowerKeyIgnoreInhibited=yes`. There is no `acpid` or custom input-event
service, and the kiosk UI has no shutdown command. From an authorized
maintenance session, inspect `loginctl list-inhibitors` and confirm no low-level
power-key inhibitor is present. A single physical short press should reach the
normal `poweroff.target` path; firmware that does not publish an ACPI
power-switch event is unsupported until separately validated.

The non-invasive QEMU equivalent is bounded and uses only the per-run monitor
socket below `build/qemu`:

```bash
make test-qemu-powerdown
```

This starts BIOS and UEFI guests from private writable-media copies, waits for
kiosk startup, sends monitor `system_powerdown`, and requires natural guest
exit. It never calls host `poweroff`, `shutdown`, or `reboot`. The checker
requires the run's Git commit, ISO SHA-256, `SHA256SUMS`, and `build-info.json`
to describe the current clean checkout. Review each
`build/qemu/*-powerdown/serial.log` for explicit `Mounted` and `Unmounted`
evidence for `SUSHIDA-CFG`, as well as the absence of failures for that unit,
before treating the test as passed. live-boot may report an unrelated
`/run/live/medium` busy-unmount during QEMU teardown; that does not replace the
required positive `SUSHIDA-CFG` evidence.

## Volatile diagnostics

The production image includes `sushida-diagnostics`, but it is not linked from
the kiosk UI and does not grant privilege. An administrator can run it from a
controlled maintenance environment:

```bash
sushida-diagnostics
sushida-diagnostics --output /run/my-report.txt
```

The default report is mode `0600` below `/run/sushida-os/diagnostics` and is
lost at reboot. Existing files and symlinked output directories are rejected.
The report covers DRM drivers and connectors, GBM/EGL/Wayland libraries,
Cage/Chromium, the configured WebGL boundary, PipeWire, ALSA, and
NetworkManager state. It deliberately omits SSIDs, connection profiles,
network addresses, MAC addresses, EDID, process command lines, environment
variables, and credentials. Common token, password, MAC, UUID, and URL-query
forms are redacted as a second boundary.

`RUNTIME_WEBGL_STATUS=UNVERIFIED` is expected: confirming Chromium's effective
GPU/WebGL backend requires the controlled hardware acceptance procedure. A
diagnostics report alone is not evidence that rendering or audio output works.

## Cleaning generated state

Container builds produce root-owned mount trees. Run `make clean` or
`make distclean` in the same privileged builder container (or with `sudo` on a
direct Debian builder). Cleanup is restricted to fixed repository paths;
`local/` and source files are preserved.
