# Acceptance tests

## Shortcut and escape prevention

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| K01 | Power on | Kiosk starts without a login screen |  |  | Live image boots directly to Cage |
| K02 | Alt+Tab | No application switcher appears |  |  | Cage: single-application compositor, no DE |
| K03 | Alt+F2 | No application launcher or run dialog appears |  |  | Cage: single-application compositor, no DE installed |
| K04 | Alt+F4 | Kiosk remains or restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| K05 | Super | No desktop shell or overview appears |  |  | Cage: no DE installed |
| K06 | Super+D | No desktop shown |  |  | Cage: no DE installed |
| K07 | Super+R | No run dialog appears |  |  | Cage: no DE installed |
| K08 | Ctrl+Alt+T | No terminal opens |  |  | No terminal emulator installed |
| K09 | Ctrl+Alt+F1 | No usable login console appears |  |  | Cage -s absent + NAutoVTs=0 + getty mask |
| K10 | Ctrl+Alt+F2 | No usable login console appears |  |  | Cage -s absent + NAutoVTs=0 + getty mask |
| K11 | Ctrl+Alt+F3 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K12 | Ctrl+Alt+F4 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K13 | Ctrl+Alt+F5 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K14 | Ctrl+Alt+F6 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K15 | Ctrl+Alt+F7 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K16 | Ctrl+Alt+F8 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K17 | Ctrl+Alt+F9 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K18 | Ctrl+Alt+F10 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K19 | Ctrl+Alt+F11 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K20 | Ctrl+Alt+F12 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K21 | Ctrl+Alt+Delete (single) | No reboot or logout |  |  | ctrl-alt-del.target masked |
| K22 | Ctrl+Alt+Delete (rapid burst) | No forced action from systemd |  |  | CtrlAltDelBurstAction=none |
| K23 | Ctrl+L | Address bar not usable or not visible |  |  | Chromium --kiosk mode |
| K24 | Ctrl+T | No new tab opens |  |  | Chromium --kiosk mode |
| K25 | Ctrl+N | No new window opens |  |  | Chromium --kiosk mode |
| K26 | Ctrl+Shift+N | No incognito window opens |  |  | IncognitoModeAvailability=1 |
| K27 | Ctrl+W | Browser tab closes but Cage recovers within 5 seconds |  |  | Restart=always + RestartSec=3 |
| K28 | Ctrl+U | Page source does not open |  |  | DeveloperToolsAvailability=2 + view-source:* |
| K29 | Ctrl+Shift+I | Developer tools do not open |  |  | DeveloperToolsAvailability=2 |
| K30 | F11 | No full-screen toggle (already kiosk) |  |  | Chromium --kiosk mode |
| K31 | F12 | Developer tools do not open |  |  | DeveloperToolsAvailability=2 |
| K32 | Disconnect network | Local Wi-Fi setup screen appears |  |  | Low-frequency watcher restarts the managed kiosk session |
| K33 | Restore network | Sushi-da page returns automatically |  |  | Fresh session selects the validated configured URL |
| K34 | First boot without Ethernet | Wi-Fi networks appear after the 15-second grace period |  |  | Loopback setup UI; physical Wi-Fi required; NetworkManager wait-online is not on the kiosk dependency path |
| K34a | Select each visible SSID row and press `再スキャン` | Radio selection works; rescan returns to the setup list without a white `Not found` page |  |  | Physical Cage/Wayland input required |
| K34b | Let NetworkManager change state while the setup page remains visible | Visible SSID rows, password field, and connect button stay interactive until the watcher changes routes |  |  | Covers the launcher/render timing race |
| K35 | Enter valid Wi-Fi credential | Association succeeds and Sushi-da opens |  |  | Credential is saved only after successful association |
| K35a | Submit after an automatic Wi-Fi backend restart | The existing form remains valid and association proceeds; no plain `Forbidden` page appears |  |  | CSRF token is preserved only across automatic service restart |
| K35b | Submit a stale or invalid setup form | A Japanese error appears inside the interactive setup page and the password is not reflected |  |  | Retrying requires password re-entry |
| K35c | Disconnect after one successful setup, then enter a replacement credential | The replacement is saved persistently despite the intervening kiosk restart |  |  | Confirms config readiness is independent of `/run/sushida-os` |
| K35d | Connect successfully while NetworkManager auto-connect modification is delayed or unavailable | The request stays on a valid transition page; no white error or traceback appears |  |  | Persistent setup credential remains the reboot recovery path |
| K36 | Clean reboot after K35 | Saved Wi-Fi reconnects and Sushi-da opens |  |  | Verify `SUSHIDA-CFG` persistence |
| K36a | Boot with saved Wi-Fi while Ethernet is connected, then unplug Ethernet | Managed Wi-Fi is already associated and online routing recovers without credential re-entry |  |  | General wired connectivity must not suppress Wi-Fi restoration |
| K37 | Enter invalid Wi-Fi credential | Error remains inside setup UI and no credential is saved |  |  | No arbitrary browser navigation |
| K38 | Boot with missing/damaged config partition | Boot continues; setup refuses persistent save |  |  | Static offline fallback remains available |
| K38a | Select an SSID with the config partition unavailable | Controls remain interactive and Wi-Fi connects for the current boot with a non-persistence warning |  |  | Must not silently claim that credentials were saved |
| K38b | Submit an open SSID with a non-empty password | Backend rejects it before changing NetworkManager and asks for an empty password |  |  | Open mode never creates a passwd-file |
| K38c | Submit WEP, 802.1X/Enterprise, OWE, SAE-only WPA3, hidden, or unknown security | A specific unsupported-mode Japanese message appears and no profile/radio change occurs |  |  | Backend re-scan owns the security decision; WPA2/WPA3 transition mode is supported as WPA Personal |
| K38d | Submit a WPA Personal password containing spaces, a colon, and symbols | Association succeeds without the password appearing in argv, logs, or the HTTP response |  |  | Confirm with redacted diagnostics only |
| K38e | Stop and restart the test AP after a successful WPA Personal setup | NetworkManager reconnects during the same boot without a second password entry |  |  | Confirm the runtime profile uses `psk-flags=0`; reboot recovery remains through `setup.json` |

