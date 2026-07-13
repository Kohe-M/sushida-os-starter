# AGENTS.md

## 1. Project mission

This repository builds an amd64 Linux kiosk image dedicated to displaying the
official Sushi-da website.

The target user experience is:

1. The machine powers on.
2. The bootloader proceeds automatically.
3. No normal desktop or login screen appears.
4. A dedicated unprivileged user launches Cage.
5. Chromium opens the official Sushi-da play page in full-screen kiosk mode.
6. The user cannot switch to another application, terminal, desktop, browser
   settings page, developer tools, or arbitrary URL.
7. If Chromium or Cage exits, systemd automatically starts the kiosk again.
8. Unexpected power loss must not corrupt the normal operating state.

Default URL:

```text
https://sushida.net/play.html
```

The URL must be configurable through:

```text
/etc/sushida-os/config.env
```

## 2. Mandatory architecture

Do not build a kernel or operating system from scratch.

Use this architecture unless a documented technical blocker requires a change:

- Base distribution: Debian 13 trixie
- Target architecture: amd64
- Image generation: Debian live-build
- Init and service management: systemd
- Display protocol: Wayland
- Kiosk compositor: Cage
- Browser: Debian Chromium
- Network management: NetworkManager
- Audio: PipeWire or the smallest stable Debian 13-compatible stack
- Root filesystem: read-only live system
- Browser profile, caches, temporary files, and runtime state: tmpfs or `/run`
- Ordinary desktop environment: prohibited
- Display manager: prohibited
- SSH server: prohibited
- Terminal emulator: prohibited
- File manager: prohibited

Intel and AMD integrated graphics with Mesa are the primary supported targets.
Do not depend on NVIDIA proprietary drivers.

## 3. Legal and content constraints

The operating system may only open the official Sushi-da website in an
unmodified Chromium browser.

Never:

- Copy Sushi-da HTML, JavaScript, WebAssembly, images, fonts, audio, or other
  game assets into this repository or generated image.
- Create or bundle an offline copy of Sushi-da.
- Mirror, scrape, reverse-engineer, or redistribute the game.
- Inject JavaScript into the page.
- Modify the DOM.
- Remove advertisements or page elements.
- Intercept or modify game traffic.
- Automate typing or gameplay.
- Manipulate scores.
- Hook game internals.

A local offline page may only explain that the network is unavailable. It must
not imitate Sushi-da or use Sushi-da assets.

## 4. Security boundaries

The primary security goal is kiosk escape prevention for ordinary users.

Distinguish these threat classes in design and documentation:

1. Accidental input and ordinary GUI escape attempts.
2. Deliberate kiosk escape attempts by a local user.
3. Privilege escalation from the kiosk account.
4. Physical attackers with access to storage, firmware settings, or removable
   boot media.

The software image alone cannot fully resist a physical attacker. Document
manual deployment controls such as:

- UEFI administrator password
- Disabling external boot devices
- Prioritizing the internal system disk
- Restricting firmware setup access
- Restricting physical access to storage and the case

Do not claim stronger security than the implementation provides.

## 5. Kiosk account requirements

Create a dedicated account named `kiosk`.

It must have:

- No usable password
- No sudo access
- No membership in administrative groups
- No interactive shell unless strictly required by the service implementation
- No persistent browser profile
- No persistent home state
- Only the device and session permissions needed for Wayland, DRM, input, audio,
  and networking

Do not create any route from the kiosk UI to root privileges.

## 6. Chromium requirements

Use both command-line kiosk options and managed Chromium policy.

Chromium must:

- Start in kiosk or app mode
- Hide tabs and the address bar
- Suppress first-run UI
- Suppress default-browser checks
- Suppress crash restore dialogs
- Disable browser sign-in
- Disable password saving
- Disable address and payment autofill
- Disable printing
- Block downloads
- Disable guest mode
- Disable incognito mode
- Disable developer tools
- Prevent navigation to arbitrary URLs
- Keep WebGL enabled
- Keep GPU acceleration enabled when supported
- Keep the Chromium sandbox enabled

Never use:

```text
--no-sandbox
--disable-gpu
```

At minimum, evaluate and configure these managed policies:

- `DeveloperToolsAvailability`
- `BrowserGuestModeEnabled`
- `IncognitoModeAvailability`
- `BrowserSignin`
- `PasswordManagerEnabled`
- `AutofillAddressEnabled`
- `AutofillCreditCardEnabled`
- `PrintingEnabled`
- `DownloadRestrictions`
- `URLBlocklist`
- `URLAllowlist`

Allow only the minimum required origins. Permit the configured Sushi-da origin
and the local offline page. Do not add broad allowlists based only on guesses.

