# Sushi-da OS 完全リファクタリング作業書（第2版）

- 初版作成日: 2026-07-20（基準 HEAD `2f72ac0`）
- 第2版再編日: 2026-07-21（基準 HEAD `b2bd238`、Stage A〜D 完了時点）
- 対象リポジトリ: `Kohe-M/sushida-os-starter`（branch: `main`）
- 本文書の位置づけ: **実行と進捗記録の唯一の正本**。コーディング担当エージェントは
  この文書の手順どおりに 1 タスクずつ実施する。
- **注意**: 初版が参照していた上位計画書
  `docs/sushida-os-development-hardening-phases-1-6.md` は本リポジトリに存在しない。
  初版で「上位計画書 §N」とされていた内容のうち実行に必要なものは本書へ取り込み済みであり、
  以後は本書のみを参照する。
- 完了済み Stage A〜D の詳細タスクカード（手順・コード断片）は本版で削除した。
  必要なら git 履歴（`b2bd238` 以前の本ファイル）を参照すること。

---

# 0. 現在地

## 0.1 Stage 一覧と状態

| Stage | 内容 | 状態 | commit 範囲 |
|---|---|---|---|
| **A** | contract checker 完成（レビュー BLOCKER 解消） | ✅ 完了 | `48af5fa`〜`c6749d9`（レビュー修正 `1a85fb3`） |
| **B** | Phase 1 残余確認（doctor 行動テスト補完） | ✅ 完了 | `a8850b4`〜`9f4210d` |
| **C** | Wi-Fi backend モジュール分割（挙動不変） | ✅ 完了 | `e825678`〜`2c096ef` |
| **D** | route 判定・kiosk signal 共通化（挙動不変） | ✅ 完了 | `04f3f64`〜`b2bd238` |
| **E** | release manifest 正本化・ISO 照合・再現性 | ⬜ 未着手 | — |
| **F** | 文書正本化（AGENTS/TASKS/STRUCTURE/docs） | ⬜ 未着手 | — |

**並行禁止**: D↔E は checker の同じ adapter・contract に触るため直列に実施する。
E↔F も E の成果物（reproducible-builds.md 等）を F が参照するため直列とする。

## 0.2 現在のテスト・検証基盤（2026-07-21 時点）

| 検証 | 規模 | 状態 |
|---|---|---|
| `tests/static/`（pytest） | 658 件 | 緑 |
| `tests/contracts/`（pytest） | 110 件 | 緑 |
| `tests/shell/`（bats、コンテナ内） | 188 件 | 緑 |
| `python3 tools/check-contracts.py` | runtime/release/drift | exit 0 |
| `make iso` / `make verify` / QEMU 系 | — | **未実行**（全 Stage 通して） |
| 実機回帰 | — | **未実行** |

## 0.3 残作業の全体像

1. **Stage E**（§5）: release contract を artifact manifest の正本にし、
   `verify-iso.sh` を manifest 駆動へ。再現可能ビルドの調査と安全な範囲の実装。
2. **Stage F**（§6）: 文書の正本化と drift 検出の CI 化。
3. **繰延 backlog**（§7）: Stage C/D の逸脱から生まれた宿題（runtime-state 完全移行など）と、
   初版でスコープ外とされた独立タスク。Stage F の TASKS.md 再編（F-03）で task record 化する。
4. **未実行検証の消化**: ISO ビルド・QEMU・実機回帰は環境が用意でき次第、
   §8 の Definition of Done 表に沿って実施する。

---

# 1. 環境と制約（全タスク共通・必読）

## 1.1 実行環境の現況

- 作業は WSL (Ubuntu) 内のリポジトリ `~/code/sushida-os-starter` で行う。
  Windows 側パス（`\\wsl.localhost\...`）から git 操作・ファイル編集をしない。
- `.venv`（pytest 入り）構築済み。podman あり（docker なし）。
  bats / shellcheck はホストになく、コンテナ経由（`make container-shell`）で実行する。
- 検証コマンド対応表:

| 目的 | ホスト venv | podman コンテナ |
|---|---|---|
| 静的テスト | `.venv/bin/python -m pytest tests/static/ -q` | `make container-test CONTAINER_ENGINE=podman` |
| contract テスト | `.venv/bin/python -m pytest tests/contracts/ -q` | 同上（`make test` に含まれる） |
| checker | `python3 tools/check-contracts.py`（pytest 不要） | 同上 |
| shell テスト | 不可 | `make container-shell CONTAINER_ENGINE=podman` |
| CI 相当 | 上記の合成 + `git diff --check` | コンテナ内で `make ci` |

- QEMU 系（`make test-qemu*`）は KVM がある環境でのみ。ISO ビルドは container-iso 経由のみ。
  実行できない場合は**「未実行」と正直に報告**し、PASS と書かない。

## 1.2 git 運用（Stage C/D で確立した現行運用）

- 実装エージェントは **1 タスク = 1 commit** を原則とし、タスクカードの推奨 commit message を
  使って自分で commit する（Co-Authored-By trailer 付き）。
- 禁止: `push / merge / rebase / reset / stash / clean / restore`、既存履歴の改変（amend 含む）。
  push はユーザーが行う。
- 作業ツリーが clean でない状態で開始した場合は、差分の由来を特定してから
  （中断タスクの続きか、無関係な残骸か）進める。由来不明なら停止して報告。

