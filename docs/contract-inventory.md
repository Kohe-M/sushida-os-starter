# Contract inventory

Every column and its meaning:

| Column | Meaning |
|---|---|
| ID | Unique identifier for this contract item |
| Domain | Area of the system (url, path, route, service, timeout, artifact) |
| Contract item | What is being specified |
| Current value | The actual value found in the codebase |
| Production source | Which production file is the authoritative reference |
| Other references | Where else this value appears |
| Mismatch | YES when production sources disagree, NO when consistent, N/A for single source |
| Candidate contract field | Proposed field name in the contract schema |
| Automatable | YES / PARTIAL / NO — can automated validation verify this? |
| Notes | Ambiguities, history, or rationale |

## Runtime inventory

### URLs

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| URL-01 | url | Sushi-da play URL | `https://sushida.net/play.html` | `config.env` | launcher, session, policy allowlist, watcher test | NO | `sushida_url` | YES | Default; overridable via `SUSHIDA_URL` in config.env |
| URL-02 | url | Setup page URL | `http://127.0.0.1:8787/` | sushida_os/wifi/web.py (HOST+PORT) | launcher, session, policy allowlist, launcher SETUP_URL | NO | `setup_url` | YES | Scheme, host, port are fixed |
| URL-03 | url | Offline page URL | `file://localhost/usr/share/sushida-os/offline.html` | launcher (OFFLINE_URL) | session, policy allowlist, docs | NO | `offline_url` | YES | Both `file://localhost/...` and `file:///...` forms exist |
| URL-04 | url | Time-sync page URL | (not implemented) | — | — | N/A | `time_sync_url` | YES | Future: `file:///usr/share/sushida-os/time-sync.html` |
| URL-05 | url | Navigation allowlist | `https://.sushida.net:443` | Chromium policy JSON | launcher patterns, watcher classify_url | NO | `nav_allowlist` | YES | Leading dot = exact host match (no subdomains) |
| URL-06 | url | Navigation blocklist | `["*", "view-source:*", "chrome://*", "chrome-untrusted://*", "devtools://*"]` | Chromium policy JSON | watcher classify_url | NO | `nav_blocklist` | YES | Combined default-deny + internal URL blocks |

### Runtime paths

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| RTP-01 | path | Runtime directory | `/run/sushida-os` | kiosk.service (RuntimeDirectory) | launcher, watchers, tmpfiles.d | NO | `runtime_dir` | YES | 0750, user kiosk |
| RTP-02 | path | Runtime state file (schema 1) | `$RUNTIME_DIR/runtime-state.json` | sushida-launch（`sushida_os.runtime.runtime_state` 経由で発行） | network-watch（同 module で読取・time-sync 解除） | NO | `runtime_state_file` | YES | BL-01 で active-route / time-sync-required を置換。fail-closed read |
| RTP-03 | path | （廃止: time-sync marker） | — | — | — | — | — | — | time_sync_required は RTP-02 のフィールドへ統合（BL-01） |
| RTP-04 | path | Wi-Fi setup runtime state | `/run/sushida-wifi-setup/` | wifi-setup.service (RuntimeDirectory) | sushida_os/wifi/storage.py (CSRF_TOKEN_FILE) | NO | `wifi_setup_runtime_dir` | YES | 0700, user wifi-setup |
| RTP-04a | path | Wi-Fi progress marker | `/run/sushida-wifi-status/connection-in-progress` | sushida_os/wifi/storage.py（coordinator が best-effort 発行） | network-watch（存在を state file へ鏡映） | NO | `wifi_connection_marker` | YES | 内容なし existence flag。0755 専用 dir（tmpfiles）+ unit ReadWritePaths |
| RTP-05 | path | CSRF token file | `/run/sushida-wifi-setup/csrf-token` | sushida_os/wifi/storage.py (CSRF_TOKEN_FILE) | — | NO | `csrf_token_file` | YES | 0600, preserved across restart |
| RTP-06 | path | Config mount path | `/var/lib/sushida-config` | mount unit (Where=) | config-prepare (CONFIG_MOUNT), sushida_os/wifi/storage.py | NO | `config_mount_path` | YES | ext4, rw, nodev, nosuid, noexec, noatime |
| RTP-07 | path | Config storage status | `/run/sushida-config/config-storage` | sushida-config-prepare | sushida_os/wifi/storage.py (STORAGE_STATUS) | NO | `config_storage_status` | YES | 0644, content "ready" or "unavailable" |
| RTP-08 | path | Credential file | `$CONFIG_MOUNT/network/setup.json` | sushida_os/wifi/storage.py (CONFIG_FILE) | persist_credentials, load_credentials | NO | `credential_file` | YES | 0600, wifi-setup owned |
| RTP-09 | path | Chromium profile | `$RUNTIME_DIR/chromium` | sushida-launch | sushida-session (--user-data-dir) | NO | `chromium_profile_dir` | YES | Volatile tmpfs |
| RTP-10 | path | Chromium session file | `$RUNTIME_DIR/chromium/Default/Sessions` | sushida-navigation-watch | sushida-session | NO | `chromium_sessions_dir` | YES | SNSS-format binary files |
| RTP-11 | path | QEMU smoke markers | `systemd.setenv=WLR_RENDERER=pixman, WLR_RENDERER_ALLOW_SOFTWARE=1, SUSHIDA_QEMU_CHROMIUM_SWIFTSHADER=1, SUSHIDA_QEMU_FORCE_OFFLINE=1` | scripts/run-qemu.sh | sushida-launch, sushida-navigation-watch (env checks) | NO | `qemu_smoke_markers` | YES | Kernel cmdline env vars, only in direct-kernel boot path |
| RTP-12 | path | QEMU boot test marker | `systemd.setenv=WLR_RENDERER=pixman` | scripts/run-qemu.sh | — | NO | `qemu_boot_marker` | YES | Checked in serial log |

