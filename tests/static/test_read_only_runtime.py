"""Static coverage for the volatile Debian live runtime design."""

from pathlib import Path


AUTO_CONFIG = Path("live-build/auto/config")
PACKAGE_LIST = Path("live-build/config/package-lists/kiosk.list.chroot")
TMPFILES = Path(
    "live-build/config/includes.chroot/usr/lib/tmpfiles.d/sushida-os.conf"
)
JOURNAL = Path(
    "live-build/config/includes.chroot/etc/systemd/journald.conf.d/90-sushida-os.conf"
)
LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
KIOSK_UNIT = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-kiosk.service"
)
ARCHITECTURE = Path("docs/architecture.md")


def _tmpfile_entries() -> dict[str, list[str]]:
    entries: dict[str, list[str]] = {}
    for line in TMPFILES.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        entries[fields[1]] = fields
    return entries


def test_live_boot_present_without_persistence_package() -> None:
    packages = {
        line.strip() for line in PACKAGE_LIST.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "live-boot" in packages
    assert not any("persistence" in package for package in packages)


def test_build_does_not_enable_persistence() -> None:
    text = AUTO_CONFIG.read_text().lower()
    assert "--bootappend-live" not in text or "persistence" not in text
    assert "persistence.conf" not in text


def test_all_mutable_kiosk_paths_are_volatile() -> None:
    entries = _tmpfile_entries()
    expected = {
        "/run/sushida-os": "0750",
        "/run/sushida-os/home": "0700",
        "/run/sushida-os/chromium": "0700",
        "/run/sushida-os/cache": "0700",
        "/run/sushida-os/tmp": "0700",
        "/run/sushida-os/downloads": "0700",
        "/run/sushida-os/xdg-runtime": "0700",
        # Content-free Wi-Fi progress marker dir (BL-02): world-readable by
        # design, owned by wifi-setup, still volatile tmpfs state.
        "/run/sushida-wifi-status": "0755",
    }
    assert set(entries) == set(expected)
    for path, mode in expected.items():
        fields = entries[path]
        assert fields[0] == "d"
        assert fields[2] == mode
        if path == "/run/sushida-wifi-status":
            assert fields[3:5] == ["wifi-setup", "wifi-setup"]
        else:
            assert fields[3:5] == ["kiosk", "kiosk"]


def test_journal_is_volatile_and_bounded() -> None:
    text = JOURNAL.read_text()
    assert "[Journal]" in text
    assert "Storage=volatile" in text
    assert "RuntimeMaxUse=" in text
    assert "ForwardToConsole=no" in text
    assert "Storage=persistent" not in text


def test_launcher_routes_mutable_state_under_run() -> None:
    text = LAUNCHER.read_text()
    assert 'PROD_RUNTIME="/run/sushida-os"' in text
    for variable in ("HOME", "XDG_RUNTIME_DIR", "XDG_CACHE_HOME", "TMPDIR"):
        assert f"export {variable}=" in text
    for name in ("chromium", "cache", "tmp", "downloads", "xdg-runtime"):
        assert name in text


def test_kiosk_service_uses_runtime_directory() -> None:
    text = KIOSK_UNIT.read_text()
    assert "RuntimeDirectory=sushida-os" in text
    assert "RuntimeDirectoryMode=0750" in text


def test_no_persistent_kiosk_home() -> None:
    text = ARCHITECTURE.read_text()
    assert "/run/sushida-os/home" in text
    assert "No persistent browser profile or kiosk home" in text


def test_architecture_explains_live_overlay_boundary() -> None:
    text = ARCHITECTURE.read_text()
    for phrase in (
        "immutable SquashFS",
        "volatile overlay",
        "discarded at shutdown or reboot",
        "not a claim",
        "Storage=volatile",
        "/run/sushida-os/active-route",
    ):
        assert phrase in text