## 1.3 禁止操作・挙動境界

- flash / 実デバイス書き込み、`dd`/mkfs/パーティション操作、ホスト設定変更、
  秘密情報の取得・表示・ログ出力、Sushi-da コンテンツのコピー/スクレイプ/注入は禁止。
- production runtime（`live-build/config/includes.chroot/**`、hooks、units、policy）の
  挙動変更は行わない。Stage E で触ってよいのは `scripts/`・`contracts/`・`tools/`・
  `tests/`・`docs/` と、E-03 に伴う checker 追随のみ。
  （Stage C/D の「挙動不変の分割・共通化」許可は終了した。）
- contract の**値**を変えないと整合しない事態になったら停止して報告
  （値の変更は仕様変更でありリファクタリングではない）。

---

# 2. 全タスク共通手順

## 2.1 開始ゲート（各タスクの最初に必ず実行）

```bash
cd ~/code/sushida-os-starter
git rev-parse HEAD && git branch --show-current
git status --short
git log --oneline -5
```

開始条件: 対象リポジトリである / detached でない / 前タスクの commit がある /
変更範囲を説明できる。

## 2.2 実施原則（Stage C/D の教訓の一般化。E/F でもこれに従う）

Stage C/D の実施で、初版の手順と既存テスト・checker の間に構造的な矛盾が複数見つかった。
その解消方法を原則化する。**個別タスクカードの字面とこの原則が衝突したら原則を優先し、
逸脱として Stage 記録に残す。**

- **P1: 全 commit を単独で緑に保つ。** checker adapter・contract テスト fixture の追随は
  「後でまとめて」ではなく、配置を変えたその commit に同伴させる
  （初版 C-08 の「checker は最後に追随」は実行不能だったため、この方式に改めた実績あり）。
- **P2: 挙動テストの不変が「挙動不変」の証明。** characterization test・bats の
  **挙動検証部は 1 行も変えない**。ソース文字列のパターン検査（grep 型テスト）だけは
  コードの移動先を検査するよう追随してよい。テスト loader の構造追随
  （sys.path 追加、転送プロキシ等）も可。どちらも逸脱として記録する。
- **P3: 新規 production ファイルは同じ commit で登録を完結させる。**
  `contracts/release-contract.json`（source_image_mappings + required_iso_paths）、
  `090-validate-image.hook.chroot`（存在・mode・import 検証）、
  `tests/contracts/test_check_contracts.py` の fixture stub、の3点セット。
- **P4: on-disk protocol の変更は dual-write で導入する。** 旧ファイルを正本のまま維持し、
  新 protocol を追加発行する。読み手の切替（正本交代）は独立した backlog タスクにする
  （runtime-state.json が現在この状態。§7 参照）。
- **P5: 秘密情報・URL 全文をログ・state・エラーメッセージに入れない。**
  新規の enum/reason 系フィールドは固定トークン集合に制限する。

## 2.3 実装の進め方

1. タスクカードの「先に読むファイル」を実際に読んでから手を付ける。
2. 変更はタスクカードの「変更可能ファイル」+ P1/P3 の追随ファイルに限定する。
3. テストは実装と同じタスクで追加・更新する（後回し禁止）。
4. 1 タスク終わるごとに §2.4 の検証を実行し、緑を確認してから commit する。
5. 無関係なリファクタリングを混ぜない。

## 2.4 タスク完了時の検証（毎回）

```bash
cd ~/code/sushida-os-starter
python3 tools/check-contracts.py; echo "exit=$?"
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
git diff --check
```

shell スクリプトを触った場合はコンテナで bats も回す:
`make container-shell CONTAINER_ENGINE=podman`。
タスクカードに追加の検証があればそれも実行する。

## 2.5 完了報告フォーマット（各タスクで提出）

```text
1. 変更概要
2. 変更ファイル
3. 維持した既存契約
4. 追加・変更したテスト
5. 実行コマンドと終了コード（実際に実行したものだけ）
6. 未実行項目（環境制約など、理由つき）
7. 残存リスク
```

**未実行の検証を PASS と書かない。** 失敗したまま次のタスクへ進まない。

## 2.6 停止条件（これに当たったら作業を止めて報告）

- 想定外のファイル差分が出た / テストが原因不明に赤い
- production 挙動を変えないと解決できないことが判明した
- contract 値そのものを変えないと整合しないことが判明した
- 秘密情報らしきものを見つけた

---

# 3. checker メンテナンス依存（Stage 間）【最重要】

checker adapter は**現行のファイル配置**を読む。配置を変える Stage は同じ commit で
adapter を追随させる（P1）。

| Stage の変更 | checker/contract への影響 | 状態 |
|---|---|---|
| C: Wi-Fi 定数が `sushida_os/wifi/*.py` へ移動 | timeout/URL/path adapter の参照先 | ✅ 済み（source key `wifi_nmcli`/`wifi_storage`/`wifi_restore`/`wifi_web` へ分割） |
| D: route 判定が `sushida_os/runtime/routes.py` へ移動 | `_drift_routes` の照合 | ✅ 済み（launcher リテラル + netwatch case + routes.py `ROUTE_*` 定数の3者照合） |
| E: verify-iso.sh が manifest 駆動化 | `DRIFT_ISO_PATH` の「verify-iso.sh にパス文字列がある」検査が壊れる | ⬜ E-03 で「verify-iso.sh が release contract を読む」方式へ変更 |

