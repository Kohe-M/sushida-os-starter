# Sushi-da OS 完全リファクタリング作業書

- 作成日: 2026-07-20
- 対象リポジトリ: `Kohe-M/sushida-os-starter`
- 基準 HEAD: `2f72ac0402e58b6cb7452f9a0d268ab8c18f81f5` (branch: `main`)
- Stage A 実装 commit: `48af5fa` → レビュー修正: `1a85fb3`
- **この文書のベースラインは `2f72ac0` 時点であり、進捗は別途追跡する。**
- 上位計画書: `docs/sushida-os-development-hardening-phases-1-6.md`（背景・設計の正本）
- 本文書の位置づけ: **実行の正本**。コーディング担当エージェントはこの文書の手順どおりに
  1 タスクずつ実施する。旧 `docs/phase2b2-work-order.md` は本文書 Stage A に統合済み。

---

# 0. はじめに

## 0.1 作業書作成時のベースライン（2026-07-20・固定。現在の commit ではない）

| 項目 | 作成時の状態 |
|---|---|
| HEAD / branch | `2f72ac0` / `main` |
| Phase 1（開発基盤） | ほぼ完了（commit `50b501b`〜`264ef8d`）。doctor/container wrapper/CI あり |
| Phase 2（contract checker） | 途中。レビューで BLOCKER 1〜4 + MEDIUM 指摘あり |
| `tests/static/test_wifi_setup_backend.py` | 1160 行・約45件。Phase 3 の characterization test は実質済み |
| `STRUCTURE.txt` | 陳腐化（contracts/, tools/, tests/contracts/, 多数の新規ファイルが未掲載） |
| `TASKS.md` | 旧形式（実装タスク 1〜20）のまま |
| `docs/acceptance-tests.md` | ID 表あり。commit / ISO SHA / 確認日の列がない |
| `README.md` | 既に最小化済みに近い |
| `Makefile` / CI | `make ci = test + check-contracts + git diff --check`、GitHub Actions は builder 内で `make ci` を実行 |

**進捗追跡は Stage 表の commit 欄と各タスクの完了報告で行う。この表は更新しない。**

## 0.2 環境と制約（全タスク共通・必読）

- **作業は必ず WSL 内で行う**: `wsl.exe -d Ubuntu -- bash -lc "cd ~/code/sushida-os-starter && ..."`
- **Windows 側パス（`\\wsl.localhost\...`）から git 操作・ファイル編集をしない**。
  Windows 側 `git status` に見える大量の mode 差分は表示 artifact であり、WSL 内では存在しない。
- Python: `/usr/bin/python3` = 3.10.12。venv/ensurepip あり。
- **pytest / bats / shellcheck はホストに未インストール**。podman はあり（docker はなし）。
- テスト実行手段（§2.4 参照）: ホスト venv に pytest を入れるか、podman builder コンテナを使う。
- **Git 操作禁止**: `commit / push / merge / rebase / reset / stash / clean / restore / worktree remove`
  はエージェントが実行しない。stage/commit はユーザーが行う。
- 禁止操作: flash/実デバイス書き込み、`dd`/mkfs/パーティション操作、ホスト設定変更、
  秘密情報の取得・表示・ログ出力、Sushi-da コンテンツのコピー/スクレイプ/注入。
- production runtime（`live-build/config/includes.chroot/**`、hooks、units、policy）の
  **挙動変更は Stage C/D でのみ、かつ挙動不変の分割・共通化として許可**される。
  Stage A/B/E/F では挙動を変えない。

---

# 1. 実行すべきリファクタリング全体像

## 1.1 Stage 一覧（実施順）

| Stage | 内容 | 対応 Phase | 完了判定 |
|---|---|---|---|
| **A** | contract checker 完成（レビュー BLOCKER 解消） | Phase 2 (P2-04〜P2-07) | §3.10 のゲート全成功 |
| **B** | Phase 1 残余確認（doctor 行動テストの穴埋め + ゲート） | Phase 1 (P1-02〜P1-04) | §4.3 のゲート全成功 |
| **C** | Wi-Fi backend モジュール分割（挙動不変） | Phase 3 | §5.11 のゲート全成功 |
| **D** | route 判定・kiosk signal 共通化（挙動不変） | Phase 4 | §6.9 のゲート全成功 |
| **E** | release manifest 正本化・ISO 照合・再現性 | Phase 5 | §7.10 のゲート全成功 |
| **F** | 文書正本化（AGENTS/TASKS/STRUCTURE/docs） | Phase 6 | §8.11 のゲート全成功 |

**並行禁止**: A↔C、C↔D、D↔E は同じ契約・パス・service 名・route 状態に触るため、
必ず直列に実施する（上位計画書 §1 準拠）。

## 1.2 スコープ外（やらないこと）

- 上位計画書 §7 の F-01〜F-04（SUSHIDA-CFG ラベル衝突、RTC 判定、console=ttyS0 方針、
  connection-in-progress 統合）は **独立タスク**。本作業書では扱わない。
- 新機能追加、production 挙動の意図的変更、UI 改善。
- ISO 実ビルド・実機検証（環境依存。各ゲートで「未実行」として正直に報告する）。

## 1.3 【最重要】Stage 間の checker メンテナンス依存

Stage A で作る checker adapter は **現行のファイル配置**を読む。後続 Stage が配置を変えるため、
各 Stage で checker/contract を追随させる必要がある。これを怠ると Stage A の成果が壊れる。

| 後続 Stage の変更 | checker/contract への影響 | 対処するタスク |
|---|---|---|
| C: Wi-Fi 定数が `sushida-wifi-setup` → `sushida_os/wifi/*.py` へ移動 | `RUNTIME_SOURCE_FILES["wifi"]`、timeout/URL/path adapter の参照先が 404 化 | C-08 で adapter 参照先を新モジュールへ更新 + release contract の mappings に package 追加 |
| D: route 判定が `sushida_os/runtime/routes.py` へ移動 | `_drift_routes` の launch/netwatch リテラル照合が不整合化 | D-04/D-06 で `_drift_routes` を新モジュール照合へ更新 |
| E: verify-iso.sh が manifest 駆動化 | `DRIFT_ISO_PATH` の「verify-iso.sh にパス文字列がある」検査が壊れる | E-03 で検査を「verify-iso.sh が release contract を読む」方式へ変更 |

---

# 2. 全タスク共通手順

## 2.1 開始ゲート（各タスクの最初に必ず実行）

```bash
cd ~/code/sushida-os-starter
git rev-parse --show-toplevel
git rev-parse HEAD
git branch --show-current
git status --short
git log --oneline -5
```

開始条件: 対象リポジトリである / detached でない / 前タスクの commit がある /
変更範囲を説明できる。作業ツリーが clean でない場合は **`reset` 等を実行せず停止して報告**。
ただし「前タスクの成果が未コミットで残っている」場合は、ユーザーに commit を求めるか、
その上に積み上げてよいか確認すること。

## 2.2 実装の進め方

1. タスクカードの「先に読むファイル」を実際に読んでから手を付ける。
2. 変更はタスクカードの「変更可能ファイル」だけに限定する（概ね 10 ファイル以内）。
3. テストは実装と同じタスクで追加・更新する（後回し禁止）。
4. 1 タスク終わるごとに §2.5 の検証を実行し、緑であることを確認してから次へ進む。
5. 無関係なリファクタリングを混ぜない。

## 2.3 環境セットアップ（最初の1回だけ）

```bash
cd ~/code/sushida-os-starter

# 方法1: ホスト venv（pytest のみ。軽量・推奨）
python3 -m venv .venv
.venv/bin/pip install pytest
# .venv が gitignore されていることを確認:
git check-ignore .venv && echo IGNORED || echo "NOT IGNORED — local/ 配下に作り直すこと"

# 方法2: podman builder（shellcheck/bats を含む全検証が可能）
make builder CONTAINER_ENGINE=podman
```

以降の記載で `PYTEST` は `.venv/bin/python -m pytest`（方法1）または
`make test-static` 等の Make 経由（方法2 のコンテナ内）を意味する。

## 2.4 検証コマンド対応表

| 目的 | ホスト venv | podman コンテナ |
|---|---|---|
| 静的テスト | `.venv/bin/python -m pytest tests/static/ -q` | `make container-test CONTAINER_ENGINE=podman` |
| contract テスト | `.venv/bin/python -m pytest tests/contracts/ -q` | 同上（`make test` に含まれる） |
| checker | `python3 tools/check-contracts.py`（pytest 不要） | 同上 |
| shell テスト | 不可（bats/shellcheck なし） | `make container-shell CONTAINER_ENGINE=podman` |
| CI 相当 | 上記の合成 + `git diff --check` | コンテナ内で `make ci` |

