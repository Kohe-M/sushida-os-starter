# Documentation map（情報 → 正本 → 参照先）

- 作成: 2026-07-21（Stage F-01）
- ルール: **各情報の正本は 1 箇所**。他の文書は値を書き写さず正本を参照する。
  値の重複が必要な場合は checker / テストで drift 検出されるものに限る。

| 情報 | 正本 (source of truth) | 主な参照先 | drift 検出 |
|---|---|---|---|
| runtime の URL・パス・timeout・route 値 | `contracts/runtime-contract.json` | production scripts、docs | `tools/check-contracts.py`（adapter 照合） |
| release artifact・ISO 内容・mapping・metadata schema | `contracts/release-contract.json` | `scripts/build.sh` / `verify-iso.sh` / `clean.sh` | checker + `tests/contracts/` + `verify-stale.bats` |
| route 決定ロジック | `sushida_os/runtime/routes.py`（`decide()`） | launcher / network watcher、`docs/runtime-routes.md` | `test_route_decision.py` + `DRIFT_ROUTE` |
| kiosk 再起動の検証連鎖 | `/usr/local/libexec/sushida-kiosk-signal`（shell）+ `sushida_os/runtime/kiosk_signal.py`（Python 双子） | 両 watcher | `kiosk-signal.bats` + `test_navigation_watch.py` |
| runtime state protocol (schema 1) | `sushida_os/runtime/runtime_state.py` | launcher（発行）・network watcher（読取/解除）、`docs/architecture.md` | `test_runtime_state.py` + checker `DRIFT_PATH` |
| Wi-Fi backend の挙動 | `sushida_os/wifi/*`（実装）+ `tests/static/test_wifi_setup_backend.py`（characterization、66件） | `docs/wifi-state-machine.md`、`docs/networking.md` | characterization test |
| Chromium navigation 境界 | `etc/chromium/policies/managed/sushida-os.json` + `sushida-navigation-watch` の `classify_url` | `docs/architecture.md` | checker（allow/blocklist）+ `test_navigation_watch.py` |
| repository 構成一覧 | `git ls-files`（生成: `tools/gen-structure.py`） | `STRUCTURE.txt`（生成物） | `make check-structure`（CI） |
| 開発・検証の入口 | `Makefile`（`make help`） | `README.md`、docs | `test_development_tooling.py` / `test_documentation.py` |
| 進捗・作業手順・逸脱記録 | `docs/refactoring-work-order.md`（Stage A〜F、確定）+ `docs/refactoring-work-order-2.md`（Stage G、実行正本） | — | —（人手） |
| 残タスク backlog | `TASKS.md`（task record 形式） | work order §7 | `test_documentation.py`（DONE の証拠列） |
| 受け入れ試験の証拠 | `docs/acceptance-tests.md`（registry） | Definition of Done | `test_documentation.py` |
| エージェント安全境界 | `AGENTS.md` | 全作業 | `test_documentation.py`（一部文言） |
| ビルド再現性の分類 | `docs/reproducible-builds.md` | `scripts/build.sh` の制御コメント | `test_artifact_pipeline.py`（制御行の存在） |
| 脅威モデル・物理対策 | `docs/threat-model.md` | installation/maintenance | `test_documentation.py` |
| contract 項目の棚卸し | `docs/contract-inventory.md` | checker 実装の背景説明 | —（人手、Stage 完了時に更新） |

## 書いてはいけない場所

- **docs に値を直書きしない**: URL・port・timeout・パスは contract か実装が正本。
  文書は「どの contract 項目か」を指す。
- **STRUCTURE.txt を手編集しない**: `tools/gen-structure.py` の生成物（header に明記）。
- **TASKS.md の DONE に証拠なしで昇格しない**: commit（と実機系は ISO SHA）が必要。
