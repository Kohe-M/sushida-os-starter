# 再現可能ビルド調査（Reproducible Builds Analysis）

- 調査日: 2026-07-21（Stage E-07）
- 対象: `scripts/build.sh` + `live-build/auto/{config,build}` + `builder/Dockerfile`
  による `sushida-os-amd64.iso` と 3 つの metadata artifact の生成
- **本書は入力の分類と現状の評価であり、bit-for-bit 再現を約束しない。**
  制御の実装は E-08 の範囲で、安全なものだけを段階的に導入する。

## 1. 分類の定義

| 分類 | 意味 |
|---|---|
| `deterministic` | 同一 commit から常に同一の bit 列になる（現状で保証済み） |
| `controlled` | 変動要因だが、現在のビルドが明示的に固定・記録している |
| `external-variable` | リポジトリ外の状態に依存し、意図的に固定しない（固定すべきでない） |
| `currently-uncontrolled` | 固定可能だが現在は固定していない（E-08 候補） |

## 2. 入力インベントリと分類

| # | 入力 | 分類 | 根拠・備考 |
|---|---|---|---|
| 1 | ソースツリー内容 | `deterministic` | `build.sh` が clean worktree を強制（dirty なら fail）。`auto/config` の `copy_tracked_tree` は `git ls-files` のみコピーし、symlink を拒否 |
| 2 | ソースファイルの mode | `deterministic` | git が実行 bit を管理、`cp -p` で保持。contract の mapping mode と checker が照合 |
| 3 | Debian package の版 | `external-variable` | mirror の現在状態に依存。**固定しない**（古い脆弱版への固定を避ける方針）。版は `package-manifest.txt` に全量記録され、`chromium/cage` は build-info と相互照合される |
| 4 | Debian mirror の内容・鍵 | `external-variable` | apt が署名検証。ネットワーク到達性も含む |
| 5 | builder イメージ（trixie）の apt 状態 | `external-variable` | `builder/Dockerfile` は tag 固定だが base image と tool 群の版は build 時点の mirror に依存 |
| 6 | `build_timestamp` | `controlled` | 実時刻を記録する設計（変動するが metadata として明示記録。source epoch とは別物として扱う） |
| 7 | ISO/SquashFS 内部の timestamp | `currently-uncontrolled` | `SOURCE_DATE_EPOCH` 未設定。live-build/mksquashfs/xorriso が実時刻を埋め込む（E-08 の第一候補） |
| 8 | chroot 内で生成されるファイルの timestamp/順序 | `currently-uncontrolled` | debootstrap・hook 実行の副産物。`SOURCE_DATE_EPOCH` で一部制御可能、完全制御は不可 |
| 9 | locale / timezone | `currently-uncontrolled`（一部 `controlled`） | `build.sh` は manifest 生成に `LC_ALL=C sort` を明示。それ以外の lb 実行環境の locale/TZ は builder の既定値任せ（E-08 候補: 明示固定） |
| 10 | umask | `currently-uncontrolled` | builder 内 root の既定 umask 依存。includes ファイルは `cp -p` で mode 保持されるため影響は生成物系のみ（E-08 候補） |
| 11 | ファイル列挙順 | `controlled` | manifest は `LC_ALL=C sort -u`。ISO 候補・manifest 候補の find も `LC_ALL=C sort -u`。squashfs/ISO 内部順序は mksquashfs/xorriso の決定的順序に依存（既定で入力順に決定的） |
| 12 | 設定 partition (`SUSHIDA-CFG`) | ほぼ `deterministic` | サイズ 64MiB・label・**UUID 固定**（`mkfs.ext4 -U 3b8c...`）。ただし ext4 の作成時刻フィールドは実時刻（`currently-uncontrolled`、E-08 候補） |
| 13 | `git_commit` / clean 判定 | `deterministic` | HEAD を記録し、verify が現 worktree と照合 |
| 14 | metadata の直列化 | `controlled` | `jq -n` による固定キー順の生成。build-info は schema_version 1 |
| 15 | `release_contract_sha256` / `package_manifest_sha256` | `deterministic` / `controlled` | E-04 で導入。contract は tracked、manifest は 3 の記録値のハッシュ |
| 16 | live-build 自身の版 | `external-variable` | builder イメージ由来。`live_build_version` として記録 |
| 17 | ISO volume ID / bootloader 生成物 | `currently-uncontrolled` | live-build が生成（timestamp を含み得る）。contract 上は presence 検証（`current_verification: "none"`） |

## 3. 評価のまとめ

- **同一 commit + 同一 mirror 状態 + 同一 builder イメージ**でも、現状は #7/#8/#9/#10/#12(作成時刻)/#17 により bit-for-bit は一致しない。
- 一方で**内容の同一性**（追跡対象ファイルの byte 一致・mode 一致・package 版の記録）は
  Stage E の manifest 駆動 verify によって commit 単位で証明される。
  再現性の目標は「bit 一致」より先に「差分の説明可能性」に置く。
- **固定してはならないもの**: package 版（#3）。セキュリティ更新を隠さないため、
  記録・照合のみ行い、pin しない。

## 4. E-08 で導入する制御の候補（安全な範囲）

| 優先 | 制御 | 内容 | リスク |
|---|---|---|---|
| 1 | `SOURCE_DATE_EPOCH` | clean HEAD の commit timestamp（`git log -1 --format=%ct`）を export。live-build/mksquashfs/xorriso が対応 | 低（`build_timestamp` は実時刻のまま別記録） |
| 2 | locale/TZ 固定 | `LC_ALL=C.UTF-8` `TZ=UTC` を build 実行環境で明示 | 低 |
| 3 | umask 固定 | `umask 022` を build.sh 冒頭で明示 | 低 |
| 4 | metadata の安定化 | 既に jq 固定キー順（追加作業なし、確認のみ） | — |

導入しないもの: package pinning（上記方針）、bootloader 生成物の byte 固定
（live-build 内部生成物であり、押さえ込みより presence + 実機起動検証が適切）。

## 5. 検証方法（将来、ビルド環境が用意できたとき）

1. 同一 commit で 2 回 `make iso` を実行し、`iso_sha256` を比較する。
2. 一致しない場合、`xorriso -indev` の listing / `unsquashfs -ll` の差分から
   変動源を特定し、本書 §2 の分類を更新する。
3. 差分が #3（package 版）由来である場合は仕様どおり（manifest の diff で説明可能）。