---

# 4. 完了 Stage の記録（アーカイブ）

詳細タスクカードは git 履歴（`b2bd238` 以前の本ファイル）を参照。
ここには状態・逸脱・ゲート結果のみ残す。

## 4.1 Stage A: contract checker 完成 — ✅

**目的**: レビュー指摘 BLOCKER 1〜4 + MEDIUM の解消、P2-07 ゲート通過。

| Step | 内容 | 状態 |
|---|---|---|
| A-00〜A-07 | runtime/release adapters、fixture 更新、negative fixtures、strict-markers 一元化、inventory 追記 | ✅ `48af5fa`（レビュー修正 `1a85fb3`、LOW 修正: timeout 数を 14 に訂正） |
| A-08/A-09 | Stage A 検証 + P2-07 ゲート | ✅ `c6749d9`（全検証 PASS） |

## 4.2 Stage B: Phase 1 残余確認 — ✅

**目的**: doctor 行動テストの穴埋め、P1-04 ゲート再確認。

| Step | 内容 | 状態 |
|---|---|---|
| B-01 | doctor 行動テストのギャップ確認と追加 | ✅ `a8850b4`（5件追加、当時 168/168 pass） |
| B-02 | Phase 1 ゲート再確認 | ✅ 全検証 PASS、production 差分なし、CI は `make ci` |

## 4.3 Stage C: Wi-Fi backend モジュール分割 — ✅

**目的**: `sushida-wifi-setup`（1310 行）を `sushida_os.wifi` package
（types / storage / nmcli / coordinator / restore / web）へ挙動不変で分割し、
entrypoint を配線のみの薄い wrapper（103 行）にする。
**安全網**: characterization test（`tests/static/test_wifi_setup_backend.py`、66 件）が
全工程で**本体無変更のまま** pass。

| Step | 内容 | 状態 |
|---|---|---|
| C-00 | 分割前の基準線確認 | ✅ 66/66 pass + checker exit 0 を記録（`9f4210d` 時点） |
| C-01 | types.py 抽出 | ✅ `e825678` |
| C-02 | nmcli.py 抽出 | ✅ `716ac14` |
| C-03 | storage.py 抽出 | ✅ `68538cd` |
| C-04 | coordinator.py 抽出（class 封じ込め + adapter 注入 + `start_after_response()`） | ✅ `976e641` |
| C-05 | restore.py 抽出（clock/sleeper 注入可能） | ✅ `5f7f74d` |
| C-06 | web.py 抽出（HTML/HTTP status/CSP hash 不変） | ✅ `2e6a148` |
| C-07 | entrypoint 薄型化（103 行） | ✅ `05a37be` |
| C-08 | package の contract/hook 登録 | ✅ `2203eb4` |
| C-09 | Phase 3 統合ゲート | ✅ 済み |

**逸脱（→ §2.2 の原則に一般化済み）**:
1. checker/fixture 追随は C-08 一括ではなく各分割 commit に同伴（→ P1）。
2. `tests/static/test_wifi_setup.py`（パターン検査）は entrypoint + package 全体を
   走査する `_backend_text()` に切替（→ P2）。
3. characterization test は loader のみ変更: dist-packages の sys.path 追加、
   sushida_os のテスト毎 purge、`monkeypatch.setattr(backend, ...)` を定義元 module へ
   鏡映する `_BackendModule` 転送プロキシ。テスト本体は 1 行も変更なし（→ P2）。
4. C-01 の「dataclass/enum 化」は行わず、状態文字列の byte 互換を優先して
   plain 定数のまま移動した。

**C-09 結果（2026-07-21）**: pytest static/contracts 全 pass、コンテナ `make test` 全 pass、
checker exit 0、`git diff --check` クリーン。`make iso` / `make verify` **未実行**。
実機回帰6項目（設定ページ表示、接続成功、寿司打遷移、restore 中 interactive、
再起動後 restore、password 非露出）**未実行**。
補足: `tests/static/fixtures/snss/*.bin` の working-tree mode 0600 を 0644 へ修正
（container 内の別 UID から読めなかった既存問題。git 追跡外）。

## 4.4 Stage D: route 判定・kiosk signal 共通化 — ✅

**目的**: 3スクリプトに分散した route 判定と kiosk 再起動処理を
`sushida_os.runtime`（routes / runtime_state / kiosk_signal）と
`/usr/local/libexec/sushida-kiosk-signal` に挙動不変で共通化。

| Step | 内容 | 状態 |
|---|---|---|
| D-01 | route 状態モデル（routes.py + 行列テスト） | ✅ `04f3f64` |
| D-02 | runtime state protocol（runtime-state.json schema 1） | ✅ `d143102` |
| D-03 | safe signal helper（bash + bats 19件） | ✅ `0d2de99` |
| D-04 | network watcher の route model 移行 | ✅ `cbda54a` |
| D-05 | navigation watcher の signal 委譲 | ✅ `64875f4` |
| D-06 | launcher の route 出力統合 | ✅ `3fe79ab` |
| D-07 | route integration test | ✅ `02f989d` |
| D-08 | Phase 4 ゲート | ✅ 済み |

