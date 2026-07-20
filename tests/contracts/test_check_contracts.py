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

    # Custom unit files named per the contract services
    for svc in (
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-navigation-watch.service",
        "sushida-config-prepare.service",
        "sushida-wifi-setup.service",
        "var-lib-sushida\\x2dconfig.mount",
    ):
        (root / f"live-build/config/includes.chroot/etc/systemd/system/{svc}").write_text(
            "[Service]\nExecStart=/bin/true\n[Install]\n"
        )

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
        'iso_sha256="$(sha256sum ...)"\nIS O_ARTIFACT="sushida-os-amd64.iso"\n'
        'SHA256SUMS="SHA256SUMS"\npackage-manifest.txt\nbuild-info.json\n'
    )
    (root / "scripts/flash.sh").write_text(
        'ISO="sushida-os-amd64.iso"\n'
    )
    (root / "scripts/clean.sh").write_text(
        'echo cleaning\n'
    )
    (root / "scripts/verify-iso.sh").write_text(
        'echo verifying\n'
    )
    (root / "scripts/run-qemu.sh").write_text(
        'ISO="sushida-os-amd64.iso"\n'
    )

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

    # Production binaries and scripts referenced by mappings
    for _bin in ("sushida-launch", "sushida-network-watch", "sushida-navigation-watch", "sushida-diagnostics"):
        (root / f"live-build/config/includes.chroot/usr/local/bin/{_bin}").write_text("#!/bin/sh\nexit 0\n")
    for _lib in ("sushida-session", "sushida-config-prepare", "sushida-wifi-setup"):
        (root / f"live-build/config/includes.chroot/usr/local/libexec/{_lib}").write_text("#!/bin/sh\nexit 0\n")

    # Polkit, NM config, offline page referenced by mappings
    (root / "live-build/config/includes.chroot/etc/polkit-1/rules.d/60-sushida-wifi-setup.rules").write_text("// polkit\n")
    (root / "live-build/config/includes.chroot/etc/NetworkManager/conf.d/90-sushida-os.conf").write_text("# NM config\n")
    (root / "live-build/config/includes.chroot/usr/share/sushida-os/offline.html").write_text("<html></html>\n")


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
