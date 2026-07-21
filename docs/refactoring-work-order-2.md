# Sushi-da OS リファクタリング作業書 第2弾（Stage G）

- 作成日: 2026-07-21（基準 HEAD `374bfad`、Stage A〜F + backlog BL-01〜04/06 完了後）
- 位置づけ: 次回リファクタリングの**実行正本**。進捗と逸脱の記録もここに追記する。
  第1弾（Stage A〜F）の記録は `docs/refactoring-work-order.md` に確定済み。
- 実施原則 P1〜P5（各 commit 単独緑 / 挙動テスト不変 / 新規ファイル3点セット /
  dual-write / secret 非露出）と共通手順・停止条件は
  `docs/refactoring-work-order.md` §1〜§3 をそのまま適用する。

## 0. 選定方針と全体評価

リポジトリ全体（実装 約7,500行 + テスト 約11,100行）を再走査した。
Stage C〜F の分割・manifest 化により大半のファイルは凝集しており、
**「リファクタリングの手間 < 保守性向上」が成立するのは、実際に事故が起きた
重複箇所と、ミスを繰り返した検査機構に限られる**。選定基準:

1. **事故実績**: 同種のバグを複数箇所で直した／同じミスを繰り返した箇所を最優先
2. **変更頻度**: 今後も触る見込みが高い箇所を優先（安定した完成部は触らない）
3. **検証コスト込みの手間**: QEMU 実走を伴う変更は束ねて再検証1回に抑える

| タスク | 効果 | 手間 | 判定 |
|---|---|---|---|
| G-01 QEMU 検証 helper 集約 | 高（同一バグの多重修正を根絶） | 小 | **実施** |
| G-02 run-qemu.sh の stage 関数化 | 中〜高（直近バグ3件の温床） | 中 | **実施**（G-01 と同時） |
| G-03 structure 検査の untracked 対応 | 中（繰り返したミスを機構で防止） | 極小 | **実施** |
| G-04 pytest 共通 conftest | 小〜中 | 小 | **実施**（軽量） |
| G-05 check-contracts.py の package 分割 | 中 | 中 | **DEFERRED**（条件付き） |
| §5 の見送り群 | 小 or 負 | 中〜大 | **見送り**（理由を記録） |

## 1. G-01: QEMU 検証 helper の集約【優先度: 高】

**動機（事故実績）**: `serial_without_ansi`/`serial_matches` が
`scripts/run-qemu.sh` と `tests/qemu/powerdown-test.sh` に重複し、
`boot-test.sh` は同じ sed を独自にインライン、`smoke-test.sh` も別実装を持つ。
pipefail×SIGPIPE バグ（`c9dd1ad`）は**2箇所を修正し、残り2箇所は偶然免疫**だった。
ANSI 除去正規表現は現在4形態ある。`result_value()` は smoke/powerdown に重複、
build-info↔HEAD↔ISO SHA の照合 python block は boot/powerdown に重複している。

**手順**:
1. `tests/qemu/lib.sh`（新規、source 専用）を作り、次を1実装に集約する:
   - `serial_without_ansi` / `serial_matches`（SIGPIPE 免疫版・`c9dd1ad` の
     コメントごと移設）
   - `result_value`
   - build-info↔HEAD↔ISO SHA 照合（`assert_release_binding <run_dir>` 等の名前で）
2. `run-qemu.sh`・`boot-test.sh`・`smoke-test.sh`・`powerdown-test.sh` を
   lib source に切替。**照合パターン文字列・エラーメッセージは一字も変えない**
   （bats/QEMU dry-run テストの期待と、registry 記録済み証跡の再現性を守る）。
3. 各 assessor の `set -euo pipefail` と lib の相互作用を確認（lib は関数定義のみ）。
4. lib は image に載らないため3点セット登録は不要。`STRUCTURE.txt` 再生成のみ
   （**git add 後に**生成すること。G-03 完了後なら不要）。

**検証**: 全 bats（QEMU dry-run 含む）+ 既存 ISO がある環境なら
`tests/qemu/*-test.sh <run_dir>` を registry R3/R4 の run_dir に対して再実行し
同判定を得る。ISO が無い場合は「assessor 単体の再実行は未実施」と明記。

**受け入れ条件**: ANSI 除去・result 読取・release 照合の実装が各1箇所。
既存テスト全緑。

**推奨 commit**: `refactor(qemu): consolidate serial and evidence helpers`

## 2. G-02: run-qemu.sh の stage 関数化【優先度: 中〜高】

**動機**: 473行に CLI 解析・QEMU 引数組立・4実行モード（plain / boot-test /
smoke / powerdown）・証跡収集・result 書出しが直列に混在。直近の実バグ3件
（120s 固定待機 `d0a23c1`、SIGPIPE `c9dd1ad`、既定 entry の serial 欠如の診断遅れ）
はいずれもこの構造の見通しの悪さが一因。verify-iso.sh で実績のある
「stage 関数 + main、source 時は定義のみ」型に揃える。

**手順**:
1. `parse_args` / `build_qemu_args` / `run_bounded` / `wait_boot_evidence` /
   `wait_smoke_marker` / `run_powerdown` / `write_result` 程度の関数に再編。
   実行時の挙動・ログ・result.env の書式・失敗メッセージは**不変**。
2. QEMU dry-run 系 bats（`dev-tools.bats`/QEMU 系）のソースパターン検査が
   あれば P2 に従い追随し、逸脱として記録する。挙動検証部は変更しない。