**逸脱**:
1. P4-07 の表の出典（上位計画書）が存在しないため、route 行列は現行3スクリプトの
   実挙動から導出（`tests/static/test_route_decision.py` の ROUTE_MATRIX）。
2. signal helper は **bash** 実装。network-watch.bats の fail-closed テストが
   PATH shim（偽 `stat`/`systemctl`）前提のため、Python では挙動テストを無変更で通せない。
3. navigation watcher は subprocess 委譲ではなく、同一検証の Python 双子
   `sushida_os/runtime/kiosk_signal.py` へ **in-process 委譲**
   （`monkeypatch.setattr(os, "geteuid")` を使う既存テストの制約）。
   `test_navigation_watch.py` は 1 行も変更せず 74 件 pass。
4. active-route / time-sync marker の state protocol への移行は **dual-write** に留めた
   （→ P4。完全移行は §7 backlog）。
5. ソースパターン検査 4 件（network-watch.bats 1、test_networking.py 2、
   test_wifi_setup.py 1）を移動先（helper / routes model）検査へ追随（→ P2）。

**D-08 結果（2026-07-21）**: コンテナ `make test`（static 658 + contracts 110 + bats 188）
全 pass、checker exit 0、`git diff --check` クリーン。
`make iso` / `make verify` / `make test-qemu-runtime` **未実行**。
実機確認7項目（offline 起動、setup 起動、Wi-Fi 接続、接続中 setup 維持、time sync 待機、
prohibited navigation 復帰、unnecessary restart なし）**未実行**。

---

# 5. Stage E: release manifest・ISO 完全照合・再現可能ビルド

**目的**: release ISO が source tree と一致することを manifest から一貫して証明する。
**変更可能ファイル**: `contracts/release-contract.json`、`contracts/schema/`、
`scripts/verify-iso.sh`、`scripts/build.sh`、`scripts/clean.sh`、`tools/`、
`tests/contracts/`、`tests/static/`、`tests/shell/`、`docs/`。
**checker と verify が release contract を正本として読む構造への変更はこの Stage の本題である。**

**前提（Stage C/D の成果として既に済んでいること）**:
- `sushida_os/**` 全 module と `sushida-kiosk-signal` は source_image_mappings +
  required_iso_paths + validate hook に登録済み（squashfs 領域、
  `current_verification: "presence"`）。
- fixture `_build_minimal_repo` は全 mapping source の stub を持ち、mode 同期済み。
- image は source-only Python（.pyc なし）方針で hook が検証する。

## E-00: 基準線確認（前提確認タスク）

**手順**:
1. `.venv/bin/python -m pytest tests/static/ tests/contracts/ -q` が緑、
   `python3 tools/check-contracts.py` が exit 0 であることを記録する。
   赤い場合は Stage E を開始せず停止して報告。
2. `contracts/release-contract.json` の現在の mapping 数・required_iso_paths 数を記録する
   （E-01 以降の増分を追跡可能にする）。
3. `scripts/verify-iso.sh` と `scripts/build.sh` を通読し、手書き artifact 名・
   パス一覧の所在をメモする（E-03/E-05 の対象範囲）。

**受け入れ条件**: 緑の基準線と対象範囲メモが記録されている。

## E-01: release manifest 正本化（P5-01）

**手順**:
1. `contracts/release-contract.json` に bootloader 領域の mapping を追加する
   （inventory の SIM-20〜22: grub.cfg 系・isolinux 系。region は `"iso-root"`、
   comparison は `"presence"`、`current_verification: "none"` から始める）。
   builder イメージ（SIM-19）は ISO 内容ではないので manifest には入れない
   （schema の region enum を広げない方針）。
2. `required_iso_paths` に `boot/grub/grub.cfg` 等を追加し、iso-root 検査
   （`DRIFT_ISO_PATH`）が通るよう verify-iso.sh 側の参照も確認する。
3. fixture に新 mapping の source ファイル stub を追加する（P1/P3: 同一 commit）。
4. manifest に存在しない critical file を検出できること、symlink 置換を検出できることを
   fixture テストで証明する。

**推奨 commit**: `feat(release): make release contract the artifact manifest`

## E-02: ISO 抽出 adapter 整理（P5-02）

**手順**: xorriso 抽出・unsquashfs 抽出・symlink 解決・mode/owner 取得・一時 dir cleanup を
`scripts/` か `tools/` の共通 helper に集約。cleanup trap 先頭設定、path traversal 拒否、
symlinked source 拒否、temporary root 外を削除しない、をテストで検証（bats または pytest）。

**推奨 commit**: `refactor(release): centralize safe ISO extraction helpers`

## E-03: `verify-iso.sh` manifest 駆動化（P5-03 + §3）

**手順**:
1. 手書きの required path・個別 `cmp` を release contract の loop に置き換える
   （existence/regular file/symlink 拒否/non-empty/exact content/mode/owner/group/
   package presence/service enable/policy/polkit/NM config/bootloader/local pages）。
2. **checker 追随（同一 commit）**: `DRIFT_ISO_PATH` の「iso-root パス文字列が
   verify-iso.sh にある」検査を、「verify-iso.sh が release contract を読む実装になっている」
   （例: `release-contract.json` への参照がある）＋ contract 内 iso-root 定義の自己整合に変更する。
3. contract テスト fixture も追随（同一 commit）。
4. 静的テストに verify-iso.sh のパターン検査があれば P2 に従い追随し、逸脱として記録する。

