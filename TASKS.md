# Sushi-da OS task backlog

- 形式改訂: 2026-07-21（Stage F-03）。旧「実装タスク 1〜20」を task record 形式へ変換。
- Status: `BACKLOG / READY / IN_PROGRESS / BLOCKED / REVIEW / DONE / DEFERRED`
- **DONE には証拠（commit、実機・ISO 系は ISO SHA と確認日）が必須。**
  「設計済み」「実装済みだが実機未確認」は DONE にしない（per-task 注記で区別）。
- 進捗の物語・逸脱の記録は `docs/refactoring-work-order.md` が正本。
  受け入れ試験の証拠は `docs/acceptance-tests.md` が正本。
  `AGENTS.md` is the authoritative project contract and takes precedence over
  this file.

## Record schema

```text
ID / Title
Status | Severity | Dependency
Scope: 触ってよい範囲
Acceptance criteria: 完了条件（検証可能な形）
Verification: 自動検証（コマンド・テスト）
Manual checks: 人手・実機での確認（未実施なら明記）
Out of scope: 含まないこと
Evidence: commit / ISO SHA / 確認日（DONE のみ）
```

## 1. 初期実装タスク（旧 Task 1〜20） — 全て実装済み

旧形式の詳細手順は git 履歴（2026-07-20 以前の本ファイル）を参照。
20 タスクは実装・自動テストとも完了しているが、**実機での受け入れ確認は
`docs/acceptance-tests.md` の registry が正本**であり、未実施項目はそちらで管理する。

| ID | 旧タスク | Status | Evidence（代表） |
|---|---|---|---|
| T01 | 静的テスト基盤 | DONE | pytest 658件（`make test-static`） |
| T02 | Debian 13 builder container | DONE | `builder/Dockerfile`、`make builder` |
| T03 | live-build 基本構成 | DONE | `live-build/auto/*`、`test_live_build_config.py` |
| T04 | production package list | DONE | `kiosk.list.chroot` ↔ contract `required_packages` |
| T05 | kiosk account 制約 | DONE | `010-create-kiosk-user.hook.chroot` + validate hook |
| T06 | Chromium launcher | DONE | `sushida-launch` + `launch.bats` |
| T07 | kiosk systemd service | DONE | `sushida-kiosk.service` + `test_systemd_units.py` |
| T08 | Chromium managed policy | DONE | policy JSON + checker allow/blocklist 照合 |
| T09 | console/escape lockdown | DONE | `050-lock-down-system.hook.chroot` + `test_lockdown.py` |
| T10 | networking + 制約付き Wi-Fi 設定 | DONE | `sushida_os.wifi` package + characterization 66件 |
| T11 | offline / network 復帰 | DONE | route model + `network-watch.bats` |
| T12 | audio/graphics/Wayland | DONE | session helper + bats/静的テスト |
| T13 | read-only runtime 設計 | DONE | tmpfs/`/run` 設計、`docs/architecture.md` |
| T14 | image 内 validation | DONE | `090-validate-image.hook.chroot` |
| T15 | ISO build + artifacts | DONE | `scripts/build.sh`（Stage E で manifest 駆動化） |
| T16 | artifact 検証・cleanup | DONE | `verify-iso.sh` + `verify-stale.bats` 13件 |
| T17 | QEMU 実行・smoke | DONE | `run-qemu.sh` + QEMU dry-run bats（実 QEMU 実行は BL-05） |
| T18 | safe diagnostics | DONE | `sushida-diagnostics` |
| T19 | guarded removable-media 書き込み | DONE | `flash.sh` + `test_flash_safety.py` |
| T20 | 文書・受け入れ整備 | DONE | Stage F（`docs/documentation-map.md` ほか） |

T10 の不変条件（維持事項）: Wi-Fi 設定 UI は fixed loopback-only provisioning
page のまま維持する。A general Wi-Fi settings GUI remains prohibited —
選択した SSID への接続と単一資格情報の保存だけを行い、汎用（general-purpose）
設定画面への拡張は明示的な設計判断なしに行わない。Keep real credentials out of
production Git history.

## 2. 繰延 backlog（refactoring-work-order §7 より変換）

### BL-01 / runtime-state.json への正本切替

- Status: DONE | Severity: Medium | Dependency: なし
- Evidence: 2026-07-21。launcher/netwatch とも protocol module 経由へ切替、
  旧 active-route / time-sync-required ファイル廃止。bats 218 全緑
  （state 破損・未知 schema・time-sync hold/解除の新4件含む）、checker exit 0。
  QEMU での route 遷移確認は BL-05 の残項目に含む。
- Scope: launcher / network watcher / runtime contract / checker `DRIFT_PATH` /
  `launch.bats`・`network-watch.bats`（挙動テストの書き換えを伴う唯一の backlog）
