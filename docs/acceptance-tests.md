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
| K32 | Disconnect network | Local offline screen appears |  |  | Task 11 network watcher |
| K33 | Restore network | Sushi-da page returns automatically |  |  | Task 11 network watcher |

## Gameplay input

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| G01 | Letters (a-z) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G02 | Digits (0-9) | Typed characters appear in-game |  |  | No keyboard filter applied |
| G03 | Punctuation | Typed characters appear in-game |  |  | No keyboard filter applied |
| G04 | Space | Space character works in-game |  |  | No keyboard filter applied |
| G05 | Enter | Enter key works in-game |  |  | No keyboard filter applied |
| G06 | Backspace | Backspace works in-game |  |  | No keyboard filter applied |

## Power and recovery

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| P01 | Chromium crash | Cage exits; service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P02 | Cage crash | Service restarts within 5 seconds |  |  | Restart=always + RestartSec=3 |
| P03 | Power loss | On next boot, system returns to known-good kiosk state |  |  | Read-only root (Task 13) |

## Audio

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| A01 | Play Sushi-da game audio | Audio is audible on the selected output |  |  | PipeWire + WirePlumber |

## Graphics

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| V01 | Check WebGL | Chromium uses WebGL without deliberate GPU disable flags |  |  | No --disable-gpu or --disable-webgl |
| V02 | Check HW acceleration | GPU-accelerated compositing is active |  |  | --ozone-platform=wayland |