3. G-01 の lib を利用する形で実装する（同一 commit 群・同一再検証で済ませる）。

**検証**: G-01 と合わせて1回の QEMU 実走（TCG で boot-test のみで可、約15分）
+ dry-run bats 全緑。実走できない環境では dry-run のみで「実走未実施」と明記。

**受け入れ条件**: main が実行順序の列挙だけになる。source しても副作用がない。
既存の `--dry-run` 出力が byte 一致（これを新テストで固定してよい）。

**推奨 commit**: `refactor(qemu): restructure runner into staged functions`

## 3. G-03: structure 検査を未 add ファイルにも効かせる【優先度: 高・手間: 極小】

**動機（ミス実績）**: `gen-structure.py --check` は `git ls-files`（index）だけを
見るため、「新規ファイル作成 → テスト実行（緑）→ add → commit → 次の commit で
stale 発覚」を**2回**繰り返した（`09b2698`、`14efdcf`）。検査が「commit 後の姿」を
事前に見られないのが原因。

**手順**:
1. `tools/gen-structure.py` の対象を
   `git ls-files --cached --others --exclude-standard` に変更
   （tracked + untracked(未 ignore) = commit 後の姿）。生成・検査の両方に適用。
2. `tests/static/test_documentation.py::test_structure_index_is_fresh` は
   そのまま（挙動が正しくなるだけ）。untracked を含むことのテストを1件追加:
   一時ファイルを repo 直下に作らず、`--check` の対象リスト関数を直接
   unit test する（repo を汚さないこと）。
3. `STRUCTURE.txt` を再生成。

**受け入れ条件**: 新規ファイルを作った時点（add 前）で `--check` が stale を報告する。

**推奨 commit**: `fix(docs): structure freshness check sees untracked files`

## 4. G-04: pytest 共通 conftest【優先度: 低〜中・手間: 小】

**動機**: `sys.dont_write_bytecode = True` + dist-packages の `sys.path` 挿入
ブロックが 5 ファイル（route_decision / runtime_state / kiosk_signal_equivalence /
connection_marker / wifi_setup_backend）に重複しており、新テスト作成のたびに
コピーされ続ける。

**手順**:
1. `tests/static/conftest.py`（新規）に sys.path 挿入と
   `sys.dont_write_bytecode = True` を移す。
2. 各テストの重複ブロックを削除。**`test_wifi_setup_backend.py` は
   characterization のため触らない**（残しても二重挿入は無害）。
3. import 順序に依存するテストがないことを全 suite で確認。

**受け入れ条件**: 新規テストが boilerplate なしで `sushida_os` を import できる。
全テスト緑。

**推奨 commit**: `test: centralize package path setup in conftest`

## 5. G-05: check-contracts.py の package 分割【DEFERRED（条件付き）】

1,201 行だが、内部は節構造（Reporting / Schema / Runtime drift / Release drift /
Secret / Main）で、最大関数 179 行、112 件の fixture テストが挙動を固定している。
**現時点では分割コスト（fixture 追随・レビュー負荷）が navigability 向上を上回る**。

**着手条件**: 次に checker へ大きな機能追加（例: 新 contract 種別、adapter の
大幅増）を行う Stage が発生した時、その前座タスクとして
`tools/check_contracts/`（`schema.py` / `runtime_drift.py` / `release_drift.py` /
`report.py` + 互換 entrypoint スクリプト）へ分割する。entrypoint のパス
（`python3 tools/check-contracts.py`）は fixture が subprocess で叩くため必ず維持。

## 6. 検討して見送った候補（再提案時の参考）

| 候補 | 見送り理由 |
|---|---|
| launch/netwatch の config.env parser 共通化（20行がほぼ同一） | 差分は許可 key のみ。2年安定・contract/checker/bats が現形を固定しており、source 共有 lib 化の追随コストが利得を上回る。3スクリプト目の parser が必要になったら再検討 |
| kiosk-signal の shell/Python 双子の単一実装化 | 双子は設計判断（PATH shim テスト互換 × in-process monkeypatch 互換）。BL-06 の11シナリオ同一性テストが乖離を自動検出するため、統一の利得が薄い |
| release-contract.json の mapping 短縮・生成化 | source=includes.chroot+image_path の「冗長」は checker が強制する明示宣言であり、行単位 diff がレビュー資産。生成化は正本の所在を曖昧にする |
| web.py の HTML template 分離 | CSP exact hash・characterization test と密結合。触るリスク > 可読性利得 |
| navigation-watch の SNSS parser 分離 | 凝集済み・実 capture fixture でテスト厚い。移動は P2 追随コストのみ発生 |
| fixture 構築の共有（test_check_contracts / verify-stale.bats / artifacts.bats） | 各 fixture は目的が異なり（checker 用 stub / 実 ISO / コピー実行）、共有すると個別の意図が読めなくなる |
| wifi/nmcli.py（475行）の再分割 | Stage C の分割単位（NM 操作の adapter）として凝集。コマンド列不変の制約下で分割益なし |

## 7. 実施ゲート（Stage G 完了条件）

```bash
python3 tools/check-contracts.py
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make check-structure
make container-shell CONTAINER_ENGINE=podman
git diff --check
```

- G-01/G-02 は可能なら QEMU boot-test 実走1回（TCG 可）。不可なら未実施と明記。
- 完了時に本書へ §形式（状態表・逸脱・ゲート結果）で記録を追記し、
  `docs/refactoring-work-order.md` 側は触らない。