- Acceptance criteria: watcher が `runtime-state.json` を読み、
  `active-route`・`time-sync-required` ファイルが廃止される。dual-write 終了。
- Verification: bats 全緑 + checker exit 0 + `test_runtime_state.py`
- Manual checks: QEMU で route 遷移（online↔setup↔offline）
- Out of scope: route 値・遷移条件の変更

### BL-02 / connection_in_progress の実出力

- Status: DONE | Severity: Low | Dependency: BL-01
- Evidence: 2026-07-21。coordinator が専用 0755 dir の内容なし marker を発行
  （best-effort・テストは opt-in）、netwatch が毎周期 state file に鏡映
  （`--set-connection-in-progress` RMW）。characterization 66件無変更、
  marker lifecycle 5件 + CLI + bats 2件追加。
- 設計判断: wifi-setup は kiosk の runtime dir に書けない（権限境界維持）ため、
  `/run/sushida-wifi-status` を新設して片方向・内容なしの existence flag のみ共有。
- 残: watcher が in-progress 中に restart を抑制する利用は別タスク（必要になれば登録）

### BL-03 / `time-sync` 専用 route 化の判断

- Status: DONE | Severity: Low | Dependency: BL-01
- 決定 (2026-07-21): **専用 route 化しない**。
  根拠: (a) state protocol の `time_sync_required` が route と直交する独立
  フィールドとして既に存在し、消費者は判別可能 (b) 専用 route は contract
  `routes` の3者照合・launcher のページ選択・専用ページ新設まで波及するが、
  低頻度シナリオ（RTC 異常）に対する UI 差別化の便益が現状ない
  (c) route 集合の安定はチェック機構を単純に保つ。
  routes.py の予約コメント（将来 `time-sync`）は維持し、専用ページの需要が
  生じた時点で backlog を再登録する。

### BL-04 / 初版スコープ外の独立ハードニング

- Status: DONE | Severity: Medium | Dependency: 独立
- Evidence: 2026-07-21、3項目とも実装（commit `e09c5ec`）:
  1. ラベル衝突: config partition を固定 UUID で mount（公開リポジトリのため
     秘匿性はなく「偶発衝突への頑健化」。改竄耐性ではないと明記）
  2. RTC 判定: 下限を image build epoch（SOURCE_DATE_EPOCH 由来の config
     mtime）+5年の窓に変更。stat 失敗時は旧固定値に fallback
  3. console=ttyS0 方針: `--bootappend-live` で既定 BIOS/UEFI entry に
     serial console + systemd status（実 ISO 診断で既定 entry が serial
     なしだった事実に基づく）。VGA は quiet のまま
- 実 ISO/QEMU での確認は BL-05 の再ビルド検証に含む

### BL-05 / 実 ISO・QEMU・実機検証の消化

- Status: IN_PROGRESS | Severity: High | Dependency: 実機（+ KVM 環境が望ましい）
- 済み (2026-07-21、registry R1〜R5):
  - `make iso && make verify`: PASS ×2（`789ac24`→R1、最終 `c9dd1ad`→R2。
    exact 31件 byte/mode/owner・partition・bootloader・metadata 相互照合すべて成立）
  - QEMU boot（BIOS/UEFI）: PASS — production bootloader から kiosk service 到達
  - QEMU powerdown（BIOS/UEFI）: PASS — 自然 poweroff + SUSHIDA-CFG（by-UUID）
    mount/unmount 証跡
  - QEMU smoke（BIOS）: PASS — screenshot 完全性・login prompt 不在・
    graphical.target・config FS/Wi-Fi service 起動
  - 途中で検出・修正した基盤バグ: boot 待機の 120s 固定（`d0a23c1`）、
    serial 照合の pipefail×SIGPIPE（`c9dd1ad`）、既定 boot entry の
    serial console 欠如（`e09c5ec`、BL-04-3）
- 済み (2026-07-22 追記):
  - QEMU smoke（UEFI）: PASS — KVM 有効化（ユーザーが kvm グループ追加・再起動）
    後、builder コンテナ + `/dev/kvm` で AUTOMATED 8 判定すべて成立（registry R6。
    旧 TCG 失敗は R5 のまま保存）。QEMU 側の残項目はこれで消化
  - 実機一次確認（ユーザー報告 2026-07-22、非公式）: ログイン画面なしで起動、
    Wi-Fi 設定→接続成功、全画面 Chromium で寿司打プレイ可、キーボード入力正常。
    同時に発見された不具合: 再起動後の SSID 復元失敗（`62d545a` で修正）、
    音声が出ない（W-3 対応中）
- 残:
  1. 実機回帰: acceptance registry の physical hardware 分類全項目
     （K/G/P/A/V シリーズ）の正式記録
