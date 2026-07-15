# Hardware compatibility

## Primary supported targets

- Intel integrated graphics (Iris Xe, UHD Graphics, etc.) with Mesa
- AMD integrated graphics (Radeon Graphics in Ryzen APUs) with Mesa

## Audio

- PipeWire (started by the kiosk launcher before Cage/Chromium)
- WirePlumber session manager
- PipeWire-Pulse compatibility layer
- HDMI/DisplayPort audio via GPU (requires hardware)
- Analog audio via built-in Intel/AMD HDA controllers (requires hardware)

## Boot

- UEFI and legacy BIOS
- Debian 13 live ISO amd64

## Untested

The following have NOT been verified in this environment and require
physical-hardware validation:

- Intel Arc discrete GPUs
- AMD Radeon discrete GPUs (RX 6000/7000 series)
- NVIDIA GPUs (not supported -- use Intel/AMD integrated graphics)
- USB audio devices
- Bluetooth audio
- Microphone capture
- DisplayPort daisy-chaining or multi-monitor
- HDR output
- Secure Boot
- specific laptop models
- external GPU enclosures
