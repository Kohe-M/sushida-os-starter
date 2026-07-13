# Architecture

This is a starter document.

The intended runtime chain is:

```text
bootloader
  -> Debian live system
  -> systemd
  -> sushida-kiosk.service
  -> Cage
  -> Chromium kiosk window
  -> official Sushi-da URL
```

Mutable browser and session state must be stored under `/run` or another tmpfs.
The root filesystem remains read-only.

Codex must replace this starter text with the implemented boot, service,
network recovery, audio, graphics, and shutdown flows.