bats/shellcheck がホストにない環境では `make test-shell` は実行せず、
**「未実行」として報告**し、コンテナでの代替結果を添えること。

## 2.5 タスク完了時の検証（毎回）

```bash
cd ~/code/sushida-os-starter
python3 tools/check-contracts.py; echo "exit=$?"
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
git diff --check
git status --short
git diff --stat
```

タスクカードに追加の検証があればそれも実行する。

## 2.6 完了報告フォーマット（各タスクで提出）

```text
1. 変更概要
2. 変更ファイル
3. 維持した既存契約
4. 追加・変更したテスト
5. 実行コマンドと終了コード（実際に実行したものだけ）
6. 未実行項目（環境制約など、理由つき）
7. 残存リスク
8. git status --short
9. git diff --stat
```

**未実行の検証を PASS と書かない。** 失敗したまま次のタスクへ進まない。

## 2.7 停止条件（これに当たったら作業を止めて報告）

- 想定外のファイル差分が出た / テストが原因不明に赤い
- production 挙動を変えないと解決できないことが判明した
- contract 値そのものを変えないと整合しないことが判明した
- 秘密情報らしきものを見つけた

---

# 3. Stage A: contract checker 完成（Phase 2 完了）

**目的**: レビュー指摘の BLOCKER 1〜4 と MEDIUM を解消し、P2-07 ゲートを通す。
**変更可能ファイル**: `tools/check-contracts.py`、`tests/contracts/test_check_contracts.py`、
`Makefile`、`tests/static/test_development_tooling.py`、`docs/contract-inventory.md`。
**変更禁止**: `contracts/*.json`、`contracts/schema/*.json`、production runtime 全般。

| Step | 内容 | 状態 |
|---|---|---|
| A-00 | runtime adapters（URLs/paths/timeouts/routes）実装 | ✅ 48af5fa |
| A-01 | BLOCKER 1: static metadata ペア照合 | ✅ 48af5fa |
| A-02 | BLOCKER 4: release adapters | ✅ 48af5fa |
| A-03 | fixture 更新（production 形式 + chmod 同期） | ✅ 48af5fa |
| A-04 | BLOCKER 2: static metadata negative fixtures（双方向） | ✅ 48af5fa |
| A-05 | 新規 adapter drift テスト | ✅ 48af5fa |
| A-06 | MEDIUM: strict-markers 一元化 | ✅ 48af5fa |
| A-07 | contract-inventory.md へ coverage 追記 | ✅ 48af5fa（レビュー修正で LOW 修正：timeout 数を 14 に訂正） |
| A-08 | Stage A 検証 | ⬅ レビュー指摘 HIGH の config.env / MEDIUM の artifact 修正後 |
| A-09 | P2-07 ゲート | A-08 完了後 |

## A-01: BLOCKER 1 修正（static metadata ペア照合）

**場所**: `tools/check-contracts.py` の `_drift_release` 内（現行 826〜835 行目付近）。

現行の欠陥コード:

```python
    if build_sh:
        btext = build_sh.read_text()
        for field in req_fields:
            if field in static_vals:
                expected_val = str(static_vals[field])
                if expected_val not in btext and field not in btext:
                    result.error("DRIFT_METADATA_STATIC", "release",
                                 f"metadata.static_values.{field}", str(build_sh),
                                 f"static value {expected_val!r} or field {field!r} not found in build.sh")
                continue
```

置き換え後:

```python
    if build_sh:
        btext = build_sh.read_text()
        for field in req_fields:
            if field in static_vals:
                expected_val = str(static_vals[field])
                # Match the field/value pair in either production form:
                #   architecture=amd64
                #   --arg architecture "amd64"   (jq argument style in build.sh)
                patterns = (
                    rf"\b{re.escape(field)}\s*=\s*['\"]?{re.escape(expected_val)}['\"]?(?=\s|$)",
                    rf"--arg\s+{re.escape(field)}\s+['\"]{re.escape(expected_val)}['\"]",
                )
                if not any(re.search(pattern, btext, re.MULTILINE) for pattern in patterns):
                    result.error("DRIFT_METADATA_STATIC", "release",
                                 f"metadata.static_values.{field}", str(build_sh),
                                 f"static value {expected_val!r} for field {field!r} "
                                 "not found as a field/value pair in build.sh")
                continue
```

**根拠（検証済み）**: production `scripts/build.sh` は 110 行目 `--arg debian_release "trixie"`、
112 行目 `--arg architecture "amd64"`（jq 形式）→ 第2パターンに一致。
`(?=\s|$)` + `re.MULTILINE` で前方一致誤検出を防ぐ。contract 側・production 側のどちらを
壊してもペアが消えるので確実に失敗する。

**即座に確認**: `python3 tools/check-contracts.py` が exit 0 のままであること。

## A-02: BLOCKER 4 実装（release adapters）

`_drift_release` の末尾（mapping source 存在チェックの後）に次の3関数の呼び出しを追加する。
また `_scripts_checks` ループで各 script の本文を辞書に保存するよう改造する
（`script_texts[script_name] = _text`）。`verify_text = script_texts.get("verify-iso.sh", "")`
を `_drift_release_iso_paths` に渡す。

```python
KNOWN_METADATA_FORMATS = {"git-sha", "date-time", "sha256"}


def _drift_release_mappings(rc: dict, root: Path, result: Result) -> None:
    """Static consistency of source_image_mappings (check-only, no ISO access)."""
    for mapping in rc.get("source_image_mappings", []):
        src_rel = mapping["source"]
        image_path = mapping["image_path"]
        region = mapping["region"]
        label = f"source_image_mappings.{src_rel}"
        if region == "squashfs":
            # source must be exactly includes.chroot + image_path
            expected_src = f"{PRODUCTION_ROOT}{image_path}"
            if src_rel != expected_src:
                result.error("DRIFT_MAPPING_PATH", "release", label, src_rel,
                             f"source {src_rel!r} does not correspond to image path "
                             f"{image_path!r} (expected {expected_src!r})")
            # includes.chroot files are installed as root:root by live-build
            if mapping.get("owner") != "root" or mapping.get("group") != "root":
                result.error("DRIFT_MAPPING_OWNER", "release", label, src_rel,
                             "squashfs mappings must declare owner/group root:root")
        if mapping.get("current_verification") == "exact" and \
                mapping.get("comparison") not in ("cmp", "sha256"):
            result.error("DRIFT_COMPARISON", "release", label, src_rel,
                         "current_verification 'exact' requires content comparison "
                         f"(cmp/sha256), got {mapping.get('comparison')!r}")
        src = root / src_rel
        if not src.is_file() or src.is_symlink():
            continue  # existence is reported by the source-existence check
        actual_mode = f"{stat.S_IMODE(src.stat().st_mode):04o}"
        if actual_mode != mapping.get("mode"):
            result.error("DRIFT_MAPPING_MODE", "release", label, src_rel,
                         f"source mode {actual_mode} != contract {mapping.get('mode')!r}")


def _drift_release_iso_paths(rc: dict, verify_text: str, result: Result) -> None:
    """required_iso_paths ↔ mappings consistency and iso-root coverage."""
    mappings_by_image: dict[str, dict] = {}
    for mapping in rc.get("source_image_mappings", []):
        mappings_by_image.setdefault(mapping["image_path"], mapping)
    for entry in rc.get("required_iso_paths", []):
        path = entry["path"]
        label = f"required_iso_paths.{path}"
        if entry.get("match_type") == "regex":
            pattern = entry.get("path_pattern", "")
            try:
                rx = re.compile(pattern)
            except re.error as exc:
                result.error("DRIFT_PATH_PATTERN", "release", label, "contract",
                             f"invalid path_pattern: {exc}")
            else:
                if not rx.search(path):
                    result.error("DRIFT_PATH_PATTERN", "release", label, "contract",
                                 f"path_pattern {pattern!r} does not match path {path!r}")
        if entry["region"] == "squashfs":
            mapping = mappings_by_image.get(path)
            if mapping is None:
                result.error("DRIFT_ISO_PATH", "release", label, "contract",
                             f"required squashfs path {path!r} has no source image mapping")
                continue
            for attr in ("region", "file_type", "required", "security_critical"):
                if mapping.get(attr) != entry.get(attr):
                    result.error("DRIFT_ISO_PATH_ATTR", "release", label, "contract",
                                 f"mapping {attr}={mapping.get(attr)!r} != "
                                 f"iso path {attr}={entry.get(attr)!r}")
        elif entry["region"] == "iso-root":
            # verify-iso.sh writes initrd/squashfs in regex-escaped form
            if path not in verify_text and re.escape(path) not in verify_text:
                result.error("DRIFT_ISO_PATH", "release", label, "scripts/verify-iso.sh",
                             f"required ISO path {path!r} not referenced by verify-iso.sh")


def _drift_release_metadata(meta: dict, result: Result) -> None:
    """static_values/formats key consistency (value drift is checked separately)."""
    req_fields = meta.get("required_fields", [])
    for field in meta.get("static_values", {}):
        if field not in req_fields:
            result.error("DRIFT_METADATA_STATIC", "release",
                         f"metadata.static_values.{field}", "contract",
                         f"static value declared for non-required field {field!r}")
    for field, fmt in meta.get("formats", {}).items():
        if field not in req_fields:
            result.error("DRIFT_METADATA_FORMAT", "release",
                         f"metadata.formats.{field}", "contract",
                         f"format declared for non-required field {field!r}")
        if fmt not in KNOWN_METADATA_FORMATS:
            result.error("DRIFT_METADATA_FORMAT", "release",
                         f"metadata.formats.{field}", "contract",
                         f"unknown format {fmt!r} (known: {sorted(KNOWN_METADATA_FORMATS)})")
```