**推奨 commit**: `refactor(release): verify critical image files from manifest`

## E-04: artifact metadata schema（P5-04）

**手順**: `build-info.json` / `SHA256SUMS` / `package-manifest.txt` に schema version、
git commit、git dirty、build timestamp、architecture、package versions、ISO SHA、
release contract version、manifest hash を持たせ、`build-info.json.iso_sha256` ↔ 実 ISO SHA ↔
`SHA256SUMS` ↔ filename ↔ clean HEAD ↔ release contract hash を相互照合する検証を追加。

**推奨 commit**: `feat(release): version and validate artifact metadata schema`

## E-05: build/publish/clean の artifact 一覧統合（P5-05）

**手順**: publish/clean/checksum/verify/QEMU 対象の一覧を release contract から取得するよう
`scripts/build.sh`・`scripts/clean.sh` を変更。同じ artifact 名を複数 script に直書きしない。
contract 外の artifact を誤 publish しない。clean が repository 外を削除しない。
checker の `RELEASE_ARTIFACT*` / `RELEASE_CHECKSUM` / `RELEASE_PUBLISH` adapter が
build.sh の文字列を照合しているため、実装方式変更時は同一 commit で追随する（P1）。

**推奨 commit**: `refactor(release): share artifact inventory across build and cleanup`

## E-06: stale fixture test（P5-06）

**fixture**: policy 1バイト古い、navigation watcher 欠落、unit 古い、bootloader config 古い、
mode 変更、symlink 置換、package 欠落、build-info SHA 不一致、manifest hash 不一致。
**全てを `verify` が拒否する**ことをテストで証明する。

**推奨 commit**: `test(release): reject stale and tampered ISO fixtures`

## E-07: 再現可能ビルド調査（P5-07）

**成果物**: `docs/reproducible-builds.md`。`SOURCE_DATE_EPOCH`、locale、timezone、file ordering、
umask、SquashFS/ISO timestamp、mirror 更新、version pinning、live-build 生成時刻を
`deterministic / controlled / external-variable / currently-uncontrolled` に分類。
**このタスクだけで bit-for-bit 再現を約束しない。**

**推奨 commit**: `docs(build): analyze reproducibility inputs and remaining variance`

## E-08: 再現性の安全な範囲を実装（P5-08）

**候補**: clean HEAD の commit timestamp を `SOURCE_DATE_EPOCH` に、locale/timezone 固定、
file order 固定、umask 固定、metadata の stable serialization、build timestamp と source epoch の区別。
**要件**: package 更新を隠さない。古い脆弱 package へ固定しない。トレードオフを文書化する。

**推奨 commit**: `build(release): control deterministic build inputs`

## E-09: Phase 5 ゲート（P5-09）

```bash
make container-test CONTAINER_ENGINE=podman
python3 tools/check-contracts.py
# container 内で: make ci
git diff --check
```

可能なら `make configure && make iso && make verify && make test-qemu-boot &&
make test-qemu-runtime && make test-qemu-powerdown`（未実行なら明記）。
E-03 以降は **ISO なしで検証できる範囲**（fixture テスト・checker・bats）と
**ISO が必要な範囲**（実 verify 実行）を分けて報告する。

**完了条件**: security-critical file が完全照合される。stale ISO を拒否する。
artifact metadata が相互整合する。release contract が正本。再現可能性の保証範囲が明文化される。
Stage 完了時に §4 と同形式の記録（状態表・逸脱・ゲート結果）を本書に追記する。

---

# 6. Stage F: 文書正本化

**目的**: コード変更と同時に文書が古くなる問題を防ぎ、エージェント・人間・CI が同じ正本を
参照する構造へ整理する。**変更可能ファイル**: `docs/**`、`AGENTS.md`、`TASKS.md`、
`STRUCTURE.txt`、`README.md`、`.github/`、`Makefile`、`tools/`（生成 script）、
`tests/static/`（文書整合テスト）。

## F-01: 文書正本マップ（P6-01）

**新規**: `docs/documentation-map.md`。「情報 → 正本 → 参照先」の表を現行ファイル名で作成。
少なくとも次を含める: contract 値（runtime/release contract が正本）、route 決定
（`sushida_os/runtime/routes.py` が正本）、Wi-Fi backend 構成（`sushida_os/wifi/` が正本）、
進捗・作業手順（本書が正本）、受け入れ試験（acceptance-tests.md が正本）。

**推奨 commit**: `docs: define documentation sources of truth`

## F-02: `AGENTS.md` 再構成（P6-02）

構成: 1. Safety invariants / 2. Allowed operations / 3. Prohibited operations /
4. Runtime contracts / 5. Test requirements / 6. Artifact requirements /
7. Final report format / 8. Stop conditions。長い実装説明を置かない。
変更してはいけない境界を中心にする。contract と Make target を参照する。
古い file 一覧を手書きで持たない。§1.2 の git 運用（agent が commit、push はユーザー）と
§2.2 の実施原則 P1〜P5 を反映する。

**推奨 commit**: `docs(agent): restructure repository safety instructions`

## F-03: `TASKS.md` を管理可能な backlog へ（P6-03）