## 7. Input and escape prevention

The kiosk must prevent escape through at least these inputs:

- Alt+Tab
- Alt+F2
- Alt+F4
- Super
- Super+D
- Super+R
- Ctrl+Alt+T
- Ctrl+Alt+F1 through Ctrl+Alt+F12
- Ctrl+Alt+Delete
- Ctrl+L
- Ctrl+T
- Ctrl+N
- Ctrl+Shift+N
- Ctrl+W
- Ctrl+U
- Ctrl+Shift+I
- F11
- F12

Normal gameplay input must continue to work, including letters, digits,
punctuation, Space, Enter, and Backspace.

Do not solve shortcut restrictions by injecting scripts into the website.
Implement them through Cage, systemd, Linux console configuration, Chromium
policy, and supported browser options.

If a shortcut still terminates Chromium, systemd must restore the kiosk within
five seconds.

## 8. systemd service requirements

The kiosk service must:

- Run as `kiosk`
- Start automatically after required local devices and networking are ready
- Start Cage and Chromium as one managed kiosk session
- Use `Restart=always`
- Use a short, bounded `RestartSec`
- Avoid permanent failure caused by the default start-rate limit
- Terminate all child processes when stopped
- Use `NoNewPrivileges=true`
- Drop unnecessary capabilities
- Apply safe systemd sandboxing

Do not apply hardening that breaks Wayland, DRM, input, audio, D-Bus,
NetworkManager integration, or Chromium's own sandbox.

## 9. Console and remote access lockdown

Production images must not expose an ordinary local or remote shell.

Requirements:

- Disable unnecessary getty services
- Prevent ordinary virtual-terminal login
- Disable serial getty in production
- Do not install an SSH server
- Do not install telnet or another remote shell
- Do not install a terminal emulator
- Do not create a terminal launch shortcut
- Do not expose a normal graphical login screen

Do not remove essential initramfs or systemd recovery components in a way that
makes the image unbootable. Test-only debug access must be isolated from the
production image and clearly documented.

## 10. Network behavior

Wired Ethernet must use DHCP automatically.

Wi-Fi provisioning rules:

- Only include Wi-Fi credentials when `local/wifi.nmconnection` exists.
- Set the connection file mode to `0600`.
- Never commit real credentials.
- Keep `local/wifi.nmconnection.example` as a redacted template.
- State clearly that credentials embedded in an ISO can be extracted by anyone
  who obtains the ISO.
- Do not include a Wi-Fi settings GUI in production.

When networking is unavailable:

1. Show the local offline page.
2. Continue checking NetworkManager state.
3. Perform only low-frequency connectivity checks.
4. Return to the configured Sushi-da URL after connectivity is restored.

Do not generate high-frequency requests to Sushi-da or another external host.

## 11. Audio and graphics requirements

Include the minimum packages required for:

- DRM
- GBM
- Wayland
- Mesa
- WebGL
- Standard keyboard layouts
- Audio playback
- Common Intel, AMD, Realtek, and Intel Wi-Fi firmware where appropriate

Do not force software rendering on real hardware.

QEMU may use software rendering, but production must attempt normal hardware
acceleration.

Provide a diagnostics command that records enough information to determine
whether WebGL, DRM, audio, Cage, Chromium, and networking are available.

## 12. Read-only design

Production is a read-only live system.

Place mutable runtime data under tmpfs or `/run`, including:

- Chromium profile
- Browser cache
- Temporary downloads, even though downloads are blocked
- Session state
- Kiosk runtime files
- Non-persistent logs

The system must return to a known-good state after sudden power loss.

Persistent user settings are outside the MVP scope unless explicitly requested.

## 13. Build isolation

Prefer a Debian 13 builder container.

Support these build paths:

- Docker on Linux
- Podman on Linux
- Docker Engine inside WSL2
- Direct build on a Debian 13 host
- Windows PowerShell wrapper that invokes WSL2

Do not modify host:

- GRUB
- UEFI variables
- Disk partitions
- Filesystems
- Network settings
- `/etc`
- User accounts

Do not write outside the repository except for normal container engine storage.

Document every required privilege, loop device, mount, or container capability.

## 14. Dangerous operation policy

Never automatically:

- Run `dd` against a real disk
- Write to a USB drive
- Create or resize partitions
- Run `mkfs`
- Modify the host bootloader
- Modify UEFI NVRAM
- Change Secure Boot
- Reboot or shut down the host

A flashing script must require an explicit block-device path and must validate:

- Effective root privileges
- Target is a block device
- Target is not the current system disk
- Device model and capacity are shown
- Final interactive confirmation is required
- `--yes` does not bypass system-disk protection
- `sync` runs after writing
- Written image checksum is verified where feasible

