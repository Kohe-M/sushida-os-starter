# Sushi-da OS implementation tasks

This file divides the implementation into reviewable units. Complete and review
one task before starting the next task. `AGENTS.md` is the authoritative project
contract and takes precedence over this file.

## Working rules

- Inspect the real repository and `git status` before every task.
- Keep each change limited to the named task and listed files.
- Do not create branches, commits, or pull requests unless explicitly requested.
- Do not claim a test passed unless the command was executed successfully.
- Do not fetch, copy, modify, inject into, automate, or redistribute Sushi-da content.
- Never run a flashing script against a real block device during development.
- Report completed, failed, and unverified work separately.
- Stop after each task so the diff can be reviewed before the next task begins.

## Task 1: Make the first static tests meaningful

Scope:

- `Makefile`
- `tests/static/test_chromium_policy.py`
- `tests/static/test_no_secrets.py`

Work:

- Make `make test-static` run the Python tests under `tests/static`.
- Replace the Chromium-policy placeholder with checks for valid JSON, required
  policy values, URL restrictions, the official default origin, and the local
  offline page.
- Replace the secrets placeholder with checks that real Wi-Fi configuration and
  other machine-local secrets are not tracked by Git.
- Leave the lockdown and systemd placeholder tests for their corresponding tasks.

Done when:

- The two named tests validate real repository state.
- The focused pytest command succeeds when pytest is available.
- `make test-static` succeeds in a supported environment.
- `git diff --check` succeeds.

## Task 2: Implement the Debian 13 builder container

Scope:

- `builder/Dockerfile`
- `builder/entrypoint.sh`
- `Makefile` target `builder`

Work:

- Use Debian 13 trixie as the builder base.
- Install live-build and the tools required for static, shell, and image checks.
- Support a repository-mounted build without modifying host system configuration.
- Keep the container usable with Docker and, where practical, Podman.

Done when:

- The builder image can be built.
- Required tool versions can be printed inside the container.
- No ISO build is required in this task.

## Task 3: Implement the base live-build configuration

Scope:

- `live-build/auto/config`
- `live-build/auto/build`
- `live-build/auto/clean`
- `Makefile` target `configure`

Work:

- Configure Debian 13 trixie, amd64, and a hybrid live ISO.
- Keep generated live-build state under ignored repository directories.
- Make configuration repeatable and fail on errors.
- Do not alter host boot, disk, network, users, or `/etc`.

Done when:

- live-build configuration can be generated more than once safely.
- Generated state is ignored by Git.
- Building a complete ISO is not required yet.

## Task 4: Define the production package list

Scope:

- `live-build/config/package-lists/kiosk.list.chroot`
- Relevant static tests

Work:

- Select Debian 13 packages for Cage, Chromium, NetworkManager, PipeWire,
  Wayland, Mesa, DRM/GBM, keyboard data, and appropriate firmware.
- Exclude SSH servers, display managers, desktop environments, terminal
  emulators, file managers, and proprietary NVIDIA drivers.
- Verify package names against Debian 13 package metadata during implementation.

Done when:

- Required package categories are represented.
- Static tests reject prohibited production packages.

## Task 5: Create and constrain the kiosk account

Scope:

- `live-build/config/hooks/live/010-create-kiosk-user.hook.chroot`
- Runtime-directory or tmpfiles configuration required by the account
- Corresponding static tests

Work:

- Create the `kiosk` account idempotently.
- Give it no usable password, sudo access, or administrative group membership.
- Avoid persistent home and browser state.
- Grant only permissions needed for Wayland, DRM, input, audio, and the session.

Done when:

- Re-running the hook is safe.
- Tests demonstrate that no administrative route is added.

## Task 6: Implement the Chromium launcher

Scope:

- `live-build/config/includes.chroot/usr/local/bin/sushida-launch`
- `live-build/config/includes.chroot/etc/sushida-os/config.env`
- `tests/shell/launch.bats`

Work:

- Start Chromium through Cage in kiosk or app mode.
- Put profile, cache, download, and session state under `/run` or tmpfs.
- Suppress first-run, default-browser, and crash-restore UI.
- Load the configured URL without evaluating arbitrary shell code.
- Keep Chromium sandbox, WebGL, and GPU acceleration enabled.
- Never use `--no-sandbox` or `--disable-gpu`.

Done when:

- BATS checks the generated Chromium invocation and unsafe input handling.
- Runtime state is non-persistent.

## Task 7: Implement the kiosk systemd service

Scope:

- `live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service`
- `live-build/config/hooks/live/020-enable-services.hook.chroot`
- `tests/static/test_systemd_units.py`

Work:

- Run the Cage/Chromium session as `kiosk`.
- Use `Restart=always` with a short bounded delay and avoid permanent start-rate
  failure.
- Terminate the complete process group when stopped.
- Apply `NoNewPrivileges=true`, capability restrictions, and safe sandboxing.
- Preserve required DRM, input, audio, Wayland, D-Bus, and Chromium sandbox access.

Done when:

- Static checks cover the required service properties.
- The unit passes `systemd-analyze verify` in a compatible environment.

## Task 8: Finalize Chromium managed policy

Scope:

- `live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json`
- `tests/static/test_chromium_policy.py`
- Relevant architecture documentation

Work:

- Verify all policy names and values against Debian Chromium.
- Disable developer tools, guest and incognito modes, sign-in, password saving,
  autofill, printing, and downloads.
- Deny navigation by default and allow only justified official and local URLs.
- Resolve how configurable URLs remain synchronized with managed URL policy.
- Decide whether `loading.html` is used and, if so, how it is safely allowed.

Done when:

- The effective policy cannot be bypassed by changing `config.env` to an
  arbitrary origin.
- No speculative broad allowlist is added.

## Task 9: Lock down console and escape inputs

Scope:

- `live-build/config/hooks/live/050-lock-down-system.hook.chroot`
- `live-build/config/includes.chroot/etc/systemd/logind.conf.d/90-sushida-kiosk.conf`
- `live-build/config/includes.chroot/etc/sysctl.d/90-sushida-kiosk.conf`
- Relevant static tests

Work:

- Disable unnecessary getty and serial-getty services in production.
- Prevent usable virtual-terminal login and disable Ctrl+Alt+Delete behavior.
- Map each required shortcut to the responsible Cage, Chromium, systemd, or
  console control.
- Preserve letters, digits, punctuation, Space, Enter, and Backspace.

Done when:

- Static controls are tested.
- Hardware-only shortcut behavior is explicitly left for acceptance testing.

## Task 10: Configure networking and optional Wi-Fi

Scope:

- `live-build/config/includes.chroot/etc/NetworkManager/conf.d/90-sushida-os.conf`
- `live-build/config/hooks/live/040-configure-network.hook.chroot`
- `local/wifi.nmconnection.example`
- Relevant static tests

Work:

- Enable automatic wired DHCP.
- Include `local/wifi.nmconnection` only when it exists.
- Enforce mode `0600` on an embedded Wi-Fi connection.
- Keep Wi-Fi settings UI and real credentials out of production Git history.

Done when:

- Builds work both with and without a local Wi-Fi file.
- Tests reject tracked credentials and unsafe permissions.

## Task 11: Implement offline and network-recovery behavior

Scope:

- `live-build/config/includes.chroot/usr/local/bin/sushida-network-watch`
- `live-build/config/includes.chroot/etc/systemd/system/sushida-network-watch.service`
- `tests/shell/network-watch.bats`

Work:

- Observe NetworkManager at a low frequency.
- Show the local offline page while disconnected.
- Return to the configured official page after recovery.
- Avoid frequent requests to Sushi-da or another external host.
- Define a safe control boundary between the watcher and Chromium session.

Done when:

- BATS covers offline, unchanged, and recovered state transitions.
- The implementation cannot become a high-frequency external poller.