**落とし穴（検証済み）**: `scripts/verify-iso.sh` の `/live/initrd.img` は
`/live/initrd\.img` のバックスラッシュ形式でしか出現しない。`re.escape(path)` の
フォールバックが必須。

**即座に確認**: `python3 tools/check-contracts.py` が exit 0 のままであること
（実リポジトリの contract・配置はこの検査を全て通ることを作成者が確認済み）。

## A-03: fixture 更新（`tests/contracts/test_check_contracts.py`）

`_build_minimal_repo` を次の方針で更新する。**全 adapter を満たす内容**にすること。

### A-03-1. unit ファイルを個別内容に

```python
    unit_contents = {
        "sushida-kiosk.service":
            "[Service]\nRuntimeDirectory=sushida-os\nRuntimeDirectoryMode=0750\n",
        "sushida-network-watch.service": "[Service]\n",
        "sushida-navigation-watch.service": "[Service]\n",
        "sushida-config-prepare.service":
            "[Service]\nRuntimeDirectory=sushida-config\n",
        "sushida-wifi-setup.service":
            "[Service]\nRuntimeDirectory=sushida-wifi-setup\nRuntimeDirectoryMode=0700\n",
        "var-lib-sushida\\x2dconfig.mount":
            "[Mount]\nWhere=/var/lib/sushida-config\n",
    }
    for svc, content in unit_contents.items():
        (root / f"live-build/config/includes.chroot/etc/systemd/system/{svc}").write_text(content)
```

### A-03-2. 実行ファイルを production 形式の stub に

```python
    (root / "live-build/config/includes.chroot/usr/local/bin/sushida-launch").write_text(
        '#!/usr/bin/env bash\n'
        'readonly PROD_CONFIG="/etc/sushida-os/config.env"\n'
        'readonly PROD_RUNTIME="/run/sushida-os"\n'
        'readonly OFFLINE_URL="file://localhost/usr/share/sushida-os/offline.html"\n'
        'readonly SETUP_URL="http://127.0.0.1:8787/"\n'
        'mkdir -p "$BASE_RUNTIME"/{chromium,cache,tmp,downloads,xdg-runtime}\n'
        'rm -f -- "$BASE_RUNTIME/time-sync-required"\n'
        ': > "$BASE_RUNTIME/time-sync-required"\n'
        'route_tmp=$(mktemp "$BASE_RUNTIME/.active-route.XXXXXXXX")\n'
        'mv -f -- "$route_tmp" "$BASE_RUNTIME/active-route"\n'
        'ACTIVE_ROUTE="offline"\n'
        'ACTIVE_ROUTE="setup"\n'
        'ACTIVE_ROUTE="online"\n'
    )
    (root / "live-build/config/includes.chroot/usr/local/bin/sushida-network-watch").write_text(
        '#!/usr/bin/env bash\n'
        'readonly PROD_RUNTIME="/run/sushida-os"\n'
        'readonly ACTIVE_ROUTE_FILE="$RUNTIME_DIR/active-route"\n'
        'readonly TIME_SYNC_REQUIRED_MARKER="$RUNTIME_DIR/time-sync-required"\n'
        "printf '%s\\n' online\n"
        "printf '%s\\n' setup\n"
        "printf '%s\\n' offline\n"
        'case "$route" in online|setup|offline) printf \'%s\\n\' "$route" ;; *) return 1 ;; esac\n'
    )
```

**落とし穴**: `printf '%s\n' ...` はファイル上バックスラッシュ+n の2文字（shell の printf
書式そのまま）。Python 文字列では `"\\n"` と書くこと。

```python
    (root / "live-build/config/includes.chroot/usr/local/bin/sushida-navigation-watch").write_text(
        '#!/usr/bin/env python3\n'
        'from pathlib import Path\n'
        'PROD_RUNTIME = Path("/run/sushida-os")\n'
        'SESSIONS_SUBDIR = Path("chromium") / "Default" / "Sessions"\n'
        'DEFAULT_POLL_SECONDS = 2.0\n'
        'DEFAULT_COOLDOWN_SECONDS = 30.0\n'
    )
    (root / "live-build/config/includes.chroot/usr/local/bin/sushida-diagnostics").write_text(
        '#!/bin/sh\nexit 0\n'
    )
    (root / "live-build/config/includes.chroot/usr/local/libexec/sushida-session").write_text(
        '#!/usr/bin/env bash\n'
        'readonly OFFLINE_URL="file://localhost/usr/share/sushida-os/offline.html"\n'
        'readonly SETUP_URL="http://127.0.0.1:8787/"\n'
        '    _raw_at=3\n'
        '--user-data-dir="${XDG_RUNTIME_DIR%/xdg-runtime}/chromium"\n'
    )
    (root / "live-build/config/includes.chroot/usr/local/libexec/sushida-config-prepare").write_text(
        '#!/usr/bin/env bash\n'
        'CONFIG_MOUNT="/var/lib/sushida-config"\n'
        'STATUS_DIR="/run/sushida-config"\n'
        'readonly STATUS_FILE="$STATUS_DIR/config-storage"\n'
    )
    (root / "live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup").write_text(
        '#!/usr/bin/env python3\n'
        'from pathlib import Path\n'
        'PORT = 8787\n'
        'CONFIG_MOUNT = Path("/var/lib/sushida-config")\n'
        'CONFIG_DIR = CONFIG_MOUNT / "network"\n'
        'CONFIG_FILE = CONFIG_DIR / "setup.json"\n'
        'STORAGE_STATUS = Path("/run/sushida-config/config-storage")\n'
        'CSRF_TOKEN_FILE = Path("/run/sushida-wifi-setup/csrf-token")\n'
        'MAX_REQUEST_BYTES = 8192\n'
        'COMMAND_TIMEOUT_SECONDS = 40\n'
        'REQUEST_READ_TIMEOUT_SECONDS = 5\n'
        '    BACKOFF_MIN = 2.0\n'
        '    BACKOFF_MAX = 16.0\n'
        '    MAX_RETRIES = 5\n'
        '    deadline = time.monotonic() + 120.0\n'
        '                    "activation", "--wait", "30", "connection", "up",\n'
        '                    "id", CONNECTION_NAME, "passwd-file", passwd_path,\n'
        '                    timeout=35, pass_fds=(passwd_fd,),\n'
        '                "activation", "--wait", "30", "connection", "up",\n'
        '                "id", CONNECTION_NAME, timeout=35,\n'
    )
```

activation ブロックは **必ず2サイト**書くこと（`min_count=2` の adapter があるため）。

### A-03-3. build.sh fixture を production の jq 形式に

```python
    (root / "scripts/build.sh").write_text(
        'ISO_NAME="sushida-os-amd64.iso"\n'
        'SHA256SUMS="SHA256SUMS"\n'
        'package-manifest.txt\n'
        'build-info.json\n'
        'mkdir -p artifacts/\n'
        'git rev-parse HEAD\n'
        'git_dirty=\n'
        'date -u +%Y\n'
        'package_version chromium\n'
        'package_version cage\n'
        'lb --version\n'
        'sha256sum ...\n'
        '--arg architecture "amd64"\n'
        '--arg debian_release "trixie"\n'
    )
```