### Routes

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| RTE-01 | route | Route type: online | `"online"` | sushida-launch (ACTIVE_ROUTE) | network-watch (desired_route) | NO | `route_online` | YES | NM connected:full |
| RTE-02 | route | Route type: setup | `"setup"` | sushida-launch | network-watch | NO | `route_setup` | YES | wifi-setup service active |
| RTE-03 | route | Route type: offline | `"offline"` | sushida-launch | network-watch | NO | `route_offline` | YES | Default fallback |
| RTE-04 | route | Route type: time-sync | (not implemented as distinct route) | — | — | N/A | `route_time_sync` | YES | Future: separate route for time-sync page |

### Services

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| SRV-01 | service | Kiosk service | `sushida-kiosk.service` | Unit file (sushida-kiosk.service) | enable hook, validate hook, watchers | NO | `kiosk_service` | YES | User=kiook, Restart=always |
| SRV-02 | service | Wi-Fi setup service | `sushida-wifi-setup.service` | Unit file | enable hook, validate hook, Before=kiosk | NO | `wifi_setup_service` | YES | User=wifi-setup, loopback-only |
| SRV-03 | service | Network watcher | `sushida-network-watch.service` | Unit file | enable hook, validate hook | NO | `network_watch_service` | YES | PartOf=kiosk |
| SRV-04 | service | Navigation watcher | `sushida-navigation-watch.service` | Unit file | enable hook, validate hook | NO | `navigation_watch_service` | YES | PartOf=kiosk |
| SRV-05 | service | Config prepare | `sushida-config-prepare.service` | Unit file | enable hook, validate hook | NO | `config_prepare_service` | YES | Before=wifi-setup |
| SRV-06 | service | Config mount | `var-lib-sushida\x2dconfig.mount` | Unit file | enable hook, validate hook, build.sh | NO | `config_mount_unit` | YES | Before=config-prepare |
| SRV-07 | service | Time sync service | `systemd-timesyncd.service` | Debian package | enable hook, validate hook | NO | `time_sync_service` | YES | Standard systemd service |
| SRV-08 | service | NetworkManager | `NetworkManager.service` | Debian package | enable hook, units' After/Wants | NO | `network_manager_service` | YES | Standard service |

### Timeouts and intervals