## Gameplay input

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| G01 | Letters (a-z) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G02 | Digits (0-9) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G03 | Punctuation | Typed characters appear in-game |  |  | No keyboard filter applied |
| G04 | Space | Space character works in-game |  |  | No keyboard filter applied |
| G05 | Enter | Enter key works in-game |  |  | No keyboard filter applied |
| G06 | Backspace | Backspace works in-game |  |  | No keyboard filter applied |
| G07 | Physical JIS `@` key | `@` is entered as `@` |  |  | Verify on the target keyboard, not a US-layout substitute |
| G08 | Shift+2 | `"` is entered as `"` |  |  | JIS symbol mapping |
| G09 | JIS punctuation | `^`, `:`, `¥`/backslash, `_`, `[`, and `]` all enter correctly |  |  | Record the physical key and resulting character |
| G10 | JIS Wi-Fi test password | A dedicated test AP accepts a password containing the symbols above |  |  | Do not include the SSID or PSK in shared evidence |

## Power and recovery

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| P01 | Chromium crash | Cage exits; service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P02 | Cage crash | Service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P03 | Power loss | On next boot, system returns to known-good kiosk state |  |  | Immutable SquashFS plus volatile overlay |
| P04 | Power loss during credential update | Root still boots; prior or new complete credential is present, never partial JSON |  |  | Sacrificial media; atomic replace does not prove ext4 durability |
| P05 | Normal shutdown | `SUSHIDA-CFG` unmounts without failure |  |  | Record exact unit if any unmount warning appears |
| P06 | Press the physical power button once | systemd-logind reaches the normal `poweroff.target` path and the guest/host test ends naturally |  |  | No acpid or custom event monitor is installed |
| P07 | Hold the physical power button | Long press is ignored; only the normal short-press action is supported |  |  | Confirm with firmware/ACPI behavior |
| P08 | QEMU monitor `system_powerdown` | Dedicated BIOS/UEFI test exits naturally, serial logs show normal poweroff, and explicit `SUSHIDA-CFG` mount plus unmount evidence is present |  |  | Monitor socket must be below `build/qemu`; result is bound to current Git commit and release checksums |

