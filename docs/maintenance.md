# Maintenance

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

Updates, rebuilds, rollback, and recovery are completed in Task 20.