| ID | Domain | Contract item | Current value (s) | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| TMO-01 | timeout | Network setup grace | 15 | config.env (NETWORK_SETUP_GRACE_SECONDS) | sushida-launch | NO | `network_setup_grace_seconds` | YES | Default; configurable |
| TMO-02 | timeout | Network check interval | 30 | config.env (NETWORK_CHECK_INTERVAL_SECONDS) | sushida-network-watch | NO | `network_check_interval_seconds` | YES | Default; configurable, min 30 max 3600 |
| TMO-03 | timeout | Wi-Fi connect timeout | 40 | sushida_os/wifi/nmcli.py (COMMAND_TIMEOUT_SECONDS) | nmcli --wait 30 in connect_wifi | NO | `wifi_connect_timeout_seconds` | PARTIAL | Nmcli per-stage timeout |
| TMO-04 | timeout | Restore retry backoff min | 2.0 (seconds) | sushida_os/wifi/restore.py (BACKOFF_MIN) | — | NO | `restore_backoff_min_seconds` | PARTIAL | Bounded exponential backoff |
| TMO-05 | timeout | Restore retry backoff max | 16.0 (seconds) | sushida_os/wifi/restore.py (BACKOFF_MAX) | — | NO | `restore_backoff_max_seconds` | PARTIAL | Bounded exponential backoff |
| TMO-06 | timeout | Restore max retries | 5 | sushida_os/wifi/restore.py (MAX_RETRIES) | — | NO | `restore_max_retries` | YES | Integer count |
| TMO-07 | timeout | Restore deadline | 120 (seconds) | sushida_os/wifi/restore.py (deadline) | — | NO | `restore_deadline_seconds` | YES | Total retry window |
| TMO-08 | timeout | Navigation poll interval | 2.0 (seconds) | sushida-navigation-watch (DEFAULT_POLL_SECONDS) | — | NO | `nav_poll_interval_seconds` | YES | Configurable for tests |
| TMO-09 | timeout | Navigation cooldown | 30.0 (seconds) | sushida-navigation-watch (DEFAULT_COOLDOWN_SECONDS) | — | NO | `nav_cooldown_seconds` | YES | Between restarts |
| TMO-10 | timeout | HTTP read timeout | 5 (seconds) | sushida_os/wifi/web.py (REQUEST_READ_TIMEOUT_SECONDS) | — | NO | `http_read_timeout_seconds` | YES | Per-request |
| TMO-11 | timeout | HTTP max body size | 8192 (bytes) | sushida_os/wifi/web.py (MAX_REQUEST_BYTES) | — | NO | `http_max_request_bytes` | YES | Upper bound |
| TMO-12 | timeout | Session audio timeout | 3 (seconds) | sushida-session (AUDIO_TIMEOUT) | — | NO | `session_audio_timeout_seconds` | YES | Best-effort |

## Release inventory

### Artifacts

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| ART-01 | artifact | Release ISO | `sushida-os-amd64.iso` | build.sh, verify-iso.sh | README, clean.sh, flash.sh, run-qemu.sh | NO | `iso_name` | YES | Hybrid ISO, BIOS+UEFI |
| ART-02 | artifact | Checksum file | `SHA256SUMS` | build.sh | verify-iso.sh | NO | `sha256sums_name` | YES | Contains ISO sha256 |
| ART-03 | artifact | Package manifest | `package-manifest.txt` | build.sh | verify-iso.sh | NO | `package_manifest_name` | YES | Sorted package list |
| ART-04 | artifact | Build info | `build-info.json` | build.sh | verify-iso.sh | NO | `build_info_name` | YES | JSON with git commit, timestamp, versions |
| ART-05 | artifact | Output directory | `artifacts/` | build.sh | verify-iso.sh, clean.sh | NO | `artifact_dir` | YES | Repository-local |

### ISO paths (inside SquashFS)