## Audio

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| A01 | Play Sushi-da game audio | Audio is audible on the selected output |  |  | PipeWire + WirePlumber |

## Graphics

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| V01 | Check WebGL | Chromium uses WebGL without deliberate GPU disable flags |  |  | No --disable-gpu or --disable-webgl |
| V02 | Check HW acceleration | GPU-accelerated compositing is active |  |  | --ozone-platform=wayland |

## Definition of Done coverage map

This table defines required evidence; it does not record a pass. Automated
configuration evidence and manual runtime evidence are complementary.

| ID | Definition of Done item | Required verification |
|---|---|---|
| D01 | `make iso` succeeds | Automated builder command exit 0 and `build/iso-build.log` ending in success with matching ISO SHA-256 |
| D02 | ISO and checksums generated | Automated `make verify`, four exact artifact paths, matching SHA-256 |
| D03 | QEMU boots image | Automated BIOS/UEFI bounded run plus reviewed final screenshots |
| D04 | No ordinary login screen | Serial login-prompt scan plus BIOS/UEFI screenshot and physical boot review |
| D05 | Chromium displays configured page full-screen | Manual QEMU/hardware visual inspection with artifact SHA recorded |
| D06 | Tabs and address bar absent | Manual Chromium UI inspection; launcher/static policy evidence is supporting only |
| D07 | Cannot switch application | Manual K02-K07 and compositor behavior on representative hardware |
| D08 | Cannot open terminal | Automated prohibited-package checks plus manual K08 |
| D09 | Developer tools cannot open | Managed-policy test plus manual K29/K31 |
| D10 | Arbitrary navigation blocked | JSON/launcher/helper URL tests plus controlled manual navigation attempts |
| D11 | Chromium restarts within five seconds | Unit static check plus timed manual P01/K04/K27 observation |
| D12 | Offline/setup mode works | Watcher BATS and writable-QEMU static fallback evidence, plus physical-hardware K32/K34 setup evidence |
| D13 | Network recovery returns to configured page | Watcher BATS plus physical or controlled runtime K33 |
| D14 | WebGL not deliberately disabled | Source/argv tests; actual WebGL backend requires V01 hardware evidence |
| D15 | Audio packages/config present | Package/image validation; audible output requires A01 hardware evidence |
| D16 | Kiosk user has no administrative privilege | Account hook, image validator, package and service static tests |
| D17 | No SSH server installed | Package-list and image-internal prohibited-package validation |
| D18 | Root filesystem is read-only design | live-build/SquashFS and isolated config-partition verification plus destructive P03/P04 test on sacrificial hardware |
| D19 | No secret committed | Git-aware secret tests and manual artifact distribution review |
| D20 | `make test` succeeds | Retained full pytest/ShellCheck/BATS command output from the release commit |
| D21 | Build, verification, installation, acceptance documented | Static documentation test plus operator review of all required docs |

## Evidence collection rules

For every manual run, record artifact SHA-256, Git commit, hardware model,
firmware version/settings, display/audio/network/input devices, date, operator,
steps, actual result, and retained screenshot/log/report paths. Do not put SSIDs,
PSKs, MAC addresses, tokens, or other credentials in shared evidence.

- Input latency: preserve raw high-speed video or external event/display timing
  data and the measurement method. Define the deployment threshold before the
  run; this project specifies no invented universal number.
- GPU/WebGL: retain a controlled `chrome://gpu` screenshot and redacted
  diagnostics; do not enable remote debugging or weaken production policy.
- Audio: identify the physical connector/output and record audible/not-audible
  results separately for each tested path.
- Power loss: use sacrificial hardware, predefine cycle count and interruption
  phases, and record every subsequent boot/runtime-state result.
- Representative hardware: use the matrix in `hardware-compatibility.md` and do
  not generalize one passing model to all Intel/AMD systems.

The `Actual result` and `Pass/Fail` cells above intentionally remain blank until
the corresponding procedure is executed on the named artifact and hardware.