### A-03-4. verify-iso.sh fixture に iso-root パスを追加

```python
    (root / "scripts/verify-iso.sh").write_text(
        'sushida-os-amd64.iso\nSHA256SUMS\npackage-manifest.txt\nbuild-info.json\n'
        '/live/filesystem.squashfs\n/live/vmlinuz\n/live/initrd.img\n'
    )
```

### A-03-5. mode 同期ループを `_build_minimal_repo` 末尾に追加

```python
    # Align fixture file modes with the contract mapping declarations
    rc_data = json.loads((root / "contracts/release-contract.json").read_text())
    for mapping in rc_data["source_image_mappings"]:
        p = root / mapping["source"]
        if p.is_file():
            p.chmod(int(mapping["mode"], 8))
```

umask 非依存になり、script 系（0755）と config 系（0644）の両方が正しくなる。

## A-04: BLOCKER 2 テスト（双方向 negative fixture）

`TestCheckContracts` に追加:

```python
    # ── Static metadata drift (contract side) ──────────────────────

    @pytest.mark.parametrize(
        ("field", "wrong_value"),
        [
            ("architecture", "arm64"),
            ("debian_release", "bookworm"),
        ],
    )
    def test_static_metadata_drift_exit_1(self, clean_repo: Path,
                                          field: str, wrong_value: str) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        data["metadata"]["static_values"][field] = wrong_value
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_METADATA_STATIC" in r.stdout

    # ── Static metadata drift (production side) ────────────────────

    @pytest.mark.parametrize(
        ("field", "good_value", "wrong_value"),
        [
            ("architecture", "amd64", "arm64"),
            ("debian_release", "trixie", "bookworm"),
        ],
    )
    def test_static_metadata_production_drift_exit_1(
            self, clean_repo: Path, field: str, good_value: str, wrong_value: str) -> None:
        bs = clean_repo / "scripts/build.sh"
        bs.write_text(bs.read_text().replace(
            f'{field} "{good_value}"', f'{field} "{wrong_value}"'))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_METADATA_STATIC" in r.stdout

    def test_static_metadata_equals_form_accepted(self, clean_repo: Path) -> None:
        """The architecture=amd64 assignment form must also be recognised."""
        bs = clean_repo / "scripts/build.sh"
        bs.write_text(bs.read_text()
                      .replace('--arg architecture "amd64"', 'architecture="amd64"')
                      .replace('--arg debian_release "trixie"', 'debian_release="trixie"'))
        r = _run_checker(clean_repo)
        assert r.returncode == 0, f"checker failed:\n{r.stdout}"
```

## A-05: 新規 adapter の drift テスト

```python
    # ── Runtime timeout adapter drift ──────────────────────────────

    @pytest.mark.parametrize(
        ("rel", "old", "new"),
        [
            ("usr/local/libexec/sushida-wifi-setup",
             "COMMAND_TIMEOUT_SECONDS = 40", "COMMAND_TIMEOUT_SECONDS = 41"),
            ("usr/local/libexec/sushida-wifi-setup",
             '"--wait", "30"', '"--wait", "25"'),
            ("usr/local/libexec/sushida-wifi-setup",
             "timeout=35", "timeout=36"),
            ("usr/local/libexec/sushida-wifi-setup",
             "BACKOFF_MIN = 2.0", "BACKOFF_MIN = 3.0"),
            ("usr/local/libexec/sushida-wifi-setup",
             "MAX_RETRIES = 5", "MAX_RETRIES = 6"),
            ("usr/local/libexec/sushida-wifi-setup",
             "deadline = time.monotonic() + 120.0",
             "deadline = time.monotonic() + 130.0"),
            ("usr/local/bin/sushida-navigation-watch",
             "DEFAULT_POLL_SECONDS = 2.0", "DEFAULT_POLL_SECONDS = 5.0"),
            ("usr/local/bin/sushida-navigation-watch",
             "DEFAULT_COOLDOWN_SECONDS = 30.0", "DEFAULT_COOLDOWN_SECONDS = 31.0"),
            ("usr/local/libexec/sushida-wifi-setup",
             "REQUEST_READ_TIMEOUT_SECONDS = 5", "REQUEST_READ_TIMEOUT_SECONDS = 6"),
            ("usr/local/libexec/sushida-wifi-setup",
             "MAX_REQUEST_BYTES = 8192", "MAX_REQUEST_BYTES = 4096"),
            ("usr/local/libexec/sushida-session",
             "_raw_at=3", "_raw_at=4"),
        ],
    )
    def test_runtime_timeout_drift_exit_1(self, clean_repo: Path,
                                          rel: str, old: str, new: str) -> None:
        p = clean_repo / "live-build/config/includes.chroot" / rel
        p.write_text(p.read_text().replace(old, new))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_TIMEOUT" in r.stdout

    # ── URL / route / path drift ───────────────────────────────────

    def test_setup_url_drift_exit_1(self, clean_repo: Path) -> None:
        p = clean_repo / "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
        p.write_text(p.read_text().replace(
            "http://127.0.0.1:8787/", "http://127.0.0.1:9999/"))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_URL" in r.stdout

    def test_offline_url_drift_exit_1(self, clean_repo: Path) -> None:
        p = clean_repo / "live-build/config/includes.chroot/usr/local/libexec/sushida-session"
        p.write_text(p.read_text().replace(
            "file://localhost/usr/share/sushida-os/offline.html",
            "file://localhost/usr/share/sushida-os/other.html"))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_URL" in r.stdout

    def test_route_drift_exit_1(self, clean_repo: Path) -> None:
        p = clean_repo / "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
        p.write_text(p.read_text().replace('ACTIVE_ROUTE="online"', 'ACTIVE_ROUTE="broken"'))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_ROUTE" in r.stdout

    def test_csrf_path_drift_exit_1(self, clean_repo: Path) -> None:
        p = clean_repo / "live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup"
        p.write_text(p.read_text().replace(
            "/run/sushida-wifi-setup/csrf-token", "/run/other/csrf-token"))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_PATH" in r.stdout

    # ── Release mapping / ISO path drift ───────────────────────────

    def test_mapping_image_path_drift_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        data["source_image_mappings"][0]["image_path"] = \
            "/etc/chromium/policies/managed/other.json"
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_MAPPING_PATH" in r.stdout

    def test_mapping_mode_drift_exit_1(self, clean_repo: Path) -> None:
        p = clean_repo / "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
        p.chmod(0o644)  # contract declares 0755
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_MAPPING_MODE" in r.stdout

    def test_iso_path_mapping_missing_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        data["source_image_mappings"] = [
            m for m in data["source_image_mappings"]
            if m["image_path"] != "/etc/systemd/system/sushida-kiosk.service"
        ]
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_ISO_PATH" in r.stdout

    def test_path_pattern_drift_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        for entry in data["required_iso_paths"]:
            if entry.get("match_type") == "regex":
                entry["path_pattern"] = "^/live/nomatch.*$"
                break
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_PATH_PATTERN" in r.stdout

    def test_comparison_consistency_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        for m in data["source_image_mappings"]:
            if m["current_verification"] == "exact":
                m["comparison"] = "presence"
                break
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_COMPARISON" in r.stdout

    def test_metadata_format_drift_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        data["metadata"]["formats"]["iso_sha256"] = "md5"
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_METADATA_FORMAT" in r.stdout
```

**既存テストとの整合メモ**:
- `test_mapping_image_path_drift_exit_1` は `DRIFT_ISO_PATH` も同時に出るが assert は
  `DRIFT_MAPPING_PATH` の存在のみなので問題ない。
- 既存の `test_verify_script_missing_artifact_exit_1` / `test_artifact_drift_exit_1` /
  `test_checksum_missing_exit_1` は A-02/A-03 後に別コードの error も併発するが、
  assert 対象のコードは引き続き出るので壊れない。

## A-06: MEDIUM 修正（strict-markers 一元化）

方針: 共通設定は `pyproject.toml` に残し、Makefile 側の重複を除去（レビュー推奨形）。

### A-06-1. `Makefile`（59〜63 行目）