現行 TASKS.md は実装タスク 1〜20 の旧形式。次の schema の task record へ変換する:
`ID / Status / Severity / Dependency / Scope / Acceptance criteria / Verification /
Manual checks / Out of scope`。status は `BACKLOG/READY/IN_PROGRESS/BLOCKED/REVIEW/DONE/DEFERRED`。
**実装済みと未実装を分離**し、「設計済み」を「完了」と扱わない。実機未確認を明示。
DONE には commit、ISO SHA、確認日を記録できる欄を設ける。
**§7 の繰延 backlog をこの schema で task record 化して取り込む。**

**推奨 commit**: `docs(tasks): convert backlog to explicit task records`

## F-04: `STRUCTURE.txt` の自動生成・検査（P6-04）

**現状**: 現行 STRUCTURE.txt は `contracts/`、`tools/`、`tests/contracts/`、
`sushida_os/` package、新規 hooks、Wi-Fi/navigation 系ファイルが掲載されていない。

**手順**:
1. `git ls-files` から決定的に生成する `tools/gen-structure.py`（新規）を作る。
   除外規則を明示（`build/`、`artifacts/`、`local/`、`__pycache__`、`.venv` 等）。
2. 生成順序を固定（ソート）、build artifact と secret/ignored file を含めない、
   手編集禁止 header を付ける。
3. `make check-structure` を Makefile に追加（生成物と現行の diff で stale なら非ゼロ）。
4. CI（`make ci`）に組み込む。

**推奨 commit**: `feat(docs): generate and verify repository structure index`

## F-05: README の最小化（P6-05）

現行 README は既に最小化に近い。差分確認のみ: プロジェクト目的・セキュリティ注意・
最短開発手順・最短 build 手順・最短 flash 案内・文書リンクが揃っているか確認し、
不足があれば `docs/` へのリンクで補う（README に詳細を新規執筆しない）。

**推奨 commit**: `docs(readme): reduce top-level guide to stable entrypoints`

## F-06: domain 別文書整理（P6-06）

対象: `docs/architecture.md`、`docs/build.md`、`docs/networking.md`、
`docs/wifi-state-machine.md`（新規）、`docs/runtime-routes.md`（新規）、
`docs/release-verification.md`、`docs/threat-model.md`、`docs/acceptance-tests.md`、
`docs/troubleshooting.md`、`docs/reproducible-builds.md`（E-07 成果物）。
**要件**: contract 値を手書きで重複しない（正本を参照する形にする）。diagram と実装名を一致。
Wi-Fi の pending-interactive（latest-wins）仕様、route model と時系列（launcher grace →
watcher 監視）、runtime-state.json の dual-write 状態、QEMU test の違いを説明。

**推奨 commit**: `docs: align architecture guides with runtime contracts`

## F-07: Acceptance test registry（P6-07）

現行 `docs/acceptance-tests.md` は ID 表だが commit / ISO SHA / 確認日 / 確認者 の列がない。
各項目に `対象commit / ISO SHA / 環境 / 手順 / 期待結果 / Actual result /
PASS/FAIL / 確認日 / 確認者` を持たせ、分類（automated/QEMU/manual VM/physical hardware/
destructive-manual-approval-required）を付ける。**未実施を PASS にしない。
古い ISO の結果を最新 ISO に流用しない。** §4 の C-09/D-08 で「未実行」とした
実機回帰項目をこの registry に登録する。

**推奨 commit**: `docs(test): make acceptance evidence versioned and traceable`

## F-08: 変更チェックリスト導入（P6-08）

**新規**: `.github/pull_request_template.md`、`docs/change-checklist.md`。
チェック項目: runtime/release contract 変更、service 追加、package 追加、Chromium policy 変更、
Wi-Fi state 変更、QEMU test 変更、artifact metadata 変更、docs 更新、acceptance test 更新、
secret 検査、privilege 境界、**新規 production ファイルの3点セット登録（P3）**。

**推奨 commit**: `docs(process): add change-impact and review checklist`

## F-09: 文書整合テスト（P6-09）

`tests/static/test_documentation.py`（既存）を拡張し、次を検証する:
- README に存在しない Make target がない（`make help` の一覧と突合）
- 文書中の service 名が contract と一致
- artifact 名が release contract と一致
- stale な「資格情報は破棄」記述がない
- STRUCTURE.txt が最新（F-04 の checker と統合）
- TASKS の DONE に証拠（commit/SHA）がある
- acceptance test の PASS に commit と ISO SHA がある

**推奨 commit**: `test(docs): enforce documentation and contract consistency`

## F-10: 最終 Phase ゲート（P6-10）

```bash
python3 tools/check-contracts.py
make check-structure
make container-test CONTAINER_ENGINE=podman    # make ci 相当
git diff --check
```

release 環境で可能なら: `make configure && make iso && make verify && make test-qemu &&
make test-qemu-powerdown`（未実行なら明記）。

**完了条件**:
- 開発入口が Makefile に統一されている。
- runtime/release contract が正本である。
- Wi-Fi backend がモジュール化されている（✅ Stage C）。
- route と signal 処理が共通化されている（✅ Stage D）。
- ISO critical file が完全照合される（Stage E）。
- 文書とコードのドリフトが CI で検出される。
- acceptance evidence が commit と ISO SHA に紐付く。

Stage 完了時に §4 と同形式の記録を本書に追記する。

---

# 7. 繰延 backlog（Stage E/F の後、または独立に実施）

Stage F-03 で TASKS.md の task record に変換する。それまでの正本はこの表。

