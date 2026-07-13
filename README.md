# Sushi-da OS

A Debian-based read-only kiosk operating system that boots directly into the
official Sushi-da website.

This repository currently contains the starter layout and permanent Codex
instructions. Implementation files are intentionally minimal placeholders.

## Default target

```text
https://sushida.net/play.html
```

## Architecture

- Debian 13 trixie
- Debian live-build
- systemd
- Cage
- Chromium
- NetworkManager
- PipeWire
- Read-only live root filesystem

Read `AGENTS.md` before implementation.

## Initial workflow

```bash
git init
git add .
git commit -m "Initialize Sushi-da kiosk OS project"
```

Then ask Codex to inspect `AGENTS.md`, implement the project in the documented
order, run all available tests, and report unverified hardware-dependent items
separately.