```make
# before
test-static:
	$(PYTHON) -m pytest tests/static/ --strict-markers -ra

test-contracts:
	$(PYTHON) -m pytest tests/contracts/ --strict-markers -ra

# after
test-static:
	$(PYTHON) -m pytest tests/static/

test-contracts:
	$(PYTHON) -m pytest tests/contracts/
```

### A-06-2. `tests/static/test_development_tooling.py` も同時更新（重要）

現行の `test_test_static_uses_strict_flags` は **Makefile 内のフラグを assert している**。
A-06-1 だけだと static テストが赤くなる。次のように差し替える:

```python
PYPROJECT = Path("pyproject.toml")

def test_pytest_strict_flags_in_pyproject() -> None:
    """Common pytest flags live in pyproject.toml, not duplicated in Makefile."""
    text = PYPROJECT.read_text()
    assert "--strict-markers" in text
    assert "-ra" in text


def test_makefile_does_not_duplicate_pytest_flags() -> None:
    text = MAKEFILE.read_text()
    assert "--strict-markers" not in text
```

`pyproject.toml` 自体は **変更不要**（現行の `addopts = "-ra --strict-markers"` を維持）。
前回 commit `2f72ac0` は「重複削除」と言いつつ残っていたので、今回の commit メッセージには
その経緯を正直に書くこと。

## A-07: 設計記録の更新（`docs/contract-inventory.md`）

末尾に「Checker coverage」節を追加する:

1. **Stage A で実装した check-only 照合の一覧**（A-00 の runtime 照合表 + A-01/A-02 の項目）。
2. **Phase 5 への正式移管事項**（レビュー BLOCKER 4 の「移管するなら設計記録へ明示」要件）:
   - ISO 実イメージの抽出（xorriso/unsquashfs）と内容バイト照合 → Stage E (E-02/E-03)。
   - `current_verification` の `presence` → `exact` 昇格 → Stage E。
   - 生成後 `build-info.json` の `metadata.formats` 実値検証・schema version・manifest hash 相互照合 → E-04。
   - bootloader 領域 mapping（inventory の SIM-19〜SIM-22）は release-contract 未登録 → E-01 で扱う。
3. 新規エラーコード一覧（付録 B 参照）を簡潔に列挙。

## A-08: Stage A 検証

```bash
cd ~/code/sushida-os-starter
python3 tools/check-contracts.py; echo "exit=$?"        # 0 であること
python3 tools/check-contracts.py --json                  # ok:true であること
.venv/bin/python -m pytest tests/contracts/ -q           # 既存21件+新規約25件 all pass
.venv/bin/python -m pytest tests/static/ -q              # all pass
make test-static                                         # Make 入口でも pass
make test-contracts
make check-contracts
make ci                                                  # exit 0
git diff --check
```

**期待結果**: checker exit 0 / warnings なし。tests/contracts 全 pass。tests/static 全 pass。

## A-09: P2-07 ゲート（Stage A 完了判定）

§A-08 が全て成功し、以下を満たすこと:

- contract file が正本候補として存在し、既存ランタイムはまだ contract を直接読まない。
- contract と実装の不一致が fixture テストで検出できる（A-04/A-05）。
- レビュー最終判定表の全項目が ✅:

| 項目 | 目標 |
|---|---|
| Static metadataをskipしない | ✅（維持） |
| Fixtureにstatic値追加 | ✅（A-03-3） |
| Production runtime非変更 | ✅（§3 の変更禁止を厳守） |
| Static値の正確な照合 | ✅（A-01） |
| Static値negative fixture | ✅（A-04 双方向） |
| Runtime agreed coverage | ✅（A-00 + A-03/A-05） |
| Release mapping／ISO coverage | ✅（A-02 + A-05。ISO 実体照合は A-07 で Phase 5 移管を明記） |
| `strict-markers`整理 | ✅（A-06） |

完了したら §2.6 の形式で報告し、ユーザーの review/commit を待つ。

---

# 4. Stage B: Phase 1 残余確認（開発基盤の固定化）

**目的**: doctor の行動テストの穴を埋め、P1-04 ゲートを再確認する。
**変更可能ファイル**: `tests/shell/dev-tools.bats`、`docs/build.md`（必要時のみ）。
**変更禁止**: production runtime、`scripts/doctor.sh` の挙動変更。

## B-01: doctor 行動テストのギャップ確認と追加

**先に読むファイル**: `scripts/doctor.sh`、`tests/shell/dev-tools.bats`。

現状（調査済み）: doctor.sh には docker/podman 検査、daemon 接続検査、OVMF CODE+VARS 検査、
WSL `/mnt/c` 警告が実装済み。dev-tools.bats には doctor 系 6 件を含む 21 件のテストがある。

**手順**:
1. 次のケースが dev-tools.bats で検証されているか1つずつ突き合わせる:
   - 必須 command が全て存在 → PASS / exit 0
   - `pytest` だけ不足 → FAIL（既存テストあり）
   - docker/podman が両方なし → `container_daemon=FAIL`
   - container daemon 未接続 → `container_daemon_<engine>=FAIL`
   - QEMU はあるが OVMF がない → `ovmf_code=FAIL` / `ovmf_vars=FAIL`
   - WSL 上 `/mnt/c` 配下で警告 → WARN
   - doctor がファイルを作成しない（既存テストあり）
2. 未カバーのケースだけを、既存の stub command パターン（fake PATH + 偽 docker/podman）に
   倣って追加する。実 container engine・ネットワークに触れないこと。
3. 終了コードと出力（PASS/FAIL/WARN）の両方を assert する。

**検証**: `make container-shell CONTAINER_ENGINE=podman`（bats はコンテナ内で実行）。

**受け入れ条件**: 上記ケースが終了コードと出力で検証される。既存テスト全 pass。

**推奨 commit**: `test(dev): complete doctor profile behavior coverage`

## B-02: Phase 1 ゲート（P1-04 再確認）

```bash
git diff --check
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make container-shell CONTAINER_ENGINE=podman   # test-shell 相当
make container-test  CONTAINER_ENGINE=podman   # make test 相当
# コンテナ内で: make ci
```

**完了条件**: 全コマンド成功、production runtime の差分なし、GitHub Actions が `make ci`
を使っている（変更不要のはず）。結果を §2.6 形式で報告。

---

# 5. Stage C: Wi-Fi backend モジュール分割（Phase 3）

**目的**: `usr/local/libexec/sushida-wifi-setup`（1310 行）を責務別に分割し、
状態機械・NetworkManager 操作・永続化・HTTP を独立テスト可能にする。
**最重要条件**: **挙動変更を行わない**（上位計画書 Phase 3 の現行維持リスト全項）。
**安全網**: `tests/static/test_wifi_setup_backend.py`（ characterization test、実質済み）が
**各タスク後に変更なく pass すること**が分割の正しさの証明である。
**変更可能ファイル**: `live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup`、
`live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/**`（新規）、
`tests/static/test_wifi_setup_backend.py`（loader 部分のみ）、`tests/contracts/`（fixture）、
`contracts/release-contract.json`（C-08 のみ）、`tools/check-contracts.py`（C-08 のみ）、
`docs/`（該当節）。

## C-00: 分割準備（前提確認タスク）

**手順**:
1. `tests/static/test_wifi_setup_backend.py` の `_load_backend()` が
   extensionless の production ファイルを `SourceFileLoader` で読んでおり、
   `sys.dont_write_bytecode = True` が設定されていることを確認する（確認のみ・変更禁止）。
2. `.venv/bin/python -m pytest tests/static/test_wifi_setup_backend.py -q` が **変更前に緑**
   であることを記録する。赤い場合は Stage C を開始せず停止して報告。
3. `python3 tools/check-contracts.py` が exit 0 であることを記録する。

**受け入れ条件**: 分割前の緑の基準線が記録されている。

## C-01: `types.py` 抽出（P3-02）

**新規**: `live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/__init__.py`、
`.../sushida_os/wifi/__init__.py`、`.../sushida_os/wifi/types.py`

**手順**:
1. `sushida-wifi-setup` から `CONNECT_*` 状態定数、security mode 定数、request/result を表す
   値を immutable dataclass / enum として `types.py` に移す。
2. password を `__repr__` に出さない（`repr=False`）。既存の状態文字列との互換を維持する。
3. entrypoint は `from sushida_os.wifi.types import ...` に差し替える（それ以外は触らない）。
4. テスト用 loader 対応: `tests/static/test_wifi_setup_backend.py` の `_load_backend()` に
   `sys.path.insert(0, "live-build/config/includes.chroot/usr/lib/python3/dist-packages")`
   を追加する（`sys.dont_write_bytecode = True` は維持）。
