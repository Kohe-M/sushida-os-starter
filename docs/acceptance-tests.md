# Acceptance tests

## Shortcut and escape prevention

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| K01 | QEMU / physical | Power on | Kiosk starts without a login screen |  |  | Live image boots directly to Cage |
| K02 | physical hardware | Alt+Tab | No application switcher appears |  |  | Cage: single-application compositor, no DE |
| K03 | physical hardware | Alt+F2 | No application launcher or run dialog appears |  |  | Cage: single-application compositor, no DE installed |
| K04 | physical hardware | Alt+F4 | Kiosk remains or restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| K05 | physical hardware | Super | No desktop shell or overview appears |  |  | Cage: no DE installed |
| K06 | physical hardware | Super+D | No desktop shown |  |  | Cage: no DE installed |
| K07 | physical hardware | Super+R | No run dialog appears |  |  | Cage: no DE installed |
| K08 | physical hardware | Ctrl+Alt+T | No terminal opens |  |  | No terminal emulator installed |
| K09 | physical hardware | Ctrl+Alt+F1 | No usable login console appears |  |  | Cage -s absent + NAutoVTs=0 + getty mask |
| K10 | physical hardware | Ctrl+Alt+F2 | No usable login console appears |  |  | Cage -s absent + NAutoVTs=0 + getty mask |
| K11 | physical hardware | Ctrl+Alt+F3 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K12 | physical hardware | Ctrl+Alt+F4 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K13 | physical hardware | Ctrl+Alt+F5 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K14 | physical hardware | Ctrl+Alt+F6 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K15 | physical hardware | Ctrl+Alt+F7 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K16 | physical hardware | Ctrl+Alt+F8 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K17 | physical hardware | Ctrl+Alt+F9 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K18 | physical hardware | Ctrl+Alt+F10 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K19 | physical hardware | Ctrl+Alt+F11 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K20 | physical hardware | Ctrl+Alt+F12 | No usable login console appears |  |  | Same controls as Ctrl+Alt+F2 |
| K21 | physical hardware | Ctrl+Alt+Delete (single) | No reboot or logout |  |  | ctrl-alt-del.target masked |
| K22 | physical hardware | Ctrl+Alt+Delete (rapid burst) | No forced action from systemd |  |  | CtrlAltDelBurstAction=none |
| K23 | physical hardware | Ctrl+L | Address bar not usable or not visible |  |  | Chromium --kiosk mode |
| K24 | physical hardware | Ctrl+T | No new tab opens |  |  | Chromium --kiosk mode |
| K25 | physical hardware | Ctrl+N | No new window opens |  |  | Chromium --kiosk mode |
| K26 | physical hardware | Ctrl+Shift+N | No incognito window opens |  |  | IncognitoModeAvailability=1 |
| K27 | physical hardware | Ctrl+W | Browser tab closes but Cage recovers within 5 seconds |  |  | Restart=always + RestartSec=3 |
| K28 | physical hardware | Ctrl+U | Page source does not open |  |  | DeveloperToolsAvailability=2 + view-source:* |
| K29 | physical hardware | Ctrl+Shift+I | Developer tools do not open |  |  | DeveloperToolsAvailability=2 |
| K30 | physical hardware | F11 | No full-screen toggle (already kiosk) |  |  | Chromium --kiosk mode |
| K31 | physical hardware | F12 | Developer tools do not open |  |  | DeveloperToolsAvailability=2 |
| K32 | physical hardware | Disconnect network | Local Wi-Fi setup screen appears |  |  | Low-frequency watcher restarts the managed kiosk session |
| K32a | physical hardware | After using Sushi-da for several minutes, disconnect the active network and wait up to about 50 seconds | The constrained Wi-Fi setup screen reappears and accepts a new connection |  |  | 30-second watcher interval, bounded service restart, and up to 15-second launcher grace; confirms setup is not first-boot-only |
| K33 | physical hardware | Restore network | Sushi-da page returns automatically |  |  | Fresh session selects the validated configured URL |
| K34 | physical hardware | First boot without Ethernet | Wi-Fi networks appear after the 15-second grace period |  |  | Loopback setup UI; physical Wi-Fi required; NetworkManager wait-online is not on the kiosk dependency path |
| K34a | physical hardware | Select each visible SSID row and press `再スキャン` | Radio selection works; rescan returns to the setup list without a white `Not found` page |  |  | Physical Cage/Wayland input required |
| K34b | physical hardware | Let NetworkManager change state while the setup page remains visible | Visible SSID rows, password field, and connect button stay interactive until the watcher changes routes |  |  | Covers the launcher/render timing race |
| K35 | physical hardware | Enter valid Wi-Fi credential | Association succeeds and Sushi-da opens |  |  | Credential is saved only after successful association |
| K35a | physical hardware | Submit after an automatic Wi-Fi backend restart | The existing form remains valid and association proceeds; no plain `Forbidden` page appears |  |  | CSRF token is preserved only across automatic service restart |
| K35b | physical hardware | Submit a stale or invalid setup form | A Japanese error appears inside the interactive setup page and the password is not reflected |  |  | Retrying requires password re-entry |
| K35c | physical hardware | Disconnect after one successful setup, then enter a replacement credential | The replacement is saved persistently despite the intervening kiosk restart |  |  | Confirms config readiness is independent of `/run/sushida-os` |
| K35d | physical hardware | Connect successfully while NetworkManager auto-connect modification is delayed or unavailable | The request stays on a valid transition page; no white error or traceback appears |  |  | Persistent setup credential remains the reboot recovery path |
| K36 | physical hardware | Clean reboot after K35 | Saved Wi-Fi reconnects and Sushi-da opens |  |  | Verify `SUSHIDA-CFG` persistence |
| K36a | physical hardware | Boot with saved Wi-Fi while Ethernet is connected, then unplug Ethernet | Managed Wi-Fi is already associated and online routing recovers without credential re-entry |  |  | General wired connectivity must not suppress Wi-Fi restoration |
| K37 | physical hardware | Enter invalid Wi-Fi credential | Error remains inside setup UI and no credential is saved |  |  | No arbitrary browser navigation |
| K38 | physical hardware | Boot with missing/damaged config partition | Boot continues; setup refuses persistent save |  |  | Static offline fallback remains available |
| K38a | physical hardware | Select an SSID with the config partition unavailable | Controls remain interactive and Wi-Fi connects for the current boot with a non-persistence warning |  |  | Must not silently claim that credentials were saved |
| K38b | physical hardware | Submit an open SSID with a non-empty password | Backend rejects it before changing NetworkManager and asks for an empty password |  |  | Open mode never creates a passwd-file |
| K38c | physical hardware | Submit WEP, 802.1X/Enterprise, OWE, SAE-only WPA3, hidden, or unknown security | A specific unsupported-mode Japanese message appears and no profile/radio change occurs |  |  | Backend re-scan owns the security decision; WPA2/WPA3 transition mode is supported as WPA Personal |
| K38d | physical hardware | Submit a WPA Personal password containing spaces, a colon, and symbols | Association succeeds without the password appearing in argv, logs, or the HTTP response |  |  | Confirm with redacted diagnostics only |
| K38e | physical hardware | Stop and restart the test AP after a successful WPA Personal setup | NetworkManager reconnects during the same boot without a second password entry |  |  | Confirm the runtime profile uses `psk-flags=0`; reboot recovery remains through `setup.json` |
| K38f | physical hardware | Submit a Wi-Fi credential while the backend holds previous connection state | The response contains the connecting page, not a post-success form; the browser does not show `ERR_NETWORK_CHANGED` or any other error page, and the setup page eventually transitions to the success message or the interactive form depending on the outcome |  |  | The async state machine guarantees the HTTP response completes before NetworkManager is changed |
| K38g | physical hardware | Submit two duplicate connection requests rapidly | The second request receives a `409 Conflict` response; exactly one connection attempt runs, and only the first credential is persisted |  |  | Duplicate POSTs are serialized; the second credential is never stored |

