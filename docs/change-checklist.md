# Change-impact checklist

- 作成: 2026-07-21（Stage F-08）。PR template（`.github/pull_request_template.md`）の
  詳細版。該当する行だけ確認し、該当なしはスキップしてよい。
- 原則 P1〜P5（各 commit 単独緑 / 挙動テスト不変 / 新規ファイル3点セット /
  dual-write / secret 非露出）は `docs/refactoring-work-order.md` §2.2 が正本。

| 変更した領域 | 確認すること |
|---|---|
| runtime contract の値 | 値の変更は仕様変更（リファクタリング不可）。checker adapter・docs・acceptance registry への波及を同一 commit で。停止条件に該当しないか |
| release contract / mapping | `verify-iso.sh` は contract を実行するため、schema・region・mode・verification level の整合。fixture（`test_check_contracts.py` / `verify-stale.bats`）追随 |
| 新規 production ファイル | **3点セット**: release contract（mapping + required_iso_paths）、`090-validate-image.hook.chroot`、fixture stub。P3 |
| systemd service 追加・変更 | contract `required_services`、enable hook、validate hook、sandboxing 項目、`test_systemd_units.py` |
| package 追加 | `kiosk.list.chroot` ↔ contract `required_packages` ↔ validate hook。禁止 package でないこと |
| Chromium policy | checker の allow/blocklist 照合、navigation watcher の `classify_url` との境界一致、K シリーズ受け入れ項目 |
| Wi-Fi backend / state | characterization test（66件）**本体無変更**で緑か（P2）。secret 非露出（P5）。`docs/wifi-state-machine.md` の不変条件 |
| route / watcher / signal | route 3者一致（launcher / netwatch / routes.py）。bats 挙動テスト無変更。同一 route で signal しないこと |
| on-disk protocol | dual-write で導入し正本交代は別タスク（P4）。fail-closed read |
| QEMU テスト | dry-run bats の安全条件（read-only ISO、bounded 実行）維持 |
| artifact metadata | build-info schema_version・hash 相互照合・`reproducible-builds.md` の分類更新 |
| build 再現性 | package pin を導入していないこと。SOURCE_DATE_EPOCH 系の制御を壊していないこと |
| docs | 値の直書きをしていないこと（`documentation-map.md`）。README リンク・`make help` との整合 |
| acceptance | 実機挙動に触れる変更は該当 K/G/P/A/V 項目の registry 再実施が必要か判断 |
| secret / 権限境界 | 資格情報・token・機体識別子が diff に無いこと。privilege 境界（kiosk/wifi-setup account、polkit）を広げていないこと |
| STRUCTURE.txt | ファイル追加/削除をしたら `python3 tools/gen-structure.py`（`make check-structure` が CI で検出） |
| TASKS.md | backlog 状態の昇格に証拠を付けたか。DONE の条件を満たすか |

最終確認（全変更共通）:

```bash
python3 tools/check-contracts.py
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make check-structure
git diff --check
# shell を触ったら: make container-shell CONTAINER_ENGINE=podman
```