## Task 12: Configure audio, graphics, and Wayland support

Scope:

- `live-build/config/hooks/live/030-configure-audio.hook.chroot`
- Production package list and necessary runtime configuration

Work:

- Provide PipeWire audio suitable for the unprivileged kiosk session.
- Include DRM, GBM, Wayland, and Mesa support for Intel and AMD graphics.
- Do not force software rendering on production hardware.
- Isolate any software-rendering option to QEMU-only execution.

Done when:

- Production configuration does not deliberately disable GPU or WebGL.
- Remaining hardware verification is documented as unverified.

## Task 13: Complete the read-only runtime design

Scope:

- live-build runtime configuration
- tmpfs/runtime directory and non-persistent logging configuration
- `docs/architecture.md`

Work:

- Keep the production live root read-only.
- Place mutable profile, cache, download, session, kiosk, and log data in tmpfs
  or `/run`.
- Ensure a reboot after unexpected power loss returns to known-good state.

Done when:

- Every expected mutable path has a documented non-persistent destination.
- No persistent kiosk user state is introduced.

## Task 14: Add image-internal validation

Scope:

- `live-build/config/hooks/live/090-validate-image.hook.chroot`

Work:

- Validate required users, packages, units, policy files, and permissions.
- Reject prohibited production packages.
- Reject unresolved placeholders in security-critical image files.

Done when:

- An invalid image fails during the build rather than producing a release ISO.

## Task 15: Build the ISO and required artifacts

Scope:

- `scripts/build.sh`
- `Makefile` target `iso`
- Build metadata generation

Work:

- Produce `artifacts/sushida-os-amd64.iso`.
- Produce `artifacts/SHA256SUMS`.
- Produce `artifacts/package-manifest.txt`.
- Produce `artifacts/build-info.json` with all fields required by `AGENTS.md`.

Done when:

- All four artifacts exist after a successful production build.
- Recorded and computed ISO SHA-256 values agree.

## Task 16: Implement artifact verification and cleanup

Scope:

- `scripts/verify-iso.sh`
- `scripts/clean.sh`
- `Makefile` targets `verify`, `clean`, and `distclean`

Work:

- Verify checksum, metadata, manifest, and required ISO contents.
- Separate disposable build-state cleanup from artifact cleanup.
- Restrict all deletions to known repository build paths.

Done when:

- Invalid artifacts cause non-zero failure.
- Cleanup cannot remove source files or local secret configuration.

## Task 17: Add QEMU execution and smoke tests

Scope:

- `scripts/run-qemu.sh`
- `scripts/smoke-test.sh`
- `tests/qemu/smoke-test.sh`
- `scripts/windows/Build-In-WSL.ps1`
- `scripts/windows/Run-Qemu.ps1`
- `Makefile` targets `qemu` and `test-qemu`

Work:

- Support practical BIOS and UEFI boots.
- Capture serial logs and screenshots where possible.
- Check that boot does not stop at a normal login screen.
- Check kiosk, Cage, Chromium, restart, and offline behavior where observable.
- Do not add a production debug shell for testing.

Done when:

- Automated results and manual-only checks are clearly distinguished.

## Task 18: Implement safe diagnostics

Scope:

- `live-build/config/includes.chroot/usr/local/bin/sushida-diagnostics`
- `docs/maintenance.md`

Work:

- Record DRM, GBM, Wayland, Cage, Chromium, WebGL, PipeWire, and NetworkManager
  information.
- Redact passwords, Wi-Fi secrets, tokens, and sensitive identifiers.
- Write to `/run` or an explicitly selected destination.
- Do not expose diagnostics as a kiosk-to-shell escape route.

Done when:

- The output is useful for hardware triage without containing credentials.

## Task 19: Implement guarded removable-media writing

Scope:

- `scripts/flash.sh`
- `docs/installation.md`

Work:

- Require an explicit block-device path and effective root privileges.
- Verify the target is a block device and not the current system disk.
- Display model and capacity and require final interactive confirmation.
- Ensure `--yes` cannot bypass system-disk protection.
- Run `sync` and verify the written image where feasible.

