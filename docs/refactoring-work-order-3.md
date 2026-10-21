# Sushi-da OS リファクタリング作業書 第3弾（Stage H）

- 作成日: 2026-10-22（基準 HEAD `0dbc9c5`、Stage G + FB-01〜06 完了後）
- 位置づけ: Stage H の**実行正本**。進捗と逸脱の記録もここに追記する。
  第1弾・第2弾の記録は `docs/refactoring-work-order.md` /
  `docs/refactoring-work-order-2.md` に確定済み（本書からは触らない）。
- 実施原則 P1〜P5・共通手順・停止条件は `docs/refactoring-work-order.md`
  §1〜§3 をそのまま適用する。
- 発注: ユーザー依頼（2026-10-22「まずリファクタリングしてほしい」）。

## 0. 選定方針と全体評価

Stage G 以降に入ったコードは実機フィードバック対応（FB-01〜06）で、
`sushida-input-watch`（新規 305 行）、config.env の新キー 3 件
（`AUDIO_VOLUME_PERCENT` / `SCREEN_BRIGHTNESS_PERCENT` / `SCREEN_ZOOM_PERCENT`）、
launcher/session のズーム処理が中心。選定基準は Stage G §0 と同じ
（事故実績・変更頻度・検証コスト込みの手間）。

**環境制約**: 本作業環境には container engine（podman/docker）が無く、
bats・ShellCheck を実行できない。シェルスクリプトの挙動変更を伴う
リファクタリングは挙動証拠（bats）が取れないため本 Stage では行わない
（AGENTS.md §8「必要な検証が実行できない」）。pytest + checker で
完全に検証できる範囲に限定する。

| タスク | 効果 | 手間 | 判定 |
|---|---|---|---|
| H-01 config.env キー集合の contract 化 | 中〜高（キー追加のたびに 3 箇所手修正、乖離は実機起動失敗） | 小 | **実施** |
| H-02 input-watch の backlight 書き込み集約 | 小〜中（root daemon の未テスト経路を固定） | 極小 | **実施** |
| §3 の見送り群 | 小 or 負 | 中 | **見送り**（理由を記録） |

## 1. H-01: config.env キー集合の contract 化【優先度: 高】

**動機**: config.env の許可キー集合が 3 箇所に手書きで重複している —
checker の `allowed` 集合、launcher の parser `case`、network-watch の
parser `case`（後者 2 つは未知キーで起動失敗する）。FB-04/FB-06 では
キー追加のたびに 3 箇所すべてを手で直しており、1 箇所でも漏れると
**実機で kiosk または watcher が起動しない**が、現行 checker はこれを
検出しない（config.env ⊆ checker 集合 しか見ていない）。Stage G §6 の
「3 スクリプト目の parser が必要になったら再検討」は input-watch の
追加で発動条件に達している。

**方針**: シェルの parser 自体は変更しない（共有 lib 化は bats 不在のため
見送り、§3）。代わりにキー集合を contract の正本へ上げ、checker が
3 者を照合する。

**手順**:
1. `contracts/runtime-contract.json` に `config_keys`（文字列配列）を追加。
   値は現行 config.env の 6 キー。schema に同フィールドを追加
   （`^[A-Z][A-Z0-9_]*$`、uniqueItems、required）。
2. checker: `allowed` を `config_keys` から読む。launcher / network-watch
   の `while ... read -r line ... done < "$CONFIG_FILE"` ブロック内の
   `case` ラベル集合が `config_keys` と一致することを照合
   （エラーコードは既存の `DRIFT_CONFIG_KEY` を流用 — 新ドリフト種別を
   増やさないため G-05 の発動条件には当たらない）。
3. `handled_runtime_fields` に `config_keys` を追加。
4. fixture: 最小 repo の launcher/netwatch stub に parser ブロックを追加。
   ドリフト fixture（launcher のキー欠落・netwatch の余剰キー・
   config.env の未登録キー）を追加。
5. 文書: `docs/contract-inventory.md` に `config_keys`（CFG-01・checker coverage・
   error code）を追記。第1弾作業書の付録 A は「これ以上更新しない」確定文書の
   ため触らない。

**受け入れ条件**: launcher / netwatch / config.env のいずれか 1 箇所だけに
キーを足す・消すと checker が exit 1 になる。production シェル無変更。

**推奨 commit**: `refactor(contracts): make config.env key set a contract value (H-01)`