5. C-00 と同じ検証を実行し、全て緑であることを確認。

**受け入れ条件**: characterization test が変更なく pass。import 失敗時に資格情報を出さない。

**推奨 commit**: `refactor(wifi): extract immutable connection types`

## C-02: `nmcli.py` 抽出（P3-03）

**手順**: subprocess 呼び出し（`run_nmcli`、stage 実行、scan、security 分類、profile
作成/削除/activation、`managed_wifi_active`、timeout、error 分類）を `wifi/nmcli.py` に移す。
- argv に password を含めない、passwd-file FD 方式はそのまま。
- C-01 と同じ手順 5 の検証を実施。

**受け入れ条件**: characterization test pass。production の command 列は一字も変えない。

**推奨 commit**: `refactor(wifi): isolate NetworkManager command adapter`

## C-03: `storage.py` 抽出（P3-04）

**手順**: CSRF token 管理、credential load/save、atomic write（temp+rename）、mode/owner、
symlink 拒否、directory traversal 拒否、永続化 unavailable 時の fallback を `wifi/storage.py` に移す。
- 例外 message に secret を含めない。JSON 形式互換。

**推奨 commit**: `refactor(wifi): isolate credential and token storage`

## C-04: `coordinator.py` 抽出（P3-05）

**手順**: 接続状態・pending request・pending interactive（latest-wins）・Event/Lock・
HTTP 応答後 activation・worker handoff・terminal result 公開・shutdown を
`wifi/coordinator.py` に移す。global 変数を class 内に閉じ込め、NetworkManager は
adapter 注入にする。`start_after_response()` を明示 API にする。

**推奨 commit**: `refactor(wifi): encapsulate connection coordinator state machine`

## C-05: `restore.py` 抽出（P3-06）

**手順**: `restore_saved_connection`（retry policy、backoff、cancel、interactive 優先、
managed profile active 判定）を `wifi/restore.py` に移す。coordinator の public API のみ使用。
test 用 clock/sleeper を注入可能にする。

**推奨 commit**: `refactor(wifi): isolate saved-connection restore supervisor`

## C-06: `web.py` 抽出（P3-07）

**手順**: HTTP handler、CSRF/Origin/Fetch Metadata 検証、request parsing、response、
HTML template（CSP hash 維持）、`/status.json` を `wifi/web.py` に移す。
既存 HTTP status・既存 HTML を変更しない。応答 flush 後 activation を維持する。

**推奨 commit**: `refactor(wifi): isolate HTTP setup service layer`

## C-07: entrypoint 薄型化（P3-08）

**手順**: `sushida-wifi-setup` は config 構築・依存生成・coordinator 生成・worker/restore 起動・
HTTP server 起動・shutdown のみを行う約 100 行以下の wrapper にする。
**systemd unit の ExecStart は変更しない**（`sushida-wifi-setup.service` を触らない）。
import 失敗時に資格情報を出さない。

**受け入れ条件**: characterization test 全 pass + `python3 -m py_compile` で entrypoint と
package 全ファイルが構文 OK。

**推奨 commit**: `refactor(wifi): reduce setup entrypoint to dependency wiring`

## C-08: package の image 配置と checker/contract 追随（P3-09 + §1.3）

**目的**: 新 package ファイルを release contract に登録し、Stage A の adapter を新配置に追随させる。

**手順**:
1. `contracts/release-contract.json` の `source_image_mappings` に
   `sushida_os/**` の各ファイルを追加する（mode 0644、owner root、comparison cmp、
   `current_verification: "presence"`）。`required_iso_paths` にも security-critical な
   module を追加するかは contract-inventory を更新して判断する。
2. `tools/check-contracts.py` の `RUNTIME_SOURCE_FILES["wifi"]` や timeout/URL/path adapter が
   参照していた定数の新しい所在（`nmcli.py`/`storage.py`/`restore.py`/`web.py`）に
   参照先キーを付け替える。adapter の source key を増やしてよい
   （例: `"wifi_nmcli"`, `"wifi_storage"` …）。
3. `tests/contracts/test_check_contracts.py` の fixture に新 package ファイルの stub を追加し、
   drift テストの `rel` パスを新配置に更新する。
4. 検証: `python3 tools/check-contracts.py` exit 0 + contract テスト全 pass。
5. `.pyc` 方針を文書化: image 内で `.pyc` を生成しない方針（test は
   `sys.dont_write_bytecode = True` 維持）、または hook で compile する方針かを決め、
   `090-validate-image.hook.chroot` の import/compile 確認と整合させる。

**受け入れ条件**: checker exit 0、contract テスト全 pass、characterization test 全 pass。

**推奨 commit**: `build(wifi): include and validate modular backend package`

## C-09: Phase 3 統合ゲート（P3-10）

```bash
.venv/bin/python -m pytest tests/static/ -q
make container-shell CONTAINER_ENGINE=podman    # bats
make container-test  CONTAINER_ENGINE=podman    # make test
python3 tools/check-contracts.py
git diff --check
```

可能なら container 内で `make iso` / `make verify`（実行できなければ「未実行」と報告）。

**実機回帰項目（未実行と明記して報告）**: Wi-Fi 設定ページ表示、接続成功、寿司打への遷移、
restore 中 interactive、再起動後 restore、password 非露出。

**完了条件**: 外部挙動が変わっていない。各モジュールが個別テスト可能。
entrypoint が薄い（概ね 100 行以下）。

---

# 6. Stage D: route 判定・kiosk signal 共通化（Phase 4）

**目的**: network watcher・navigation watcher・launcher に分散した route 判定と
kiosk 再起動処理を共通化する。**挙動変更を行わない**。
**変更可能ファイル**: 上記3スクリプト、`sushida_os/runtime/**`（新規）、
`/usr/local/libexec/sushida-kiosk-signal`（新規）、`tools/check-contracts.py`、
`contracts/`（runtime contract 拡張時のみ）、`tests/**`、`docs/`。

## D-01: route 状態モデル定義（P4-01）

**新規**: `live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/runtime/__init__.py`、`.../runtime/routes.py`

**手順**:
1. route enum（`online/setup/offline`、将来 `time-sync`）、input model（connectivity、
   setup 可否、time sync、connection 中か、navigation 違反、現在 route）、output model
   （desired route、restart 要否、reason、retry/backoff class）を pure function で実装。
2. 表形式の unit test を `tests/static/test_route_decision.py`（新規）に作る
   （上位計画書 P4-07 の表をそのまま使える）。
3. secret や URL 全文を state に保存しない。

**受け入れ条件**: 空 route を返さない。unknown 入力は fail closed（offline 側）。

**推奨 commit**: `refactor(runtime): define pure route decision model`

## D-02: runtime state protocol（P4-02）

**手順**: `/run/sushida-os/runtime-state.json` の schema（`schema_version: 1`、`active_route`、
`time_sync_required`、`connection_in_progress`、`last_reason`）を定義し、atomic write /
symlink 拒否 / unknown schema version fail closed / URL・SSID・password 非保存を実装。
shell と Python 双方から安全に読める形式にする。単体テスト追加。

**推奨 commit**: `feat(runtime): define volatile route state protocol`

## D-03: safe signal helper（P4-03）

**新規**: `live-build/config/includes.chroot/usr/local/libexec/sushida-kiosk-signal`

**手順**: systemd MainPID 取得・PID/UID/cgroup 検証・signal 送信・固定 enum reason ログを行う
helper を実装。任意 PID/signal/service 名を受け取らない。URL/SSID/secret をログしない。
dry-run/test mode を用意する。**現在の `sushida-network-watch` の `restart_kiosk()` と
`sushida-navigation-watch` の `restart_kiosk()` が行っている検証（active 確認、MainPID>1、
同一 UID、cgroup に service 名）と完全に同じ判定にすること**——両ファイルを先に読んで写す。

**推奨 commit**: `refactor(runtime): centralize safe kiosk restart signaling`

## D-04: network watcher の route model 移行（P4-04 + §1.3）

**手順**:
1. `sushida-network-watch` の `desired_route()` を D-01 の pure function 呼び出しに置き換え、
   time-sync marker を D-02 の state protocol へ移す。route 差分がある場合だけ D-03 の
   helper を呼ぶ。
2. **checker 追随**: `_drift_routes` が launch/netwatch のリテラルを読んでいるため、
   新配置（`routes.py` の route 定数 + launch/netwatch が model を呼ぶ構造）に照合方法を
   更新する。contract テストの fixture も追随。
