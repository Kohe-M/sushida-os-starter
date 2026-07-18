# Threat model

## Security objective and limits

The primary objective is to prevent an ordinary local user from escaping the
kiosk UI or obtaining administrative privilege. The image reduces attack
surface; it is not a tamper-proof appliance and does not claim resistance to an
unrestricted physical attacker.

## 1. Accidental input and ordinary GUI escape

Controls include Cage as a single-application compositor, Chromium kiosk mode,
managed policy disabling developer tools/incognito/guest/sign-in/printing and
downloads, no desktop/display manager/terminal/file manager, masked gettys and
Ctrl+Alt+Delete target, and automatic systemd restart. Static configuration and
stubbed process behavior are verified. Every keyboard shortcut and normal
gameplay input still needs physical acceptance because software inspection
cannot prove keyboard/firmware/compositor behavior.

## 2. Deliberate kiosk escape by a local user

Navigation is default-deny in managed policy and independently validated by the
launcher and session helper. Mutable browser/session state is volatile. The
kiosk service has no shell-facing UI, SSH, general settings GUI, or second
application. The local Wi-Fi page is restricted to scanning and connecting; it
does not expose arbitrary NetworkManager settings, URLs, files, or commands.
Residual risks include Chromium/Cage/kernel vulnerabilities, unverified policy
runtime semantics, PID-reuse races in network recovery, USB/input
firmware behavior, and shortcuts not caught by the selected components.

## 3. Privilege escalation from the kiosk account

The `kiosk` account has a locked password, `/usr/sbin/nologin`, no sudo or
administrative groups, no persistent home, `NoNewPrivileges=true`, and empty
ambient/capability bounding sets. System services own lifecycle and terminate
the control group. Safe hardening avoids claims that would break DRM, input,
audio, NetworkManager, D-Bus, or Chromium's sandbox. Kernel, driver, browser,
and systemd vulnerabilities remain outside what configuration alone can prove.

## 4. Physical attacker

An attacker with unrestricted access can remove/replace storage, boot external
media, reset firmware, attach malicious peripherals, or open the case. The
software image cannot fully prevent this. Deployments must:

- set a UEFI administrator password;
- disable external/removable boot after installation;
- prioritize the internal kiosk disk;
- restrict firmware setup and Secure Boot changes;
- restrict physical access to storage, ports, and the case.

Secure Boot and firmware passwords are deployment controls, not repository
automation. The flash script never changes UEFI NVRAM or Secure Boot.

## Content and network boundary

The image opens only the official Sushi-da site in unmodified Chromium. It does
not copy, mirror, scrape, inject into, automate, or alter the game or traffic.
The offline page is a plain local network-unavailable notice with no Sushi-da
assets. The watcher derives connectivity only from NetworkManager and makes no
external probe requests.

Optional Wi-Fi credentials are root-only in the image but are extractable by
anyone who obtains the ISO. Use a dedicated low-privilege network credential
and control distribution of the artifact.

Credentials entered on-device persist in plaintext on the separate
`SUSHIDA-CFG` partition and are likewise extractable by anyone with the medium.
The unprivileged `wifi-setup` service can perform only three explicit
NetworkManager polkit actions and write its private configuration directory.
Its loopback HTTP surface still adds parser, NetworkManager, and local-browser
attack surface. Same-origin/CSRF checks, bounded inputs, argv-based process
execution without a shell, HTML escaping, service sandboxing, and a default-deny
Chromium policy reduce but do not eliminate vulnerabilities. Wi-Fi setup
re-scans the selected SSID in the backend and accepts only open or WPA Personal
networks. SSID and PSK data are carried by separate mode-`0600` temporary
descriptors (`/proc/self/fd/N`); WPA uses the exact
`802-11-wireless-security.psk:<password>` passwd-file record. They are not
placed in process arguments, HTTP responses, or the setup service's
stage/exit/reason logs. The profile is deleted after a failed activation and
its `psk-flags=1` setting prevents a password-bearing persistent NetworkManager
profile. This reduces local observation of secrets but does not protect the
plaintext credential stored in `SUSHIDA-CFG` from someone who can read the
device.

## Evidence interpretation

Static tests demonstrate repository configuration; BATS demonstrates shell
state machines with stubs; image validation demonstrates chroot contents;
artifact verification demonstrates release integrity; bounded QEMU provides
boot/display evidence. None alone proves resistance to a determined local or
physical attacker. Hardware acceptance results must identify device, firmware,
artifact SHA-256, procedure, and observed outcome.