| ID | Domain | Contract item | Current value | Production source | Other references | Mismatch | Candidate contract field | Automatable | Notes |
|---|---|---|---|---|---|---|---|---|---|
| ISO-01 | iso-path | Chromium policy | `/etc/chromium/policies/managed/sushida-os.json` | Policy file | build.sh (copy_tracked_tree) | NO | `chromium_policy_path` | YES | Security-critical |
| ISO-02 | iso-path | Kiosk unit | `/etc/systemd/system/sushida-kiosk.service` | Unit file | validate hook | NO | `kiosk_unit_path` | YES | Security-critical |
| ISO-03 | iso-path | Network watch unit | `/etc/systemd/system/sushida-network-watch.service` | Unit file | validate hook | NO | `network_watch_unit_path` | YES | Security-critical |
| ISO-04 | iso-path | Navigation watch unit | `/etc/systemd/system/sushida-navigation-watch.service` | Unit file | validate hook | NO | `navigation_watch_unit_path` | YES | Security-critical |
| ISO-05 | iso-path | Config prepare unit | `/etc/systemd/system/sushida-config-prepare.service` | Unit file | validate hook | NO | `config_prepare_unit_path` | YES | Security-critical |
| ISO-06 | iso-path | Wi-Fi setup unit | `/etc/systemd/system/sushida-wifi-setup.service` | Unit file | validate hook | NO | `wifi_setup_unit_path` | YES | Security-critical |
| ISO-07 | iso-path | Config mount unit | `/etc/systemd/system/var-lib-sushida\x2dconfig.mount` | Unit file | validate hook | NO | `config_mount_unit_path` | YES | Security-critical |
| ISO-08 | iso-path | Polkit rule | `/etc/polkit-1/rules.d/60-sushida-wifi-setup.rules` | Polkit file | validate hook | NO | `polkit_rule_path` | YES | Security-critical |
| ISO-09 | iso-path | NM config | `/etc/NetworkManager/conf.d/90-sushida-os.conf` | NM config | validate hook | NO | `nm_config_path` | YES | Security-critical |
| ISO-10 | iso-path | Launcher | `/usr/local/bin/sushida-launch` | Production script | validate hook | NO | `launcher_path` | YES | Security-critical |
| ISO-11 | iso-path | Network watch binary | `/usr/local/bin/sushida-network-watch` | Production script | validate hook | NO | `network_watch_bin_path` | YES | Security-critical |
| ISO-12 | iso-path | Navigation watch binary | `/usr/local/bin/sushida-navigation-watch` | Production script | validate hook | NO | `navigation_watch_bin_path` | YES | Security-critical |
| ISO-13 | iso-path | Diagnostics | `/usr/local/bin/sushida-diagnostics` | Production script | validate hook | NO | `diagnostics_path` | YES | Not security-critical |
| ISO-14 | iso-path | Session helper | `/usr/local/libexec/sushida-session` | Production script | validate hook | NO | `session_helper_path` | YES | Security-critical |
| ISO-15 | iso-path | Config prepare | `/usr/local/libexec/sushida-config-prepare` | Production script | validate hook | NO | `config_prepare_lib_path` | YES | Security-critical |
| ISO-16 | iso-path | Wi-Fi backend | `/usr/local/libexec/sushida-wifi-setup` | Production script | validate hook | NO | `wifi_setup_lib_path` | YES | Security-critical |
| ISO-17 | iso-path | Offline HTML | `/usr/share/sushida-os/offline.html` | HTML file | policy allowlist | NO | `offline_html_path` | YES | Static local page |
| ISO-18 | iso-path | Config env | `/etc/sushida-os/config.env` | Config file | launcher | NO | `config_env_path` | YES | Contains SUSHIDA_URL |
| ISO-19 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/__init__.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-20 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/__init__.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-21 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/types.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-22 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/storage.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-23 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-24 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/coordinator.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-25 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/restore.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-26 | iso-path | Wi-Fi backend module | `/usr/lib/python3/dist-packages/sushida_os/wifi/web.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-27 | iso-path | Runtime module | `/usr/lib/python3/dist-packages/sushida_os/runtime/__init__.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-28 | iso-path | Route decision model | `/usr/lib/python3/dist-packages/sushida_os/runtime/routes.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-29 | iso-path | Runtime state protocol | `/usr/lib/python3/dist-packages/sushida_os/runtime/runtime_state.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-30 | iso-path | Kiosk signal module | `/usr/lib/python3/dist-packages/sushida_os/runtime/kiosk_signal.py` | Python module | validate hook | NO | — | YES | Security-critical |
| ISO-31 | iso-path | Kiosk signal helper | `/usr/local/libexec/sushida-kiosk-signal` | Production script | validate hook | NO | — | YES | Security-critical |