## Navigation recovery

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| K39 | physical hardware | Click a non-allowlisted link inside the Sushi-da play page | Within about 10 seconds the kiosk returns to the Sushi-da play page; no user interaction is required |  |  | The navigation watcher detects the blocked entry in Chromium's session file and restarts the kiosk |
| K39a | physical hardware | Click a link with `target="_blank"` to a non-allowlisted origin | The popup window opens briefly but the kiosk returns to the Sushi-da play page within about 15 seconds |  |  | The watcher examines every tab's current entry; no managed policy can prevent user-gesture popups |
| K39b | physical hardware | Press every non-allowlisted shortcut while the game is running | The kiosk remains on the Sushi-da play page; no unexpected restart occurs |  |  | Normal gameplay URLs are all within the allowlist; the watcher never triggers on allowed pages |
| K39c | physical hardware | Disconnect the network while Sushi-da is displayed | The network watcher routes to the offline or setup page; the navigation watcher sees that page as allowed and does not restart the kiosk |  |  | The navigation watcher only acts on concretely disallowed URLs (blocked pages, error interstitials) |
 
## Gameplay input

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| G01 | physical hardware | Letters (a-z) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G02 | physical hardware | Digits (0-9) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G03 | physical hardware | Punctuation | Typed characters appear in-game |  |  | No keyboard filter applied |
| G04 | physical hardware | Space | Space character works in-game |  |  | No keyboard filter applied |
| G05 | physical hardware | Enter | Enter key works in-game |  |  | No keyboard filter applied |
| G06 | physical hardware | Backspace | Backspace works in-game |  |  | No keyboard filter applied |
| G07 | physical hardware | Physical JIS `@` key | `@` is entered as `@` |  |  | Verify on the target keyboard, not a US-layout substitute |
| G08 | physical hardware | Shift+2 | `"` is entered as `"` |  |  | JIS symbol mapping |
| G09 | physical hardware | JIS punctuation | `^`, `:`, `¥`/backslash, `_`, `[`, and `]` all enter correctly |  |  | Record the physical key and resulting character |
| G10 | physical hardware | JIS Wi-Fi test password | A dedicated test AP accepts a password containing the symbols above |  |  | Do not include the SSID or PSK in shared evidence |