| ID | 内容 | 出自 | 依存 |
|---|---|---|---|
| BL-01 | **runtime-state.json への正本切替**: watcher/launcher の読み手を state protocol へ移し、`active-route`・`time-sync-required` ファイルを廃止。bats・checker の `DRIFT_PATH`（active_route_file / time_sync_marker）・runtime contract の追随を含む。dual-write はそれまで維持 | Stage D 逸脱 4（P4） | Stage E/F と独立。ただし挙動テストの書き換えを伴うため単独 Stage 扱いで慎重に |
| BL-02 | `connection_in_progress` の実出力: Wi-Fi backend の接続中状態を runtime-state.json に反映（現在は常に false のプレースホルダ） | D-02 schema 予約 + 初版スコープ外「connection-in-progress 統合」 | BL-01 |
| BL-03 | route enum への `time-sync` 追加検討: 現在は offline + reason で表現。専用 route 化するか判断 | D-01 予約 | BL-01 |
| BL-04 | SUSHIDA-CFG ラベル衝突対策 / RTC 判定 / console=ttyS0 方針（初版で独立タスクとされた残り） | 初版 §1.2 | 独立 |
| BL-05 | ISO ビルド・QEMU・実機回帰の実施と §8 判定表の消化（C-09/D-08/E-09 の未実行項目） | 各 Stage ゲート | ビルド環境 |
| BL-06 | kiosk-signal helper の検証ロジックと Python 双子（`kiosk_signal.py`）の同一性を自動照合するテスト（現在は bats/pytest が別々に検証。実装は2箇所） | Stage D 設計判断 | 独立 |

---

# 8. 最終完了判定（Definition of Done 対応表）

全 Stage 完了後に判定する。ISO ビルド・QEMU・実機依存の項目は、実行環境がなければ
**READY_TO_PROCEED とは言わず**、`READY_TO_PROCEED_WITH_ADVISORIES` か `PARTIAL` として、
未検証項目を明確に列挙して報告する。

| # | 項目 | 検証手段 |
|---|---|---|
| 1 | `make iso` 成功 | 環境依存 |
| 2 | ISO と checksums 生成 | 環境依存 |
| 3 | QEMU が boot する | 環境依存 |
| 4 | 通常 login 画面が出ない | QEMU/実機 |
| 5 | Chromium が全画面で表示 | QEMU/実機 |
| 6 | tab と address bar がない | QEMU/実機 |
| 7 | アプリ切替不可 | QEMU/実機 |
| 8 | terminal を開けない | QEMU/実機 |
| 9 | developer tools を開けない | QEMU/実機 |
| 10 | 任意 URL 遷移がブロックされる | QEMU/実機 |
| 11 | Chromium 終了後 5 秒以内に再起動 | QEMU/実機 |
| 12 | offline mode が動く | QEMU/実機 |
| 13 | network 復帰で設定ページに戻る | QEMU/実機 |
| 14 | WebGL が意図的に無効化されていない | static + 実機 |
| 15 | audio package と設定が存在 | static |
| 16 | kiosk user に管理者権限なし | static |
| 17 | SSH server なし | static |
| 18 | root filesystem が read-only | static + QEMU |
| 19 | secret が commit されていない | static |
| 20 | `make test` 成功 | Stage A〜D で検証済み・維持 |
| 21 | build/verify/install/acceptance が文書化 | Stage F で検証 |

---

# 付録 A. production 値の所在表（contract → production、Stage C/D 反映済み）

checker adapter が現在読んでいる場所。

| contract 項目 | production 所在（現行） |
|---|---|
| `urls.sushida_url` | `config.env` の `SUSHIDA_URL=` |
| `urls.setup_url` | `sushida-launch` / `sushida-session` の `readonly SETUP_URL=`、`sushida_os/wifi/web.py` の `PORT = 8787` |
| `urls.offline_url` | `sushida-launch` / `sushida-session` の `readonly OFFLINE_URL=` |
| `runtime_paths.runtime_dir` | launch/netwatch `PROD_RUNTIME`、navwatch `PROD_RUNTIME = Path(...)`、kiosk unit `RuntimeDirectory=` |
| `runtime_paths.active_route_file` / `time_sync_marker` | launch `$BASE_RUNTIME/...`、netwatch `$RUNTIME_DIR/...`（BL-01 完了までこのまま。runtime-state.json は追加発行） |
| `runtime_paths.wifi_setup_runtime_dir` / `csrf_token_file` | `sushida_os/wifi/storage.py` `CSRF_TOKEN_FILE`、wifi unit `RuntimeDirectory=` |
| `runtime_paths.config_mount_path` | `sushida_os/wifi/storage.py` `CONFIG_MOUNT`、config-prepare `CONFIG_MOUNT`、mount unit `Where=` |
| `runtime_paths.config_storage_status` | `sushida_os/wifi/storage.py` `STORAGE_STATUS`、config-prepare `STATUS_DIR`/`STATUS_FILE` |
| `runtime_paths.credential_file` | `sushida_os/wifi/storage.py` `CONFIG_DIR` / `CONFIG_FILE` |
| `runtime_paths.chromium_profile_dir` / `chromium_sessions_dir` | launch mkdir、session `--user-data-dir`、navwatch `SESSIONS_SUBDIR` |
| `timeouts.network_*` | `config.env` |
| `timeouts.wifi_command_default` / `wifi_activation_*` | `sushida_os/wifi/nmcli.py`（activation は `"--wait", "30"` と `timeout=35` が **2サイト**） |
| `timeouts.restore_*` | `sushida_os/wifi/restore.py`（deadline は注入 clock 形 `monotonic() + 120.0` も許容） |
| `timeouts.http_*` | `sushida_os/wifi/web.py` |
| `timeouts.nav_*` | navwatch `DEFAULT_POLL_SECONDS`/`DEFAULT_COOLDOWN_SECONDS` |
| `timeouts.session_audio_timeout_seconds` | session `_raw_at=3`（デフォルト行） |
| `routes` | launch `ACTIVE_ROUTE="..."` ＋ netwatch `case "$route" in ...` ＋ `sushida_os/runtime/routes.py` `ROUTE_*` 定数（3者一致） |
| `metadata.static_values` | `scripts/build.sh` の `--arg <field> "<value>"` |

