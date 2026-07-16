# Hardware compatibility

## Intended targets

- amd64 systems with legacy BIOS or UEFI
- Intel integrated graphics with Mesa and `firmware-intel-graphics`
- AMD integrated graphics with Mesa and `firmware-amd-graphics`
- Intel Wi-Fi (`firmware-iwlwifi`) and common Realtek devices (`firmware-realtek`)
- HDMI/DisplayPort or HDA analog audio through PipeWire/WirePlumber

The image includes DRM, GBM, EGL/GLES, Wayland, Mesa DRI/VA, PipeWire,
PipeWire-Pulse, and standard keyboard data. Production does not pass
`--disable-gpu`, `--disable-webgl`, or `--no-sandbox`, and does not force
software rendering. The normal boot entry preserves that boundary. The bounded
QEMU runner explicitly selects a separate `QEMU smoke test` boot entry that
uses the pixman software renderer and enables a serial console without a getty.
QEMU uses emulated `virtio-vga` for BIOS and standard VGA/bochs DRM for UEFI.
The explicit smoke entries select Chromium's bundled ANGLE SwiftShader backend
because the emulated adapters have no accelerated render node. These
software-rendering settings are absent from the production entry. QEMU uses TCG
when KVM is absent; that is not evidence for physical GPU performance.

NVIDIA proprietary drivers are not included or supported. Xwayland may appear
as a Debian Cage dependency; no Xorg desktop, display manager, or ordinary X11
session is configured.

## Evidence to collect per representative machine

Record the hardware model, firmware version/settings, display/audio connection,
input devices, network adapter, artifact SHA-256, and test date. Preserve the
diagnostics report and acceptance worksheet without Wi-Fi credentials.

- **DRM/GBM/EGL/WebGL:** save `sushida-diagnostics`, inspect Chromium's
  controlled `chrome://gpu` view, and record renderer/backend, errors, and a
  screenshot. Do not enable remote debugging or weaken URL policy in production.
- **Audio:** record selected physical output, whether game audio is audible,
  PipeWire/WirePlumber state, and failures for HDMI/DP/analog/USB separately.
- **Input latency:** use a repeatable camera or external event/display capture,
  preserve raw timestamps/video, and compare candidate releases on identical
  hardware. The project does not invent a universal pass threshold; deployment
  owners must define one before testing.
- **Power loss:** use sacrificial test hardware, interrupt power at documented
  phases, then record boot, filesystem, kiosk, and runtime-state outcome. Define
  the number of cycles before execution; do not infer durability from one boot.
- **Networking:** record wired DHCP, optional Wi-Fi association, offline page,
  and recovery without including SSID/PSK in public evidence.
- **Escape controls:** execute every shortcut and gameplay-input row in
  `docs/acceptance-tests.md` with the actual keyboard/firmware.

## Current verification boundary

Repository static/BATS/image checks confirm package/configuration presence and
forbidden-flag absence. QEMU automation captures BIOS/UEFI screenshots and
serial logs and rejects blank white/black frames, but effective
Cage/Chromium/offline UI must still be reviewed from those images. Audio
playback, Chromium WebGL/GPU acceleration, Intel/AMD DRM/GBM/EGL,
HDMI/DP/analog audio, physical shortcut resistance, sudden-power-loss recovery,
Secure Boot, and representative hardware are unverified until a completed
worksheet records them.

Additional unverified targets include Intel Arc and AMD discrete GPUs, USB and
Bluetooth audio, microphones, multi-monitor/daisy-chain/HDR, laptop-specific
hotkeys, docks, and external GPU enclosures.