### Source-image mappings

| ID | Domain | Source path | Image path | Region | Type | Comparison | Security critical |
|---|---|---|---|---|---|---|---|
| SIM-01 | mapping | `live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json` | `/etc/chromium/policies/managed/sushida-os.json` | squashfs | file (JSON policy) | `cmp` | YES |
| SIM-02 | mapping | (via auto/config copy_tracked_tree from includes.chroot) | `/etc/systemd/system/sushida-kiosk.service` | squashfs | file (systemd unit) | `cmp` | YES |
| SIM-03 | mapping | (via auto/config) | `/etc/systemd/system/sushida-network-watch.service` | squashfs | file | `cmp` | YES |
| SIM-04 | mapping | (via auto/config) | `/etc/systemd/system/sushida-navigation-watch.service` | squashfs | file | `cmp` | YES |
| SIM-05 | mapping | (via auto/config) | `/etc/systemd/system/sushida-config-prepare.service` | squashfs | file | `cmp` | YES |
| SIM-06 | mapping | (via auto/config) | `/etc/systemd/system/sushida-wifi-setup.service` | squashfs | file | `cmp` | YES |
| SIM-07 | mapping | (via auto/config) | `/etc/systemd/system/var-lib-sushida\x2dconfig.mount` | squashfs | file | `cmp` | YES |
| SIM-08 | mapping | (via auto/config) | `/etc/polkit-1/rules.d/60-sushida-wifi-setup.rules` | squashfs | file | `cmp` | YES |
| SIM-09 | mapping | (via auto/config) | `/etc/NetworkManager/conf.d/90-sushida-os.conf` | squashfs | file | `cmp` | YES |
| SIM-10 | mapping | (via auto/config) | `/usr/local/bin/sushida-launch` | squashfs | file (script) | `cmp` | YES |
| SIM-11 | mapping | (via auto/config) | `/usr/local/bin/sushida-network-watch` | squashfs | file | `cmp` | YES |
| SIM-12 | mapping | (via auto/config) | `/usr/local/bin/sushida-navigation-watch` | squashfs | file | `cmp` | YES |
| SIM-13 | mapping | (via auto/config) | `/usr/local/bin/sushida-diagnostics` | squashfs | file | `cmp` | NO |
| SIM-14 | mapping | (via auto/config) | `/usr/local/libexec/sushida-session` | squashfs | file | `cmp` | YES |
| SIM-15 | mapping | (via auto/config) | `/usr/local/libexec/sushida-config-prepare` | squashfs | file | `cmp` | YES |
| SIM-16 | mapping | (via auto/config) | `/usr/local/libexec/sushida-wifi-setup` | squashfs | file | `cmp` | YES |
| SIM-17 | mapping | (via auto/config) | `/usr/share/sushida-os/offline.html` | squashfs | file | `cmp` | NO |
| SIM-18 | mapping | (via auto/config) | `/etc/sushida-os/config.env` | squashfs | file | `cmp` | NO |
| SIM-19 | mapping | `builder/Dockerfile` + `builder/entrypoint.sh` | (builder image, not in ISO) | builder | file | `cmp` | YES |
| SIM-20 | mapping | ISO bootloader (generated by live-build) | `boot/grub/grub.cfg` | iso-root | file | `cmp` | YES |
| SIM-21 | mapping | `live-build/config/bootloaders/grub-pc/config.cfg` | (input to bootloader config) | — | file | `cmp` | YES |
| SIM-22 | mapping | `live-build/config/bootloaders/isolinux/live.cfg` | (input to bootloader config) | — | file | `cmp` | YES |
| SIM-23 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/__init__.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-24 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/__init__.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-25 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/types.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-26 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/storage.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-27 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-28 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/coordinator.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-29 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/restore.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-30 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/wifi/web.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-31 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/runtime/__init__.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-32 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/runtime/routes.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-33 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/runtime/runtime_state.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-34 | mapping | (via auto/config) | `/usr/lib/python3/dist-packages/sushida_os/runtime/kiosk_signal.py` | squashfs | file (Python module) | `cmp` | YES |
| SIM-35 | mapping | (via auto/config) | `/usr/local/libexec/sushida-kiosk-signal` | squashfs | file (script) | `cmp` | YES |