## 2. H-02: input-watch の backlight 書き込み集約【優先度: 中・手間: 極小】

**動機**: `set_brightness_percent` と `step_brightness` が
「device 検索 → max_brightness 読取 → clamp → 書込」を重複実装している。
root で動きキー入力に反応する唯一のプロセスなのに、ステップ経路
（`brightness_up/down`）には挙動テストが無い。

**手順**:
1. 先に characterization test を追加（step の上下・上限 100%・
   下限 5%（黒画面防止）・device 不在/max 不正で False）。現行コードで緑を確認。
2. `_write_brightness(device, max_raw, percent) -> bool` を抽出し両関数から使う。
3. 既存テスト・新テストとも無変更で緑。

**受け入れ条件**: 追加 test が refactor 前後で同一結果。既存
`test_input_watch.py` のソース assertion（定数・argv・ログ token）不変。

**推奨 commit**: `refactor(input-watch): share the backlight write path (H-02)`

## 3. 検討して見送った候補

| 候補 | 見送り理由 |
|---|---|
| launch/netwatch の config parser を共有 shell lib 化 | 本環境で bats 不可（挙動証拠なし）。H-01 で乖離は機械検出できるようになり、残る重複は「動くが冗長」なだけ |
| ズーム範囲（50–300 / 既定 180）を contract 化 | launcher・session・test に重複するが、FB-06 で入ったばかりで変更予定なし。シェル側の照合 regex が脆く、手間 > 利得 |
| input-watch を `sushida_os` package へ移す | 新規 shipped file の 3 点登録（P3）と release contract 変更を伴い、単一ファイルで凝集しているため利得が薄い |
| G-05 check-contracts.py 分割 | H-01 は既存エラーコード・既存節の拡張に留め、発動条件（新 contract 種別・adapter 大幅増）に当たらない |

## 4. 実施ゲート（Stage H 完了条件）

```bash
python3 tools/check-contracts.py
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make check-structure
git diff --check
```

- `make container-shell`（bats + ShellCheck）は本環境で実行不可 →
  未実施と明記。H-01/H-02 は shell を変更しないため挙動上の依存は無い。

## 5. Stage H 完了記録（2026-10-22）

### 状態表

| タスク | 状態 | コミット | 備考 |
|---|---|---|---|
| H-01 config.env キー集合の contract 化 | DONE | d587135 | runtime contract `config_keys`（6 キー）+ schema。checker が config.env / launcher parser / netwatch parser の 3 者を照合（`DRIFT_CONFIG_KEY`）。fixture 5 件追加（launcher 欠落・netwatch 余剰・parser loop 不在・contract 側削除・schema pattern）。production シェル無変更 |
| H-02 input-watch backlight 書き込み集約 | DONE | af0885a | `_backlight()` / `_write_brightness()` を抽出。先に characterization 2 件（step 上下・上限・5% 下限・sysfs 不正値）を追加し、抽出前後とも緑 |
| （付随）inventory TMO-06 の陳腐化 | DONE | da88d32 | FB-01 で 5→8 になった retry 回数が inventory に未反映だった |

### 逸脱

- H-01 手順 5 の「作業書 付録 A へ追記」は、第1弾作業書が「これ以上更新しない」
  確定文書であるため取りやめ、`docs/contract-inventory.md` のみ更新した
  （手順文を同コミットで修正済み）。
- 本クローンには `.venv` が無かったため、付録 C の手順どおり作成した
  （`.venv/` は git-ignore 済み）。git identity も未設定のため、設定は変更せず
  既存コミットと同じ author をコミット単位（`git -c`）で指定した。

### ゲート結果（2026-10-22, HEAD da88d32）

| 項目 | 結果 |
|---|---|
| python3 tools/check-contracts.py | exit 0 |
| pytest tests/static/ tests/contracts/ -q | 833 passed（基準 826 + H-01 5 件 + H-02 2 件） |
| make check-structure | exit 0 |
| git diff --check | exit 0 |
| make container-shell（bats + ShellCheck） | **未実施**（container engine なし）。H-01/H-02 とも shell 無変更 |
| make iso / verify / QEMU | **未実施**。H-02 は shipped file（`sushida-input-watch`）を変更したため、既存 ISO（R9/R10, `e5187348…`）は HEAD と一致しない。次回 `make iso` で反映・検証が必要 |