Done when:

- Safety logic is tested without writing to a real device.
- Codex and automated tests never execute the script against a real device.

## Task 20: Complete documentation and acceptance coverage

Scope:

- `README.md`
- All required files under `docs/`

Work:

- Document Linux, Docker, Podman, WSL2, and direct Debian build paths.
- Document networking, deployment, updates, rollback, diagnostics, and recovery.
- Document physical-security controls and extractable ISO Wi-Fi credentials.
- Map every Definition of Done item to an automated or manual verification.
- Define evidence collection for input latency, GPU/WebGL, audio, power loss, and
  representative hardware without inventing numerical thresholds.

Done when:

- Verified, expected, failed, and hardware-unverified behavior are clearly
  distinguished.
- No unexecuted test is described as passing.

## Prompt for the first coding agent

Copy the following prompt exactly for the first implementation pass:

```text
Work in C:\Users\2omur\development\sushida-os-starter and implement only Task 1,
"Make the first static tests meaningful."

Before editing, read and inspect:

- AGENTS.md
- README.md
- Makefile
- live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json
- tests/static/test_chromium_policy.py
- tests/static/test_no_secrets.py
- .gitignore
- local/README.md
- local/wifi.nmconnection.example
- the current Git status and diff

Treat AGENTS.md as the highest-priority repository instruction.

Allowed implementation scope:

1. Change Makefile so test-static runs the tests under tests/static with pytest.
2. Replace the placeholder in tests/static/test_chromium_policy.py with tests of
   the real Chromium managed-policy JSON.
3. Replace the placeholder in tests/static/test_no_secrets.py with tests that
   real local Wi-Fi settings and machine-local secrets are not tracked by Git.

The Chromium policy tests must check at least:

- The file parses as JSON and has the expected value types.
- DeveloperToolsAvailability disables developer tools.
- BrowserGuestModeEnabled is false.
- IncognitoModeAvailability disables incognito mode.
- BrowserSignin is disabled.
- PasswordManagerEnabled is false.
- AutofillAddressEnabled is false.
- AutofillCreditCardEnabled is false.
- PrintingEnabled is false.
- DownloadRestrictions blocks downloads.
- URLBlocklist exists and denies by default.
- URLAllowlist exists.
- The default official Sushi-da URL or its required origin is allowed.
- The local offline page is allowed.
- Do not add --no-sandbox or --disable-gpu as Chromium launch arguments.

The secret-handling tests must check at least:

- local/wifi.nmconnection is not tracked by Git.
- Only README and explicit example files are allowed as tracked local files.
- Example files continue to contain obvious redacted placeholders rather than
  plausible real credentials.
- Do not generate a secret file merely to run the test.
- Any Git command used by a test must be read-only.

Do not:

- Start Task 2 or any later task.
- Modify builder files, live-build scripts, systemd units, launcher, network
  watcher, documentation, or production packages.
- Modify tests/static/test_lockdown.py or tests/static/test_systemd_units.py in
  this task.
- Change the managed-policy JSON unless a concrete test-backed inconsistency
  makes a minimal correction necessary; explain any such correction.
- Create a branch, commit, push, build an ISO, start QEMU, or flash a device.
- Fetch, copy, scrape, inject into, or redistribute Sushi-da content.
- Overwrite unrelated existing changes.
- Weaken a security assertion merely to make a test pass.

Verification:

- Run the focused pytest tests when pytest is available.
- Run make test-static in a supported shell environment when available.
- Run git diff --check.
- Finish with git status --short.
- If a command cannot run, report the exact command and error instead of claiming
  success.

Final report:

1. Changed files and why.
2. Commands executed and their results.
3. Failed or unexecuted verification.
4. Remaining placeholders.
5. The complete diff or sufficiently complete diff information for review.

Stop immediately after Task 1 so Codex can review the diff before further work.
```