- Acceptance criteria: 残項目が registry に記録されること

### BL-06 / kiosk-signal の shell/Python 双子の同一性照合

- Status: DONE | Severity: Low | Dependency: なし
- Acceptance criteria: 検証連鎖（active・MainPID・UID・cgroup・TERM）が
  2 実装で一致することを自動テストが証明する
- Verification: `tests/static/test_kiosk_signal_equivalence.py` —
  11 シナリオ（正常系 + 全 refuse 経路）を両実装に同時適用し判定一致を検査
- Evidence: 2026-07-21、11/11 pass（commit は本タスクの commit）

## 3. 実機フィードバック対応（2026-07-22、ユーザー承認済みタスク）

### FB-01 / 再起動後の SSID 復元失敗の修正

- Status: DONE | Severity: High
- 症状: 再起動後、設定ページに「SSIDが見つかりません」。原因は Wi-Fi アダプタの
  firmware ロード / NM takeover 完了前に復元リトライ（旧 5 回）が尽きること。
- 対応: `nmcli.wifi_device_waiting()`（unmanaged/unavailable のときのみ true、
  照会失敗は false で fail-open）を復元ループでポーリングし、リトライを消費せず
  待機（120s deadline は不変）。リトライ上限 5→8（runtime contract 同時更新）。
- Verification: `tests/static/test_wifi_restore_readiness.py`（新規）、
  characterization 75 件不変、checker 0
- Manual checks: 実機での再起動→自動再接続は未確認（次回実機試験で確認）
- Evidence: `62d545a` / 2026-07-22

### FB-02 / 画面拡大率 2 倍

- Status: DONE | Severity: Medium
- 対応: sushida-session の Chromium 引数に `--force-device-scale-factor=2`。
  サイト DOM・注入は一切なし（AGENTS §1 遵守）。
- Verification: `test_launcher.py::test_helper_display_scale_is_fixed_two`
- Manual checks: 実機での見え方は未確認
- Evidence: `c76fdeb` / 2026-07-22

### FB-03 / ノート PC で音声が出ない

- Status: DONE（イメージ側） | Severity: High
- 対応: `firmware-sof-signed` + `alsa-ucm-conf` を package list / release
  contract / 090 hook に追加（post-2019 Intel ノートは SOF なしでカード自体が
  出ない）。加えて FB-04 の起動時 unmute / 既定音量適用。
- Manual checks: 実機での発音確認は再ビルド ISO で要確認
- Evidence: `8910c99` / 2026-07-22

### FB-04 / 音量・輝度のホットキー + 起動時初期値

- Status: DONE（イメージ側） | Severity: Medium
- 対応: 新規 root サービス `sushida-input-watch`（python3-evdev）。固定
  キー→アクション表（VOLUMEUP/DOWN/MUTE/BRIGHTNESSUP/DOWN）、amixer 固定
  argv・sysfs backlight 書き込みのみ、レート制限 0.15s、輝度下限 5%（黒画面
  防止）。config.env に `AUDIO_VOLUME_PERCENT=70`（session が wpctl で
  best-effort 適用）と `SCREEN_BRIGHTNESS_PERCENT=80`（daemon が適用）。
  3 点登録（release contract mapping / 090 hook / fixture）+ service enable。
- Verification: `tests/static/test_input_watch.py`（新規）、checker 0、
  bats 220
- Manual checks: 実機ホットキー動作は再ビルド ISO で要確認
- Evidence: （本コミット） / 2026-07-22

### FB-05 / CI（docker root 実行）での verify-stale 5 件失敗

- Status: DONE | Severity: High
- 原因: git-archive の tar.umask 既定 002 によるモード正規化（dir 0775 /
  file 0664）を root 実行の GNU tar が保存し、fixture が契約宣言モードと
  乖離。ローカル非 root 実行では umask 022 で偶然正規化され検出不能だった。
  新 builder イメージでは tar の fchmodat 系 syscall を seccomp が拒否する
  別問題も併発。
- 対応: fixture 展開を Python tarfile + 明示モード正規化（0755/0644）へ。
  root（CI 形）14/14・非 root gate 220/220 で検証。
- Evidence: `650e642` / 2026-07-22

## 4. 運用ルール（旧 Working rules の後継）

- 1 タスク = 1 commit（`docs/refactoring-work-order.md` §1.2 の git 運用に従う）
- 実装とテストは同じタスクで完結させる（原則 P1〜P5 は work order §2.2）
- Do not claim a test passed unless the command was executed successfully.
- Do not fetch, copy, modify, inject into, automate, or redistribute Sushi-da
  content. Never run a flashing script against a real block device during
  development.
- タスクの昇格・完了はこのファイルを更新し、証拠列を埋めてから行う