## Power and recovery

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| P01 | QEMU / physical | Chromium crash | Cage exits; service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P02 | QEMU / physical | Cage crash | Service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P03 | destructive-manual-approval-required | Power loss | On next boot, system returns to known-good kiosk state |  |  | Immutable SquashFS plus volatile overlay |
| P04 | destructive-manual-approval-required | Power loss during credential update | Root still boots; prior or new complete credential is present, never partial JSON |  |  | Sacrificial media; atomic replace does not prove ext4 durability |
| P05 | physical hardware | Normal shutdown | `SUSHIDA-CFG` unmounts without failure |  |  | Record exact unit if any unmount warning appears |
| P06 | physical hardware | Press the physical power button once | systemd-logind reaches the normal `poweroff.target` path and the guest/host test ends naturally |  |  | No acpid or custom event monitor is installed |
| P07 | physical hardware | Hold the physical power button | Long press is ignored; only the normal short-press action is supported |  |  | Confirm with firmware/ACPI behavior |
| P08 | QEMU | QEMU monitor `system_powerdown` | Dedicated BIOS/UEFI test exits naturally, serial logs show normal poweroff, and explicit `SUSHIDA-CFG` mount plus unmount evidence is present |  |  | Monitor socket must be below `build/qemu`; result is bound to current Git commit and release checksums |

## Audio

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| A01 | physical hardware | Play Sushi-da game audio | Audio is audible on the selected output |  |  | PipeWire + WirePlumber |

## Graphics

| ID | Class | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| V01 | physical hardware | Check WebGL | Chromium uses WebGL without deliberate GPU disable flags |  |  | No --disable-gpu or --disable-webgl |
| V02 | physical hardware | Check HW acceleration | GPU-accelerated compositing is active |  |  | --ozone-platform=wayland |