**Stage E (2026-07-21) 以降**: squashfs 領域の全 mapping は `current_verification: "exact"`（verify-iso.sh が byte 比較 + mode/owner/group を image 内で照合）。bootloader 入力（SIM-20〜22 相当）は iso-root presence として mapping / required_iso_paths / verify に登録済み。build-info.json は schema_version 1 で `source_date_epoch` / `release_contract_sha256` / `package_manifest_sha256` を持ち、verify が相互照合する。

### Metadata

| ID | Domain | Contract item | Source | Notes |
|---|---|---|---|---|
| META-01 | metadata | git_commit | build.sh (git rev-parse HEAD) | Current commit at build time |
| META-02 | metadata | git_dirty | build.sh (git status --porcelain) | Always false for release builds |
| META-03 | metadata | build_timestamp | build.sh (date -u) | ISO 8601 UTC |
| META-04 | metadata | architecture | build.sh (lb config --architectures) | amd64 |
| META-05 | metadata | iso_sha256 | build.sh (sha256sum) | Computed from final ISO |
| META-06 | metadata | chromium_version | build.sh (from package manifest) | From binary.packages |
| META-07 | metadata | cage_version | build.sh (from package manifest) | From binary.packages |
| META-08 | metadata | live_build_version | build.sh (lb --version) | From tool |
| META-09 | metadata | debian_release | build.sh (hardcoded) | trixie |

## Checker coverage (`tools/check-contracts.py`)

The contract checker implements the following check-only verifications against
the current production source tree.  No ISO image extraction or runtime
behaviour change is performed.

### Runtime verifications

| Domain | What is checked |
|---|---|
| `urls.sushida_url` | `config.env` `SUSHIDA_URL=` value |
| `urls.setup_url` | Literal URL in `sushida-launch` / `sushida-session`; port match in `sushida_os/wifi/web.py` (`PORT`) |
| `urls.offline_url` | Literal URL in `sushida-launch` / `sushida-session` |
| `runtime_paths.runtime_dir` | `PROD_RUNTIME` in launch/netwatch/navwatch; `RuntimeDirectory=` in kiosk unit |
| `runtime_paths.runtime_state_file` | runtime_dir 内であること + launch/netwatch が protocol module (`sushida_os.runtime.runtime_state`) を呼ぶこと + module の `STATE_BASENAME`/`PROD_RUNTIME_DIR` 宣言一致（BL-01 で active_route_file / time_sync_marker を置換） |
| `runtime_paths.wifi_setup_runtime_dir` / `csrf_token_file` | Dirname consistency; `CSRF_TOKEN_FILE` literal in `sushida_os/wifi/storage.py`; `RuntimeDirectory=` in wifi unit |
| `runtime_paths.config_mount_path` | Literals in `sushida_os/wifi/storage.py`, config-prepare, mount unit `Where=` |
| `runtime_paths.config_storage_status` / `credential_file` | Literals + derived components in `sushida_os/wifi/storage.py` + config-prepare |
| `runtime_paths.chromium_profile_dir` / `chromium_sessions_dir` | Basename in launch/session; `SESSIONS_SUBDIR` chain in navwatch |
| `timeouts.*` (14 fields: 2 in config.env + 12 in production scripts) | Literal values in the corresponding production sources, with config.env verbatim comparison and min-count checks for multi-site activation calls |
| `routes` | Set comparison: contract routes == launcher `ACTIVE_ROUTE=` literals == netwatch route `case` literals == `sushida_os/runtime/routes.py` `ROUTE_*` constants |
| `navigation` allowlist/blocklist | Chromium managed policy JSON `URLAllowlist`/`URLBlocklist` |
| `services.*` | Unit file existence in `includes.chroot/etc/systemd/system` |