# 付録 B. エラーコード一覧（checker、実装と同期: 2026-07-21）

| コード | 意味 |
|---|---|
| `MISSING_SOURCE` | 必須 production source 不在 |
| `RUNTIME_URL_MISMATCH` / `DRIFT_URL` | URL の contract↔実装不一致 |
| `DRIFT_PATH` | runtime path 不一致 |
| `DRIFT_TIMEOUT` | timeout リテラル不一致 |
| `DRIFT_ROUTE` / `RUNTIME_UNKNOWN_ROUTE` | route 集合不一致 |
| `DRIFT_CONFIG_KEY` / `DRIFT_CONFIG_FORMAT` / `DRIFT_CONFIG_DUPLICATE` | config.env の構文・キー違反（行内容は出力しない） |
| `RUNTIME_ALLOWLIST_MISMATCH` / `RUNTIME_BLOCKLIST_MISMATCH` / `RUNTIME_ALLOWLIST_CONTENT` / `RUNTIME_BLOCKLIST_CONTENT` | policy ↔ contract 不一致 |
| `RUNTIME_SERVICE_MISSING` / `UNHANDLED_RUNTIME_FIELD` | unit 不在 / contract 未対応フィールド |
| `RELEASE_ARTIFACT` / `RELEASE_ARTIFACT_REF` / `RELEASE_ARTIFACT_REF_UNEXPECTED` / `RELEASE_ISO_NAME` | artifact 名の参照不整合 |
| `RELEASE_PACKAGE_MISSING` | package list 欠落 |
| `DRIFT_SERVICE_ENABLE` / `DRIFT_SERVICE_MASK` | hook との不整合 |
| `RELEASE_CHECKSUM` / `RELEASE_PUBLISH` | build.sh との不整合 |
| `DRIFT_METADATA_STATIC` / `DRIFT_METADATA` / `DRIFT_METADATA_FORMAT` / `DRIFT_METADATA_UNSUPPORTED` | metadata 不整合 |
| `RELEASE_MAPPING_SOURCE` / `DRIFT_MAPPING_PATH` / `DRIFT_MAPPING_MODE` / `DRIFT_MAPPING_OWNER` / `DRIFT_COMPARISON` | mapping 不整合 |
| `DRIFT_ISO_PATH` / `DRIFT_ISO_PATH_ATTR` / `DRIFT_PATH_PATTERN` | ISO path 不整合 |
| `SCHEMA_*`（TYPE/ENUM/REQUIRED/UNKNOWN/VERSION 等） | schema validation 系 |
| `FORBIDDEN_KEY` | secret らしきキー |
| `PARSE_ERROR` / `INTERNAL_ERROR` | JSON 破損 / checker 内部エラー（exit 2） |

# 付録 C. 環境構築詳細

```bash
# 1. WSL に入る（Windows 側から起動する場合）
wsl.exe -d Ubuntu

# 2. リポジトリへ
cd ~/code/sushida-os-starter

# 3. venv + pytest（構築済み。壊れた場合の再構築手順）
python3 -m venv .venv
.venv/bin/pip install pytest
git check-ignore .venv   # IGNORED であること

# 4. podman builder（全検証用。初回は時間がかかる）
make builder CONTAINER_ENGINE=podman

# 5. 動作確認
python3 tools/check-contracts.py
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make container-test CONTAINER_ENGINE=podman
```

- `make test-shell` / bats / shellcheck はコンテナ経由（`make container-shell`）でのみ実行可能。
- QEMU 系（`make test-qemu*`）は KVM がある環境でのみ実行。なければ「未実行」と報告。
- ISO ビルド（`make iso`）は `--privileged` が必要なため container-iso 経由のみ。
  実行できない環境では「未実行」と報告し、READY 判定を行わない。

---

**改訂履歴**
- 2026-07-20: 初版。`docs/phase2b2-work-order.md`（Stage A 部分）を統合し、
  実リポジトリ調査に基づく Stage B〜F を追加して一元化。
- 2026-07-21: 第2版。Stage A〜D 完了を受けて再編。完了 Stage の詳細タスクカードを
  アーカイブ化（git 履歴参照）、C/D の逸脱を実施原則 P1〜P5 として一般化、
  存在しない上位計画書への依存を解消、Stage E/F を現状前提に改訂、
  繰延 backlog（§7）を新設、付録を実装と同期。