## Registry: 実行記録（PASS の唯一の根拠）

上の各表の `Actual result` / `Pass/Fail` は、この registry に対応する記録行が
あるときだけ埋めてよい。**未実施は PASS にしない。古い ISO の結果を最新 ISO に
流用しない**（ISO SHA が変わったら再実施するまで空欄に戻す）。

記録 schema（1 実行 = 1 行。secret・SSID・PSK・MAC を書かない）:

| Run | 対象 ID | Class | 対象 commit | ISO SHA-256 | 環境（機種/FW/QEMU 版） | 手順との差分 | 結果 (PASS/FAIL) | 確認日 | 確認者 | 証拠（log/screenshot パス） |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | D01, D02 | automated | `789ac24` | `d541644fc5fadee372c350cabba539cd65d319e98301da540547b78468d87dac` | rootless podman `--privileged` builder (trixie) on WSL2 | clone 上で実行（本 repo と同一 commit）。単独 `make verify` は privileged で実施 | PASS | 2026-07-21 | agent (Claude) / 依頼: repo owner | `~/code/sushida-os-iso-validation/build/iso-build.log`（会期外は再ビルドで再現） |
| R2 | D01, D02 | automated | `c9dd1ad` | `aebbd14b36673ac2360a3590b98cb904746b24bdea748d1fd0f9ec95216bf745` | rootless podman `--privileged` builder (trixie), WSL2 | BL-01/02/04 反映後の最終ビルド。verify は build 内で実行 | PASS | 2026-07-21 | agent (Claude) / 依頼: repo owner | `~/code/sushida-os-iso-validation/build/iso-build.log` |
| R3 | D03, D04, K01（QEMU 範囲）, P08 | QEMU | `c9dd1ad` | `aebbd14b36673ac2360a3590b98cb904746b24bdea748d1fd0f9ec95216bf745` | QEMU 10.x TCG（builder コンテナ、KVM なし）、BIOS+UEFI 各 900s | `make test-qemu-boot` + `make test-qemu-powerdown`。BIOS/UEFI とも production bootloader→kiosk 起動、自然 poweroff、SUSHIDA-CFG（by-UUID）mount/unmount 証跡 | PASS | 2026-07-21 | agent (Claude) | `build/qemu/{bios,uefi}-offline{,-powerdown}/serial.log` + `result.env` |
| R4 | D03, D12（QEMU 範囲）, D05 補助 | QEMU | `c9dd1ad` | `aebbd14b36673ac2360a3590b98cb904746b24bdea748d1fd0f9ec95216bf745` | 同上、BIOS smoke 観測 1500s | `make test-qemu-runtime` 相当（BIOS）。screenshot 完全性・login prompt 不在・kiosk/graphical 到達・config FS + Wi-Fi service 起動の 8 判定 | PASS | 2026-07-21 | agent (Claude) | `build/qemu/bios-offline/{screenshot.png,serial.plain.log,result.env}` |
| R5 | D03, D12（UEFI smoke） | QEMU | `c9dd1ad` | `aebbd14b36673ac2360a3590b98cb904746b24bdea748d1fd0f9ec95216bf745` | 同上、UEFI smoke（OVMF + TCG） | screenshot 完全性判定が不成立（OVMF+TCG では post-GOP scanout が黒のままになり得る既知制約。serial では graphical.target・全 service 起動を確認） | FAIL（環境制約。KVM または実機で要再実施） | 2026-07-21 | agent (Claude) | `build/qemu/uefi-offline/serial.plain.log` |

Class の定義:

- `automated`: リポジトリ内の自動テスト（commit に紐づく）
- `QEMU`: 有界 QEMU 実行（serial log / screenshot が証拠）
- `manual VM`: 手動 VM 操作
- `physical hardware`: 実機（`hardware-compatibility.md` の matrix 記載機で実施）
- `destructive-manual-approval-required`: 犠牲ハードでの破壊試験。事前承認必須

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
| D22 | Blocked navigation auto-recovers | Navigation watcher static tests; manual K39 series hardware validation |

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
