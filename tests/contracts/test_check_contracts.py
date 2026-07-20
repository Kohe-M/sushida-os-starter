"""Fixture tests for tools/check-contracts.py.

Each test creates a minimal repository skeleton, writes the current
contracts and schemas into it, optionally introduces a drift, runs the
checker via subprocess, and verifies the exit code and output.
No production files are modified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).parent.parent.parent / "tools" / "check-contracts.py"
CONTRACTS = Path(__file__).parent.parent.parent / "contracts"

REQUIRED_CONTRACT_FILES = [
    "runtime-contract.json",
    "release-contract.json",
    "schema/runtime-contract.schema.json",
    "schema/release-contract.schema.json",
]


def _skip_if_no_checker() -> None:
    if not CHECKER.is_file():
        pytest.skip("check-contracts.py not found")


def _build_minimal_repo(root: Path) -> None:
    """Populate root with the minimum files needed for a clean check."""
    # Contract files
    for name in REQUIRED_CONTRACT_FILES:
        dst = root / "contracts" / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(CONTRACTS / name), str(dst))

    # Production source files the checker reads
    dirs = [
        "live-build/config/includes.chroot/etc/sushida-os",
        "live-build/config/includes.chroot/etc/chromium/policies/managed",
        "live-build/config/includes.chroot/etc/systemd/system",
        "live-build/config/includes.chroot/usr/local/bin",
        "live-build/config/includes.chroot/usr/local/libexec",
        "live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/wifi",
        "live-build/config/includes.chroot/usr/share/sushida-os",
        "live-build/config/includes.chroot/etc/polkit-1/rules.d",
        "live-build/config/includes.chroot/etc/NetworkManager/conf.d",
        "live-build/config/package-lists",
        "live-build/config/hooks/live",
        "scripts",
    ]
    for d in dirs:
        (root / d).mkdir(parents=True)

    # Minimal config.env matching the contract's sushida_url
    (root / "live-build/config/includes.chroot/etc/sushida-os/config.env").write_text(
        'SUSHIDA_URL=https://sushida.net/play.html\n'
        'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
        'NETWORK_SETUP_GRACE_SECONDS=15\n'
    )

    # Chromium policy matching the contract
    (root / "live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json").write_text(json.dumps({
        "URLAllowlist": ["https://.sushida.net:443", "file:///usr/share/sushida-os/offline.html", "http://127.0.0.1:8787"],
        "URLBlocklist": ["*", "view-source:*", "chrome://*", "chrome-untrusted://*", "devtools://*"],
    }))

    # Custom unit files — individual content for adapter checks
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

    # Enable and validate hooks
    (root / "live-build/config/hooks/live/020-enable-services.hook.chroot").write_text(
        'systemctl enable sushida-kiosk.service\n'
        'systemctl enable sushida-network-watch.service\n'
        'systemctl enable sushida-navigation-watch.service\n'
        'systemctl enable var-lib-sushida\\x2dconfig.mount\n'
        'systemctl enable sushida-config-prepare.service\n'
        'systemctl enable sushida-wifi-setup.service\n'
        'systemctl enable systemd-timesyncd.service\n'
    )
    (root / "live-build/config/hooks/live/090-validate-image.hook.chroot").write_text(
        'systemctl mask getty@.service\n'
        'systemctl mask autovt@.service\n'
        'systemctl mask serial-getty@.service\n'
        'systemctl mask console-getty.service\n'
        'systemctl mask container-getty@.service\n'
        'systemctl mask ctrl-alt-del.target\n'
        'systemctl mask apt-daily.timer\n'
        'systemctl mask apt-daily-upgrade.timer\n'
        'systemctl mask apt-daily.service\n'
        'systemctl mask apt-daily-upgrade.service\n'
    )

    # Minimal scripts
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
    (root / "scripts/flash.sh").write_text('ISO="sushida-os-amd64.iso"\n')
    (root / "scripts/clean.sh").write_text(
        'sushida-os-amd64.iso\nSHA256SUMS\npackage-manifest.txt\nbuild-info.json\n'
    )
    (root / "scripts/verify-iso.sh").write_text(
        'sushida-os-amd64.iso\nSHA256SUMS\npackage-manifest.txt\nbuild-info.json\n'
        '/live/filesystem.squashfs\n/live/vmlinuz\n/live/initrd.img\n'
    )
    (root / "scripts/run-qemu.sh").write_text('ISO="sushida-os-amd64.iso"\n')

# Package list
    pkgs = [
        "linux-image-amd64", "live-boot", "live-config", "systemd-sysv",
        "cage", "chromium", "network-manager", "wpasupplicant",
        "wireless-regdb", "polkitd", "pipewire", "pipewire-pulse",
        "wireplumber", "libspa-0.2-modules", "dbus-user-session",
        "libgl1-mesa-dri", "mesa-va-drivers", "libegl1", "libgles2",
        "libgbm1", "libdrm2", "libwayland-client0", "libwayland-server0",
        "keyboard-configuration", "console-setup", "xkb-data",
        "fonts-noto-cjk",
        "firmware-intel-graphics", "firmware-iwlwifi",
        "firmware-realtek", "firmware-amd-graphics",
        "intel-microcode", "amd64-microcode",
        "ca-certificates", "systemd-timesyncd",
        "python3-minimal", "python3", "pciutils",
    ]
    (root / "live-build/config/package-lists/kiosk.list.chroot").write_text(
        "\n".join(pkgs) + "\n"
    )

    # Production scripts — realistic stubs matching all runtime adapters
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
        'from sushida_os.wifi.web import HOST, PORT, SetupHandler\n'
    )
    (root / "live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/wifi/web.py").write_text(
        'PORT = 8787\n'
        'MAX_REQUEST_BYTES = 8192\n'
        'REQUEST_READ_TIMEOUT_SECONDS = 5\n'
    )
    (root / "live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/wifi/restore.py").write_text(
        '    BACKOFF_MIN = 2.0\n'
        '    BACKOFF_MAX = 16.0\n'
        '    MAX_RETRIES = 5\n'
        '    deadline = monotonic() + 120.0\n'
    )
    (root / "live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py").write_text(
        'COMMAND_TIMEOUT_SECONDS = 40\n'
        '                    "activation", "--wait", "30", "connection", "up",\n'
        '                    "id", CONNECTION_NAME, "passwd-file", passwd_path,\n'
        '                    timeout=35, pass_fds=(passwd_fd,),\n'
        '                "activation", "--wait", "30", "connection", "up",\n'
        '                "id", CONNECTION_NAME, timeout=35,\n'
    )
    (root / "live-build/config/includes.chroot/usr/lib/python3/dist-packages/sushida_os/wifi/storage.py").write_text(
        'from pathlib import Path\n'
        'CONFIG_MOUNT = Path("/var/lib/sushida-config")\n'
        'CONFIG_DIR = CONFIG_MOUNT / "network"\n'
        'CONFIG_FILE = CONFIG_DIR / "setup.json"\n'
        'STORAGE_STATUS = Path("/run/sushida-config/config-storage")\n'
        'CSRF_TOKEN_FILE = Path("/run/sushida-wifi-setup/csrf-token")\n'
    )

    # Polkit, NM config, offline page referenced by mappings
    (root / "live-build/config/includes.chroot/etc/polkit-1/rules.d/60-sushida-wifi-setup.rules").write_text("// polkit\n")
    (root / "live-build/config/includes.chroot/etc/NetworkManager/conf.d/90-sushida-os.conf").write_text("# NM config\n")
    (root / "live-build/config/includes.chroot/usr/share/sushida-os/offline.html").write_text("<html></html>\n")

    # Align fixture file modes with the contract mapping declarations
    rc_data = json.loads((root / "contracts/release-contract.json").read_text())
    for mapping in rc_data["source_image_mappings"]:
        p = root / mapping["source"]
        if p.is_file():
            p.chmod(int(mapping["mode"], 8))


def _run_checker(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), *extra],
        capture_output=True, text=True, timeout=30,
    )


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Path:
    _skip_if_no_checker()
    root = tmp_path / "repo"
    _build_minimal_repo(root)
    return root


@pytest.fixture()
def repo_with_drift(clean_repo: Path) -> Path:
    """Return a repo with SUSHIDA_URL changed."""
    cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
    cfg.write_text('SUSHIDA_URL=https://evil.example/\n')
    return clean_repo


# ── Normal / success ───────────────────────────────────────────────────


class TestCheckContracts:
    """Group related tests for shared fixture setup."""

    def test_clean_repo_exit_0(self, clean_repo: Path) -> None:
        r = _run_checker(clean_repo)
        assert r.returncode == 0, f"checker failed on clean repo:\n{r.stdout}\n{r.stderr}"
        assert "contract_drift=PASS" in r.stdout

    def test_json_output_valid(self, clean_repo: Path) -> None:
        r = _run_checker(clean_repo, "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["ok"] is True
        assert "errors" in data
        assert "warnings" in data

    # ── URL drift ───────────────────────────────────────────────────

    def test_url_drift_exit_1(self, repo_with_drift: Path) -> None:
        r = _run_checker(repo_with_drift)
        assert r.returncode == 1
        assert "DRIFT_URL" in r.stdout or "RUNTIME_URL_MISMATCH" in r.stdout

    # ── Blocklist drift ─────────────────────────────────────────────

    def test_blocklist_drift_exit_1(self, clean_repo: Path) -> None:
        pol = clean_repo / "live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json"
        data = json.loads(pol.read_text())
        data["URLBlocklist"] = ["*"]
        pol.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_BLOCKLIST" in r.stdout or "RUNTIME_BLOCKLIST_MISMATCH" in r.stdout

    # ── Service file missing ────────────────────────────────────────

    def test_missing_service_exit_1(self, clean_repo: Path) -> None:
        svc = clean_repo / "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
        svc.unlink()
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "MISSING_SOURCE" in r.stdout or "RUNTIME_SERVICE_MISSING" in r.stdout

    # ── Package drift ───────────────────────────────────────────────

    def test_missing_package_exit_1(self, clean_repo: Path) -> None:
        pl = clean_repo / "live-build/config/package-lists/kiosk.list.chroot"
        text = pl.read_text().replace("cage\n", "")
        pl.write_text(text)
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_PACKAGE" in r.stdout or "RELEASE_PACKAGE_MISSING" in r.stdout

    # ── Service enable drift ────────────────────────────────────────

    def test_service_enable_drift_exit_1(self, clean_repo: Path) -> None:
        hook = clean_repo / "live-build/config/hooks/live/020-enable-services.hook.chroot"
        text = hook.read_text().replace("sushida-kiosk.service\n", "")
        hook.write_text(text)
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_SERVICE_ENABLE" in r.stdout or "RUNTIME_SERVICE_MISSING" in r.stdout

    # ── Artifact drift ──────────────────────────────────────────────

    def test_artifact_drift_exit_1(self, clean_repo: Path) -> None:
        bs = clean_repo / "scripts/build.sh"
        bs.write_text('echo nothing\n')
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_ARTIFACT" in r.stdout

    # ── Mapping source missing ──────────────────────────────────────

    def test_mapping_source_missing_exit_1(self, clean_repo: Path) -> None:
        src = clean_repo / "live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup"
        src.unlink(missing_ok=True)
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "MISSING_SOURCE" in r.stdout or "RELEASE_MAPPING_SOURCE" in r.stdout

    # ── Unknown contract field ──────────────────────────────────────

    def test_unknown_contract_field_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        data["rogue_field"] = "bad"
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "SCHEMA_UNKNOWN" in r.stdout

    # ── Corrupted JSON ──────────────────────────────────────────────

    def test_corrupted_json_exit_2(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        rc.write_text("{broken}")
        r = _run_checker(clean_repo)
        assert r.returncode == 2
        assert "ERROR" in r.stderr or "invalid JSON" in r.stderr

    def test_corrupted_json_with_json_flag_exit_2(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        rc.write_text("{broken}")
        r = _run_checker(clean_repo, "--json")
        assert r.returncode == 2
        data = json.loads(r.stdout)
        assert data["ok"] is False
        assert any(e["code"] == "PARSE_ERROR" for e in data["errors"])

    # ── JSON determinism ────────────────────────────────────────────

    def test_json_output_deterministic(self, clean_repo: Path) -> None:
        r1 = _run_checker(clean_repo, "--json")
        r2 = _run_checker(clean_repo, "--json")
        assert r1.stdout == r2.stdout, "JSON output is not deterministic"

    # ── Non-destructive ─────────────────────────────────────────────

    def test_checker_does_not_modify_repo(self, clean_repo: Path) -> None:
        # Compute a hash of every file before and after
        hashes_before = {}
        for path in sorted(clean_repo.rglob("*")):
            if path.is_file():
                hashes_before[str(path.relative_to(clean_repo))] = hash(path.read_bytes())
        _run_checker(clean_repo)
        hashes_after = {}
        for path in sorted(clean_repo.rglob("*")):
            if path.is_file():
                hashes_after[str(path.relative_to(clean_repo))] = hash(path.read_bytes())
        assert hashes_before == hashes_after, "checker modified files"

    # ── Missing production source ───────────────────────────────────

    def test_missing_config_env_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.unlink()
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "MISSING_SOURCE" in r.stdout

    def test_timeout_drift_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=9999\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_TIMEOUT" in r.stdout

    def test_verify_script_missing_artifact_exit_1(self, clean_repo: Path) -> None:
        vs = clean_repo / "scripts/verify-iso.sh"
        vs.write_text("echo no artifacts\n")
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_ARTIFACT_REF" in r.stdout

    def test_run_qemu_missing_iso_exit_1(self, clean_repo: Path) -> None:
        rq = clean_repo / "scripts/run-qemu.sh"
        rq.write_text("echo no iso\n")
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_ARTIFACT_REF" in r.stdout

    def test_checksum_missing_exit_1(self, clean_repo: Path) -> None:
        bs = clean_repo / "scripts/build.sh"
        bs.write_text("echo no sha256sum\n")
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_CHECKSUM" in r.stdout or "RELEASE_ARTIFACT" in r.stdout

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

    # ── Runtime timeout adapter drift ──────────────────────────────

    @pytest.mark.parametrize(
        ("rel", "old", "new"),
        [
            ("usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py",
             "COMMAND_TIMEOUT_SECONDS = 40", "COMMAND_TIMEOUT_SECONDS = 41"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py",
             '"--wait", "30"', '"--wait", "25"'),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/nmcli.py",
             "timeout=35", "timeout=36"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/restore.py",
             "BACKOFF_MIN = 2.0", "BACKOFF_MIN = 3.0"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/restore.py",
             "MAX_RETRIES = 5", "MAX_RETRIES = 6"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/restore.py",
             "deadline = monotonic() + 120.0",
             "deadline = monotonic() + 130.0"),
            ("usr/local/bin/sushida-navigation-watch",
             "DEFAULT_POLL_SECONDS = 2.0", "DEFAULT_POLL_SECONDS = 5.0"),
            ("usr/local/bin/sushida-navigation-watch",
             "DEFAULT_COOLDOWN_SECONDS = 30.0", "DEFAULT_COOLDOWN_SECONDS = 31.0"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/web.py",
             "REQUEST_READ_TIMEOUT_SECONDS = 5", "REQUEST_READ_TIMEOUT_SECONDS = 6"),
            ("usr/lib/python3/dist-packages/sushida_os/wifi/web.py",
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
        p = clean_repo / (
            "live-build/config/includes.chroot/usr/lib/python3/dist-packages/"
            "sushida_os/wifi/storage.py"
        )
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

    # ── config.env strict parser — missing / quoted / whitespace ───

    def test_config_env_missing_sushida_url_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_URL" in r.stdout

    def test_config_env_quoted_sushida_url_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL="https://sushida.net/play.html"\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RUNTIME_URL_MISMATCH" in r.stdout or "DRIFT_URL" in r.stdout

    def test_config_env_missing_network_check_interval_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_TIMEOUT" in r.stdout

    def test_config_env_missing_network_setup_grace_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_TIMEOUT" in r.stdout

    def test_config_env_leading_whitespace_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            ' SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_URL" in r.stdout

    # ── Artifact boolean drift: clean/verify false but referenced ───

    def test_verify_false_but_referenced_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        for artifact in data["artifacts"]:
            if artifact.get("verify"):
                artifact["verify"] = False
                break
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_ARTIFACT_REF_UNEXPECTED" in r.stdout

    def test_clean_false_but_referenced_exit_1(self, clean_repo: Path) -> None:
        rc = clean_repo / "contracts/release-contract.json"
        data = json.loads(rc.read_text())
        for artifact in data["artifacts"]:
            if artifact.get("clean"):
                artifact["clean"] = False
                break
        rc.write_text(json.dumps(data))
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "RELEASE_ARTIFACT_REF_UNEXPECTED" in r.stdout

    # ── config.env syntax: unknown key / missing = / duplicate / indented comment

    def test_config_env_unknown_key_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
            'UNKNOWN_KEY=value\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_KEY" in r.stdout

    def test_config_env_missing_equals_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
            'broken-line\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_FORMAT" in r.stdout

    def test_config_env_duplicate_sushida_url_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_DUPLICATE" in r.stdout

    def test_config_env_duplicate_network_interval_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_DUPLICATE" in r.stdout

    def test_config_env_duplicate_network_grace_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_DUPLICATE" in r.stdout

    def test_config_env_indented_comment_exit_1(self, clean_repo: Path) -> None:
        cfg = clean_repo / "live-build/config/includes.chroot/etc/sushida-os/config.env"
        cfg.write_text(
            'SUSHIDA_URL=https://sushida.net/play.html\n'
            'NETWORK_CHECK_INTERVAL_SECONDS=30\n'
            'NETWORK_SETUP_GRACE_SECONDS=15\n'
            ' # not a comment because of leading whitespace\n'
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_FORMAT" in r.stdout

    # ── Secret non-exposure ────────────────────────────────────────

    def test_config_env_error_does_not_expose_line_content(
            self, clean_repo: Path) -> None:
        secret = "SUPER_SECRET_SENTINEL_12345"
        cfg = clean_repo / (
            "live-build/config/includes.chroot/etc/sushida-os/config.env"
        )
        cfg.write_text(
            "SUSHIDA_URL=https://sushida.net/play.html\n"
            "NETWORK_CHECK_INTERVAL_SECONDS=30\n"
            "NETWORK_SETUP_GRACE_SECONDS=15\n"
            f"{secret}\n"
        )
        r = _run_checker(clean_repo)
        assert r.returncode == 1
        assert "DRIFT_CONFIG_FORMAT" in r.stdout
        assert secret not in r.stdout
        assert secret not in r.stderr
        j = _run_checker(clean_repo, "--json")
        assert j.returncode == 1
        assert secret not in j.stdout
