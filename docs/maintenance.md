# Maintenance

## Update and rebuild

The production image has no in-place persistent package update path. Update the
repository, review the diff and dependency changes, run `make test`, rebuild
with `make iso`, and retain all four artifacts together. Compare
`package-manifest.txt` and `build-info.json` with the deployed release before
installation. A successful static suite is not a substitute for QEMU and
hardware acceptance after Chromium, kernel, Mesa, firmware, Cage, or PipeWire
changes.

Wi-Fi changes require replacing the ignored `local/wifi.nmconnection` and
rebuilding. Credentials inside an ISO are extractable. Never commit the real
profile.

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
systemctl status sushida-kiosk.service sushida-network-watch.service --no-pager
```

These commands are not reachable from the kiosk UI.

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
