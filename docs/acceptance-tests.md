# Acceptance tests

| ID | Operation | Expected result | Actual result | Pass/Fail | Notes |
|---|---|---|---|---|---|
| K01 | Power on | Kiosk starts without a login screen |  |  |  |
| K02 | Alt+Tab | No application switcher appears |  |  |  |
| K03 | Alt+F4 | Kiosk remains or restarts within 5 seconds |  |  |  |
| K04 | Ctrl+Alt+T | No terminal opens |  |  |  |
| K05 | Ctrl+Alt+F2 | No usable login console appears |  |  |  |
| K06 | Ctrl+L | Address bar cannot be used |  |  |  |
| K07 | Ctrl+T | No new tab opens |  |  |  |
| K08 | Ctrl+Shift+I | Developer tools do not open |  |  |  |
| K09 | F12 | Developer tools do not open |  |  |  |
| K10 | Disconnect network | Local offline screen appears |  |  |  |
| K11 | Restore network | Sushi-da page returns automatically |  |  |  |
| K12 | Type normal gameplay text | Letters, symbols, Space, Enter and Backspace work |  |  |  |
| K13 | Power loss and restart | System returns to known-good kiosk state |  |  |  |
| K14 | Play game audio | Audio is audible on the selected output |  |  |  |
| K15 | Check WebGL | Chromium uses WebGL without deliberate GPU disable flags |  |  |  |