### Release verifications

| Domain | What is checked |
|---|---|
| `artifacts` | Names referenced in `build.sh` / `flash.sh` / `clean.sh` / `verify-iso.sh` / `run-qemu.sh` |
| `required_packages` | Package list `kiosk.list.chroot` membership |
| `required_services` (enable) | Hook `020-enable-services.hook.chroot` references |
| `required_services` (mask) | Hook `090-validate-image.hook.chroot` references |
| `source_image_mappings` existence | Source files in the repository |
| `source_image_mappings` correspondence | squashfs region: `source == includes.chroot + image_path`; owner/group must be `root:root` |
| `source_image_mappings` mode | Filesystem mode matches contract declaration |
| `source_image_mappings` consistency | `current_verification: exact` ⇒ `comparison` must be `cmp` or `sha256` |
| `required_iso_paths` ↔ mappings | Every squashfs path has a mapping with matching `region/file_type/required/security_critical` |
| `required_iso_paths` iso-root | `verify-iso.sh` が release contract を読む manifest 駆動実装であること（個別 path 文字列の重複は廃止。Stage E-03） + contract 内の pattern↔path 自己整合 |
| `path_pattern` / `match_type` | When `match_type=regex`, the `path_pattern` must compile and match its own `path` |
| `metadata.required_fields` | Token presence in `build.sh` (git rev-parse, date, package_version, etc.) |
| `metadata.static_values` | Field/value pair match in `build.sh` (`--arg` jq form or `=` assignment) |
| `metadata.formats` | Keys must be a subset of `required_fields`; format names must be known (`git-sha`, `date-time`, `sha256`) |

### Deferred to subsequent phases

The checker operates on the **source tree only** (check-only, no ISO access).
The following are explicitly out of scope for this Phase and belong to later
stages of the refactoring programme:

- ISO image extraction (xorriso/unsquashfs) and byte-for-byte content comparison → **Phase 5**.
- `current_verification` upgrade from `presence` to `exact` → **Phase 5**.
- Runtime validation of generated `build-info.json` content (schema version, manifest hash, ISO SHA cross-check) → **Phase 5**.
- Bootloader region source mappings (SIM-19–22 in this inventory) are not yet registered in `release-contract.json` → **Phase 5** manifest canonicalisation.

### Error codes

| Code | Domain |
|---|---|
| `RUNTIME_URL_MISMATCH` / `DRIFT_URL` | URL mismatch |
| `DRIFT_PATH` | Runtime path mismatch |
| `DRIFT_TIMEOUT` | Timeout literal mismatch |
| `DRIFT_ROUTE` | Route set mismatch |
| `RUNTIME_ALLOWLIST_MISMATCH` / `RUNTIME_BLOCKLIST_MISMATCH` | Policy ↔ contract mismatch |
| `RUNTIME_SERVICE_MISSING` | Unit file not found |
| `DRIFT_METADATA_STATIC` / `DRIFT_METADATA` / `DRIFT_METADATA_FORMAT` / `DRIFT_METADATA_UNSUPPORTED` | Metadata inconsistency |
| `DRIFT_MAPPING_PATH` / `DRIFT_MAPPING_MODE` / `DRIFT_MAPPING_OWNER` / `DRIFT_COMPARISON` | Mapping inconsistency |
| `DRIFT_ISO_PATH` / `DRIFT_ISO_PATH_ATTR` / `DRIFT_PATH_PATTERN` | ISO path inconsistency |
| `RELEASE_ARTIFACT` / `RELEASE_ARTIFACT_REF` / `RELEASE_PACKAGE_MISSING` / `DRIFT_SERVICE_ENABLE` / `DRIFT_SERVICE_MASK` / `RELEASE_CHECKSUM` / `RELEASE_PUBLISH` | Release consistency |
