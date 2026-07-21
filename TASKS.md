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

- Status: BACKLOG | Severity: Low | Dependency: BL-01
- Scope: Wi-Fi coordinator → runtime_state 連携
- Acceptance criteria: 接続試行中に state file の `connection_in_progress` が true
- Verification: characterization test 拡張
- Out of scope: watcher 側での利用（別タスク）

### BL-03 / `time-sync` 専用 route 化の判断

- Status: BACKLOG | Severity: Low | Dependency: BL-01
- Acceptance criteria: 専用 route 化する/しないの決定が work order に記録され、
  する場合は routes model・contract `routes`・checker・bats が一括更新される
- Out of scope: 決定前の実装

### BL-04 / 初版スコープ外の独立ハードニング

- Status: BACKLOG | Severity: Medium | Dependency: 独立
- 内容: SUSHIDA-CFG ラベル衝突対策 / RTC 判定改善 / console=ttyS0 方針
- Acceptance criteria: 各項目ごとに設計判断 + 実装 + テスト（3 子タスクに分割して着手）

### BL-05 / 実 ISO・QEMU・実機検証の消化

- Status: IN_PROGRESS | Severity: High | Dependency: ビルド環境
- 進捗 (2026-07-21): `make iso && make verify` は **PASS**（commit `789ac24`、
  ISO SHA `d541644f…`、acceptance registry R1）。exact 31件の byte/mode/owner
  照合・partition stage・bootloader 配置とも実 ISO で成立し、contract の降格は
  不要だった。残: QEMU 系・実機回帰。
  既知の制約: rootless podman では `make container-verify`（非 privileged）が
  bind mount 上の scratch 作成で失敗する。privileged 実行か docker を使う。
- 内容: `make iso && make verify`（exact 昇格の positive 検証・partition stage 含む）、
  `make test-qemu*`、実機回帰（work order §4.3/§4.4 の未実行項目）
- Acceptance criteria: verify exit 0 の実 ISO が存在し、acceptance registry に
  commit / ISO SHA / 確認日つきで記録される。exact 昇格で乖離が出た mapping は
  証拠つきで contract を修正する
- Verification: `make iso && make verify`、`make test-qemu-runtime`
- Manual checks: acceptance registry の QEMU/実機分類の全項目

### BL-06 / kiosk-signal の shell/Python 双子の同一性照合

- Status: DONE | Severity: Low | Dependency: なし
- Acceptance criteria: 検証連鎖（active・MainPID・UID・cgroup・TERM）が
  2 実装で一致することを自動テストが証明する
- Verification: `tests/static/test_kiosk_signal_equivalence.py` —
  11 シナリオ（正常系 + 全 refuse 経路）を両実装に同時適用し判定一致を検査
- Evidence: 2026-07-21、11/11 pass（commit は本タスクの commit）

## 3. 運用ルール（旧 Working rules の後継）

- 1 タスク = 1 commit（`docs/refactoring-work-order.md` §1.2 の git 運用に従う）
- 実装とテストは同じタスクで完結させる（原則 P1〜P5 は work order §2.2）
- Do not claim a test passed unless the command was executed successfully.
- Do not fetch, copy, modify, inject into, automate, or redistribute Sushi-da
  content. Never run a flashing script against a real block device during
  development.
- タスクの昇格・完了はこのファイルを更新し、証拠列を埋めてから行う