3. `tests/shell/network-watch.bats`（343 行）が変更なく pass することを確認
   （挙動不変の主要証拠）。

**受け入れ条件**: 既存 online/setup/offline 動作維持。同じ route で再起動しない。

**推奨 commit**: `refactor(network): use shared route decision and signal helper`

## D-05: navigation watcher の signal helper 移行（P4-05）

**手順**: Python 内の MainPID/UID/cgroup 検証を削除し、URL 分類だけを担当させる。
blocked navigation 時に固定 reason で D-03 helper を呼ぶ。target failure と blocked
navigation を混同しない。`tests/static/test_navigation_watch.py`（629 行）が
変更なく pass すること（loader が entrypoint を読む構造への追随だけは許可）。

**推奨 commit**: `refactor(navigation): delegate kiosk restart to safe helper`

## D-06: launcher の route 出力統合（P4-06）

**手順**: `sushida-launch` の active route 記録を state protocol へ移し、setup/offline/時計判定の
page 選択を routes model へ集約する。`tests/shell/launch.bats`（572 行）が変更なく pass すること。
checker の `DRIFT_PATH`/`DRIFT_ROUTE` adapter を追随。

**推奨 commit**: `refactor(kiosk): centralize startup route selection`

## D-07: route integration test（P4-07）

**手順**: 上位計画書の表（connectivity × time sync × connection × navigation → expected）を
そのままテスト化。追加: 同じ route では signal しない / route 変更時だけ1回 signal /
helper が PID 検証失敗時に signal しない / unknown state fail closed / corrupted JSON の安全処理。

**推奨 commit**: `test(runtime): cover route matrix and kiosk signal safety`

## D-08: Phase 4 ゲート（P4-08）

```bash
make container-test CONTAINER_ENGINE=podman
python3 tools/check-contracts.py
git diff --check
```

可能なら `make iso && make verify && make test-qemu-runtime`（未実行なら明記）。

**実機確認（未実行と明記）**: offline 起動、setup 起動、Wi-Fi 接続、接続中 setup 維持、
time sync 待機、prohibited navigation からの復帰、unnecessary restart なし。

---

# 7. Stage E: release manifest・ISO 完全照合・再現可能ビルド（Phase 5）

**目的**: release ISO が source tree と一致することを manifest から一貫して証明する。
**変更可能ファイル**: `contracts/release-contract.json`、`contracts/schema/`、
`scripts/verify-iso.sh`、`scripts/build.sh`、`scripts/clean.sh`、`tools/`、
`tests/contracts/`、`tests/static/`、`docs/`。**checker と verify が release contract を
正本として読む構造への変更はこの Stage の本題である。**

## E-01: release manifest 正本化（P5-01）

**手順**:
1. `contracts/release-contract.json` に bootloader 領域の mapping を追加する
   （inventory の SIM-20〜22: grub.cfg 系・isolinux 系。region は `"iso-root"`、
   comparison は `"presence"`、`current_verification: "none"` から始める）。
   builder イメージ（SIM-19）は ISO 内容ではないので manifest には入れない
   （schema の region enum を広げない方針）。
2. `required_iso_paths` に `boot/grub/grub.cfg` 等を追加し、A-02 の iso-root 検査
   （`DRIFT_ISO_PATH`）が通るよう verify-iso.sh 側の参照も確認する。
3. fixture（A-03）に新 mapping の source ファイル stub を追加する。
4. manifest に存在しない critical file を検出できること、symlink 置換を検出できることを
   fixture テストで証明する。

**推奨 commit**: `feat(release): make release contract the artifact manifest`

## E-02: ISO 抽出 adapter 整理（P5-02）

**手順**: xorriso 抽出・unsquashfs 抽出・symlink 解決・mode/owner 取得・一時 dir cleanup を
`scripts/` か `tools/` の共通 helper に集約。cleanup trap 先頭設定、path traversal 拒否、
symlinked source 拒否、temporary root 外を削除しない、をテストで検証（bats または pytest）。

**推奨 commit**: `refactor(release): centralize safe ISO extraction helpers`

## E-03: `verify-iso.sh` manifest 駆動化（P5-03 + §1.3）

**手順**:
1. 手書きの required path・個別 `cmp` を release contract の loop に置き換える
   （existence/regular file/symlink 拒否/non-empty/exact content/mode/owner/group/
   package presence/service enable/policy/polkit/NM config/bootloader/local pages）。
2. **checker 追随**: A-02 の `DRIFT_ISO_PATH`（iso-root は verify-iso.sh に文字列がある
   ことの検査）を、「verify-iso.sh が release contract を読む実装になっている」
   （例: `release-contract.json` への参照がある）＋ contract 内の iso-root 定義の自己整合に変更する。
3. contract テスト fixture も追随。

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

**完了条件**: security-critical file が完全照合される。stale ISO を拒否する。
artifact metadata が相互整合する。release contract が正本。再現可能性の保証範囲が明文化される。

---

# 8. Stage F: 文書正本化（Phase 6）

**目的**: コード変更と同時に文書が古くなる問題を防ぎ、エージェント・人間・CI が同じ正本を
参照する構造へ整理する。**変更可能ファイル**: `docs/**`、`AGENTS.md`、`TASKS.md`、
`STRUCTURE.txt`、`README.md`、`.github/`、`Makefile`、`tools/`（生成 script）。

## F-01: 文書正本マップ（P6-01）

**新規**: `docs/documentation-map.md`。上位計画書 P6-01 の表（情報 → 正本 → 参照先）を
現行ファイル名に合わせて作成。

**推奨 commit**: `docs: define documentation sources of truth`

## F-02: `AGENTS.md` 再構成（P6-02）

構成: 1. Safety invariants / 2. Allowed operations / 3. Prohibited operations /
4. Runtime contracts / 5. Test requirements / 6. Artifact requirements /
7. Final report format / 8. Stop conditions。長い実装説明を置かない。
変更してはいけない境界を中心にする。contract と Make target を参照する。
古い file 一覧を手書きで持たない。

**推奨 commit**: `docs(agent): restructure repository safety instructions`

## F-03: `TASKS.md` を管理可能な backlog へ（P6-03）

現行 TASKS.md は実装タスク 1〜20 の旧形式。次の schema の task record へ変換する:
`ID / Status / Severity / Dependency / Scope / Acceptance criteria / Verification /
Manual checks / Out of scope`。status は `BACKLOG/READY/IN_PROGRESS/BLOCKED/REVIEW/DONE/DEFERRED`。
**実装済みと未実装を分離**し、「設計済み」を「完了」と扱わない。実機未確認を明示。
DONE には commit、ISO SHA、確認日を記録できる欄を設ける。

**推奨 commit**: `docs(tasks): convert backlog to explicit task records`

## F-04: `STRUCTURE.txt` の自動生成・検査（P6-04）

**現状（確認済み）**: 現行 STRUCTURE.txt は `contracts/`、`tools/`、`tests/contracts/`、
多数の新規テスト、新規 hooks、Wi-Fi/navigation 系ファイルが **全く掲載されていない**。

**手順**:
1. `git ls-files` から決定的に生成する `tools/gen-structure.py`（新規）を作る。
   除外規則を明示（`build/`、`artifacts/`、`local/`、`__pycache__`、`.venv` 等）。
2. 生成順序を固定（ソート）、build artifact と secret/ignored file を含めない、
   手編集禁止 header を付ける。
3. `make check-structure` を Makefile に追加（生成物と現行の diff で stale なら非ゼロ）。
4. CI（`make ci`）に組み込む。

**推奨 commit**: `feat(docs): generate and verify repository structure index`

## F-05: README の最小化（P6-05）

現行 README は既に最小化に近い（調査済み）。差分確認のみ: プロジェクト目的・セキュリティ注意・
最短開発手順・最短 build 手順・最短 flash 案内・文書リンクが揃っているか確認し、
不足があれば `docs/` へのリンクで補う（README に詳細を新規執筆しない）。

**推奨 commit**: `docs(readme): reduce top-level guide to stable entrypoints`

## F-06: domain 別文書整理（P6-06）

対象: `docs/architecture.md`、`docs/build.md`、`docs/networking.md`、
`docs/wifi-state-machine.md`（新規）、`docs/runtime-routes.md`（新規）、
`docs/release-verification.md`、`docs/threat-model.md`、`docs/acceptance-tests.md`、
`docs/troubleshooting.md`、`docs/reproducible-builds.md`（E-07 成果物）。
**要件**: contract 値を手書きで重複しない（正本を参照する形にする）。diagram と実装名を一致。
最新の Wi-Fi pending 仕様を記載。time-sync、route、QEMU test の違いを説明。