Codex must not execute the flashing script against a real device.

## 15. Repository hygiene

Generated files belong in:

```text
build/
artifacts/
```

Secrets and machine-local configuration belong in:

```text
local/
```

Rules:

- Keep generated images and build trees out of Git.
- Keep real Wi-Fi credentials out of Git.
- Do not commit private keys, passwords, tokens, or machine-specific identifiers.
- Use deterministic scripts where practical.
- Quote shell variables.
- Use strict shell modes where compatible.
- Prefer POSIX shell unless Bash features are justified.
- Run ShellCheck on shell scripts.
- Format shell scripts consistently.
- Validate JSON and systemd unit syntax.
- Do not leave unresolved TODOs in security-critical code.

## 16. Required artifacts

A successful production build must create:

```text
artifacts/sushida-os-amd64.iso
artifacts/SHA256SUMS
artifacts/package-manifest.txt
artifacts/build-info.json
```

`build-info.json` must include:

- Git commit
- Debian release
- Build timestamp
- Architecture
- Chromium package version
- Cage package version
- live-build version
- ISO SHA-256

## 17. Required Make targets

Maintain at least:

```text
make builder
make configure
make iso
make test
make test-static
make test-shell
make test-qemu
make qemu
make verify
make clean
make distclean
```

Targets must fail with a non-zero exit code when their operation fails.

## 18. Test requirements

Static tests must verify at least:

- Chromium managed policy is valid JSON.
- Developer tools are disabled.
- Guest mode is disabled.
- Incognito mode is disabled.
- Printing is disabled.
- Downloads are blocked.
- URL restrictions exist.
- `--no-sandbox` is absent.
- `--disable-gpu` is absent.
- Kiosk service has automatic restart.
- Kiosk user does not gain sudo access.
- SSH server is not in the production package list.
- Terminal emulators are not in the production package list.
- Real secrets under `local/` are not tracked.

QEMU smoke tests should verify, when practical:

- BIOS or UEFI boot succeeds.
- Boot does not stop at a login screen.
- Kiosk service starts.
- Cage starts.
- Chromium starts.
- The configured URL is attempted.
- Chromium restart works.
- Offline mode activates when networking is absent.

Use serial logs, systemd status, and screenshots for automation where possible.
Do not add a debug shell to the production image merely to make testing easier.

## 19. Documentation requirements

Maintain:

- `README.md`
- `docs/architecture.md`
- `docs/threat-model.md`
- `docs/build.md`
- `docs/installation.md`
- `docs/networking.md`
- `docs/maintenance.md`
- `docs/hardware-compatibility.md`
- `docs/acceptance-tests.md`

Documentation must distinguish verified behavior from expected behavior and must
list anything requiring physical-hardware validation.

## 20. Implementation workflow

For substantial changes:

1. Inspect the repository and current Git status.
2. Read this file and the relevant documentation.
3. State the implementation scope internally before editing.
4. Implement the smallest coherent change.
5. Add or update tests.
6. Run relevant static checks.
7. Run build or QEMU tests when the environment supports them.
8. Inspect generated logs and artifacts.
9. Update documentation.
10. Report completed, failed, and unverified items separately.

Do not claim that a test passed unless it was actually executed successfully.

If the execution environment cannot build or run QEMU, still complete static
implementation and state the exact limitation.

## 21. Definition of done

The project is complete only when all of these are satisfied:

1. `make iso` succeeds.
2. The ISO and checksums are generated.
3. QEMU boots the image.
4. No ordinary login screen appears.
5. Chromium displays the configured page full-screen.
6. Tabs and address bar are absent.
7. The user cannot switch to another application.
8. The user cannot open a terminal.
9. Developer tools cannot be opened.
10. Arbitrary URL navigation is blocked.
11. Chromium restarts within five seconds after exit.
12. Offline mode works.
13. Network recovery returns to the configured page.
14. WebGL is not deliberately disabled.
15. Audio packages and configuration are present.
16. The kiosk user has no administrative privilege.
17. No SSH server is installed.
18. The root filesystem is read-only.
19. No secret is committed.
20. `make test` succeeds.
21. Build, verification, installation, and manual acceptance tests are documented.

## 22. Final reporting format

When completing a large implementation task, report:

### A. Implementation status

- Complete
- Partial
- Incomplete

### B. Selected versions

- Debian
- Chromium
- Cage
- live-build

### C. Generated artifacts

List exact repository-relative paths.

### D. Tests executed

List every command and its result.

### E. Security controls

List implemented kiosk escape controls.

### F. Unverified items

List hardware-dependent or environment-dependent checks.

### G. Deployment commands

Show the next commands the user must run, but do not write to a real block
device yourself.