**推奨 commit**: `docs: align architecture guides with runtime contracts`

## F-07: Acceptance test registry（P6-07）

現行 `docs/acceptance-tests.md` は ID 表だが **commit / ISO SHA / 確認日 / 確認者 の列がない**
（確認済み）。各項目に `対象commit / ISO SHA / 環境 / 手順 / 期待結果 / Actual result /
PASS/FAIL / 確認日 / 確認者` を持たせ、分類（automated/QEMU/manual VM/physical hardware/
destructive-manual-approval-required）を付ける。**未実施を PASS にしない。
古い ISO の結果を最新 ISO に流用しない。**

**推奨 commit**: `docs(test): make acceptance evidence versioned and traceable`

## F-08: 変更チェックリスト導入（P6-08）

**新規**: `.github/pull_request_template.md`、`docs/change-checklist.md`。
チェック項目: runtime/release contract 変更、service 追加、package 追加、Chromium policy 変更、
Wi-Fi state 変更、QEMU test 変更、artifact metadata 変更、docs 更新、acceptance test 更新、
secret 検査、privilege 境界。

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

**完了条件（上位計画書 §6 P6-10 そのまま）**:
- 開発入口が Makefile に統一されている。
- runtime/release contract が正本である。
- Wi-Fi backend がモジュール化されている。
- route と signal 処理が共通化されている。
- ISO critical file が完全照合される。
- 文書とコードのドリフトが CI で検出される。
- acceptance evidence が commit と ISO SHA に紐付く。

---

# 9. 最終完了判定（Definition of Done 対応表）

全 Stage 完了後、AGENTS.md §21 / 上位計画書 §10 に従って判定する。
ISO ビルド・QEMU・実機依存の項目は、実行環境がなければ **READY_TO_PROCEED とは言わず**、
`READY_TO_PROCEED_WITH_ADVISORIES` か `PARTIAL` として、未検証項目を明確に列挙して報告する。

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
| 20 | `make test` 成功 | 本 Stage 群で検証 |
| 21 | build/verify/install/acceptance が文書化 | Stage F で検証 |

---

# 付録 A. production 値の所在表（contract → production）

Stage A の adapter が読む場所であり、Stage C/D で移動する値の一覧。

| contract 項目 | production 所在（現行） | Stage C/D での移動先 |
|---|---|---|
| `urls.sushida_url` | `config.env` の `SUSHIDA_URL=` | 移動なし |
| `urls.setup_url` | `sushida-launch` / `sushida-session` の `readonly SETUP_URL=`、wifi `PORT = 8787` | wifi → `sushida_os/wifi/web.py` 等 |
| `urls.offline_url` | `sushida-launch` / `sushida-session` の `readonly OFFLINE_URL=` | 移動なし |
| `runtime_paths.runtime_dir` | launch/netwatch `PROD_RUNTIME`、navwatch `PROD_RUNTIME = Path(...)`、kiosk unit `RuntimeDirectory=` | 移動なし |
| `runtime_paths.active_route_file` / `time_sync_marker` | launch `$BASE_RUNTIME/...`、netwatch `$RUNTIME_DIR/...` | D で state protocol 化 |
| `runtime_paths.wifi_setup_runtime_dir` / `csrf_token_file` | wifi `CSRF_TOKEN_FILE = Path(...)`、wifi unit `RuntimeDirectory=` | C で `wifi/storage.py` 等 |
| `runtime_paths.config_mount_path` | wifi `CONFIG_MOUNT`、config-prepare `CONFIG_MOUNT`、mount unit `Where=` | C で `wifi/storage.py` 等 |
| `runtime_paths.config_storage_status` | wifi `STORAGE_STATUS`、config-prepare `STATUS_DIR`/`STATUS_FILE` | C で `wifi/storage.py` 等 |
| `runtime_paths.credential_file` | wifi `CONFIG_DIR = CONFIG_MOUNT / "network"`、`CONFIG_FILE = CONFIG_DIR / "setup.json"` | C で `wifi/storage.py` 等 |
| `runtime_paths.chromium_profile_dir` / `chromium_sessions_dir` | launch mkdir、session `--user-data-dir`、navwatch `SESSIONS_SUBDIR` | 移動なし |
| `timeouts.network_*` | `config.env` | 移動なし |
| `timeouts.wifi_*` / `restore_*` / `http_*` | wifi `COMMAND_TIMEOUT_SECONDS` 等（activation は `"--wait", "30"` と `timeout=35` が **2サイト**） | C で `wifi/nmcli.py`/`restore.py` 等 |
| `timeouts.nav_*` | navwatch `DEFAULT_POLL_SECONDS`/`DEFAULT_COOLDOWN_SECONDS` | 移動なし |
| `timeouts.session_audio_timeout_seconds` | session `_raw_at=3`（デフォルト行） | 移動なし |
| `routes` | launch `ACTIVE_ROUTE="..."`、netwatch `printf '%s\n' ...` と `case "$route" in ...` | D で `runtime/routes.py` |
| `metadata.static_values` | `scripts/build.sh` の `--arg <field> "<value>"` | 移動なし |

# 付録 B. エラーコード一覧（checker）

| コード | 意味 |
|---|---|
| `MISSING_SOURCE` | 必須 production source 不在 |
| `RUNTIME_URL_MISMATCH` / `DRIFT_URL` | URL の contract↔実装不一致 |
| `DRIFT_PATH` | runtime path 不一致 |
| `DRIFT_TIMEOUT` | timeout リテラル不一致 |
| `DRIFT_ROUTE` | route 集合不一致 |
| `RUNTIME_ALLOWLIST_MISMATCH` / `RUNTIME_BLOCKLIST_MISMATCH` | policy ↔ contract 不一致 |
| `RUNTIME_SERVICE_MISSING` | unit ファイル不在 |
| `RELEASE_ARTIFACT` / `RELEASE_ARTIFACT_REF` | artifact 名の参照不整合 |
| `RELEASE_PACKAGE_MISSING` | package list 欠落 |
| `DRIFT_SERVICE_ENABLE` / `DRIFT_SERVICE_MASK` | hook との不整合 |
| `RELEASE_CHECKSUM` / `RELEASE_PUBLISH` | build.sh との不整合 |
| `DRIFT_METADATA_STATIC` / `DRIFT_METADATA` / `DRIFT_METADATA_FORMAT` / `DRIFT_METADATA_UNSUPPORTED` | metadata 不整合 |
| `RELEASE_MAPPING_SOURCE` / `DRIFT_MAPPING_PATH` / `DRIFT_MAPPING_MODE` / `DRIFT_MAPPING_OWNER` / `DRIFT_COMPARISON` | mapping 不整合 |
| `DRIFT_ISO_PATH` / `DRIFT_ISO_PATH_ATTR` / `DRIFT_PATH_PATTERN` | ISO path 不整合 |
| `SCHEMA_*` | schema validation 系 |
| `FORBIDDEN_KEY` | secret らしきキー |

# 付録 C. 環境構築詳細

```bash
# 1. WSL に入る
wsl.exe -d Ubuntu

# 2. リポジトリへ
cd ~/code/sushida-os-starter

# 3. venv + pytest（ホストでの最小検証用）
python3 -m venv .venv
.venv/bin/pip install pytest
git check-ignore .venv   # IGNORED であること。でなければ .gitignore に追加をユーザーに提案

# 4. podman builder（全検証用。初回は時間がかかる）
make builder CONTAINER_ENGINE=podman

# 5. 動作確認
python3 tools/check-contracts.py
.venv/bin/python -m pytest tests/static/ tests/contracts/ -q
make container-test CONTAINER_ENGINE=podman
```

- `make test-shell` / bats / shellcheck はコンテナ経由（`make container-shell`）でのみ実行可能。
- QEMU 系（`make test-qemu*`）は KVM がある環境でのみ実行。なければ全 Stage で「未実行」と報告。
- ISO ビルド（`make iso`）は `--privileged` が必要なため container-iso 経由のみ。
  実行できない環境では全 Stage で「未実行」と報告し、READY 判定を行わない。

---

**改訂履歴**
- 2026-07-20: 初版。`docs/phase2b2-work-order.md`（Stage A 部分）を統合し、
  実リポジトリ調査に基づく Stage B〜F を追加して一元化。
