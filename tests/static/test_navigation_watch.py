"""Blocked-navigation recovery: strict session parsing and kiosk restart.

The binary fixtures under fixtures/snss were captured from a real Chromium
150 profile inside a throwaway Debian container.  They contain only loopback
and example.com URLs plus container-random session identifiers; no host,
user, or network identifiers are present.  Fixtures are test data only and
are never staged into the production image.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import re
import stat
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Loading the extensionless production helper must not leave an ignored .pyc
# beside files that live-build later stages into the ISO.
sys.dont_write_bytecode = True


WATCHER = Path("live-build/config/includes.chroot/usr/local/bin/sushida-navigation-watch")
UNIT = Path(
    "live-build/config/includes.chroot/etc/systemd/system/sushida-navigation-watch.service"
)
ENABLE_HOOK = Path("live-build/config/hooks/live/020-enable-services.hook.chroot")
VALIDATE_HOOK = Path("live-build/config/hooks/live/090-validate-image.hook.chroot")
SESSION_HELPER = Path("live-build/config/includes.chroot/usr/local/libexec/sushida-session")
FIXTURES = Path(__file__).parent / "fixtures" / "snss"


def _load_watcher():
    loader = importlib.machinery.SourceFileLoader("sushida_navigation_watch", str(WATCHER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture()
def watcher():
    return _load_watcher()


def snss_record(tab_id: bytes, index: int, url: str, trailer: bytes = b"\x00" * 24) -> bytes:
    raw = url.encode("utf-8")
    payload = tab_id + struct.pack("<I", index) + struct.pack("<I", len(raw)) + raw + trailer
    return b"\x06" + struct.pack("<I", len(payload)) + payload


def snss_file(*records: bytes, junk_prefix: bytes = b"\x09\x00\x09fakehdr") -> bytes:
    return b"SNSS" + struct.pack("<i", 3) + junk_prefix + b"".join(records)


def write_sessions(root: Path, files: dict[str, bytes], mtimes: dict[str, float] | None = None) -> Path:
    sessions = root / "chromium" / "Default" / "Sessions"
    sessions.mkdir(parents=True)
    for name, data in files.items():
        (sessions / name).write_bytes(data)
    if mtimes:
        for name, mtime in mtimes.items():
            os.utime(sessions / name, (mtime, mtime))
    return sessions


# ── Parser against real Chromium 150 captures ─────────────────────────────


def test_parser_extracts_current_url_from_real_allowed_capture(watcher) -> None:
    data = (FIXTURES / "allowed-loopback.bin").read_bytes()
    entries = watcher.current_entries(data)
    assert list(entries.values()) == ["http://127.0.0.1:18923/allowed.html"]


def test_parser_extracts_blocked_url_from_real_sametab_capture(watcher) -> None:
    data = (FIXTURES / "blocked-sametab.bin").read_bytes()
    entries = watcher.current_entries(data)
    assert list(entries.values()) == ["https://blocked.example/off-limits"]


def test_parser_separates_tabs_in_real_popup_capture(watcher) -> None:
    data = (FIXTURES / "blocked-popup.bin").read_bytes()
    entries = watcher.current_entries(data)
    assert len(entries) == 2
    urls = sorted(entries.values())
    assert urls == [
        "http://127.0.0.1:18923/page3.html",
        "https://blocked3.example/y",
    ]


def test_parser_extracts_file_url_from_real_capture(watcher) -> None:
    data = (FIXTURES / "allowed-file-url.bin").read_bytes()
    entries = watcher.current_entries(data)
    assert list(entries.values()) == ["file://localhost/usr/share/sushida-os/offline.html"]


def test_parser_uses_last_record_per_tab(watcher) -> None:
    data = snss_file(
        snss_record(b"\x01\x02\x03\x04", 0, "https://sushida.net/play.html"),
        snss_record(b"\x01\x02\x03\x04", 1, "https://sushida.net/other"),
    )
    assert list(watcher.current_entries(data).values()) == ["https://sushida.net/other"]


# ── Parser fail-closed behavior ────────────────────────────────────────────


def test_parser_rejects_garbage(watcher) -> None:
    assert watcher.current_entries(os.urandom(4096)) == {}
    assert watcher.current_entries(b"") == {}
    assert watcher.current_entries(b"SNSS") == {}
    assert watcher.current_entries(b"X" * 100) == {}


def test_parser_rejects_bad_magic_and_version(watcher) -> None:
    good = snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://sushida.net/"))
    assert watcher.current_entries(good) != {}
    assert watcher.current_entries(b"XNSS" + good[4:]) == {}
    assert watcher.current_entries(good[:4] + struct.pack("<i", 0) + good[8:]) == {}


def test_parser_rejects_torn_records(watcher) -> None:
    good = snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://sushida.net/play.html"))
    for cut in range(len(good) - 13, len(good)):
        assert watcher.current_entries(good[:cut]) == {}


def test_parser_rejects_oversized_file(watcher, monkeypatch: pytest.MonkeyPatch) -> None:
    good = snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://sushida.net/"))
    monkeypatch.setattr(watcher, "MAX_SESSION_BYTES", len(good) - 1)
    assert watcher.current_entries(good) == {}


def test_parser_rejects_invalid_url_bytes(watcher) -> None:
    tab = b"\x01\x02\x03\x04"
    raw = b"https://sushida.net/\xff"
    payload = tab + struct.pack("<I", 0) + struct.pack("<I", len(raw)) + raw + b"\x00" * 8
    record = b"\x06" + struct.pack("<I", len(payload)) + payload
    assert watcher.current_entries(snss_file(record)) == {}


def test_parser_ignores_fake_record_inside_payload(watcher) -> None:
    # A 0x06 byte inside a record's trailing payload must not start a
    # phantom record; the real record still parses exactly once.
    tab = b"\x01\x02\x03\x04"
    url = "https://sushida.net/play.html"
    fake = b"\x06" + struct.pack("<I", 13) + b"\x99" * 13
    data = snss_file(snss_record(tab, 0, url, trailer=fake + b"\x00" * 8))
    assert list(watcher.current_entries(data).values()) == [url]


# ── URL classification mirrors the managed policy ─────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://sushida.net", "allowed"),
        ("https://sushida.net/", "allowed"),
        ("https://sushida.net/play.html", "allowed"),
        ("https://sushida.net:443/play.html", "allowed"),
        ("https://sushida.net:8443/", "blocked"),
        ("https://sub.sushida.net/", "blocked"),
        ("https://sushida.net.evil.example/", "blocked"),
        ("https://sushida.net./", "blocked"),
        ("http://sushida.net/", "blocked"),
        # The policy filter ignores userinfo; the watcher mirrors it.
        ("https://user:pass@sushida.net/", "allowed"),
        ("http://127.0.0.1:8787/", "allowed"),
        ("http://127.0.0.1:8787/connect", "allowed"),
        ("http://127.0.0.1:8787/status.json", "allowed"),
        ("http://127.0.0.1:8788/", "blocked"),
        ("http://localhost:8787/", "blocked"),
        ("http://[::1]:8787/", "blocked"),
        ("file://localhost/usr/share/sushida-os/offline.html", "allowed"),
        ("file:///usr/share/sushida-os/offline.html", "allowed"),
        ("file:///usr/share/sushida-os/offline.html.evil", "blocked"),
        ("file:///etc/passwd", "blocked"),
        ("file://evil.example/usr/share/sushida-os/offline.html", "blocked"),
        ("chrome-error://chromewebdata/", "blocked"),
        ("chrome://newtab", "blocked"),
        ("view-source:https://sushida.net/", "blocked"),
        ("javascript:alert(1)", "blocked"),
        ("data:text/html,<p>x</p>", "blocked"),
        ("ftp://sushida.net/", "blocked"),
        ("about:blank", "unknown"),
        ("about:srcdoc", "unknown"),
        ("", "unknown"),
        ("not a url", "unknown"),
        ("https://sushida.net:99999/", "unknown"),
    ],
)
def test_classify_url(watcher, url: str, expected: str) -> None:
    assert watcher.classify_url(url) == expected


def test_classify_url_rejects_oversized(watcher) -> None:
    assert watcher.classify_url("https://sushida.net/" + "a" * 4096) == "unknown"


# ── Directory assessment ──────────────────────────────────────────────────


def test_assess_missing_and_empty_directories(watcher, tmp_path: Path) -> None:
    assert watcher.assess_sessions(tmp_path / "missing") == "unknown"
    sessions = tmp_path / "chromium" / "Default" / "Sessions"
    sessions.mkdir(parents=True)
    assert watcher.assess_sessions(sessions) == "unknown"


def test_assess_allowed_origins(watcher, tmp_path: Path) -> None:
    for url in (
        "https://sushida.net/play.html",
        "http://127.0.0.1:8787/",
        "file://localhost/usr/share/sushida-os/offline.html",
    ):
        sessions = write_sessions(
            tmp_path / url.replace(":", "_").replace("/", "_"),
            {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, url))},
        )
        assert watcher.assess_sessions(sessions) == "allowed", url


def test_assess_blocked_and_chrome_error(watcher, tmp_path: Path) -> None:
    for url in ("https://evil.example/", "chrome-error://chromewebdata/"):
        sessions = write_sessions(
            tmp_path / url.replace(":", "_").replace("/", "_"),
            {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, url))},
        )
        assert watcher.assess_sessions(sessions) == "blocked", url


def test_assess_about_blank_is_unknown(watcher, tmp_path: Path) -> None:
    sessions = write_sessions(
        tmp_path, {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "about:blank"))}
    )
    assert watcher.assess_sessions(sessions) == "unknown"


def test_assess_blocked_tab_wins_over_allowed_tab(watcher, tmp_path: Path) -> None:
    sessions = write_sessions(
        tmp_path,
        {
            "Session_1": snss_file(
                snss_record(b"\x01\x01\x01\x01", 0, "https://sushida.net/play.html"),
                snss_record(b"\x02\x02\x02\x02", 0, "https://evil.example/"),
            )
        },
    )
    assert watcher.assess_sessions(sessions) == "blocked"


def test_assess_uses_newest_file_only(watcher, tmp_path: Path) -> None:
    sessions = write_sessions(
        tmp_path,
        {
            "Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://evil.example/")),
            "Session_2": snss_file(snss_record(b"\x05\x06\x07\x08", 0, "https://sushida.net/")),
        },
        mtimes={"Session_1": 1000.0, "Session_2": 2000.0},
    )
    assert watcher.assess_sessions(sessions) == "allowed"


def test_assess_ignores_symlinks(watcher, tmp_path: Path) -> None:
    sessions = write_sessions(
        tmp_path, {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://evil.example/"))}
    )
    target = sessions / "Session_1"
    link = sessions / "Session_2"
    link.symlink_to(target)
    os.utime(target, (1000.0, 1000.0), follow_symlinks=False)
    os.utime(link, (2000.0, 2000.0), follow_symlinks=False)
    # The symlink (newest) is skipped; the regular file is assessed instead.
    assert watcher.assess_sessions(sessions) == "blocked"
    target.unlink()
    assert watcher.assess_sessions(sessions) == "unknown"


def test_assess_torn_newest_file_is_unknown(watcher, tmp_path: Path) -> None:
    good = snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://evil.example/"))
    sessions = write_sessions(tmp_path, {"Session_1": good[: len(good) - 5]})
    assert watcher.assess_sessions(sessions) == "unknown"


# ── Validated kiosk restart ───────────────────────────────────────────────


@pytest.fixture()
def restart_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    watcher = _load_watcher()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "mainpid").write_text("0\n")
    systemctl = tmp_path / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *' is-active '*) [ ! -f '" + str(state_dir / "inactive") + "' ] || exit 1 ;;\n"
        "  *' show '*) [ ! -f '" + str(state_dir / "show-fail") + "' ] || exit 1; cat '"
        + str(state_dir / "mainpid") + "' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    systemctl.chmod(0o755)
    cgroup = tmp_path / "cgroup"
    cgroup.write_text("0::/system.slice/sushida-kiosk.service\n")
    monkeypatch.setenv("SUSHIDA_OS_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_NAV_WATCH_SYSTEMCTL", str(systemctl))
    monkeypatch.setenv("SUSHIDA_OS_TEST_CGROUP_FILE", str(cgroup))
    config = watcher.load_config()
    return watcher, config, state_dir, cgroup


def _start_fixture_process() -> subprocess.Popen:
    return subprocess.Popen(["/usr/bin/sleep", "30"])


def test_restart_terminates_validated_main_pid(restart_env) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    fixture = _start_fixture_process()
    (state_dir / "mainpid").write_text(f"{fixture.pid}\n")
    try:
        assert watcher.restart_kiosk(config)
        assert fixture.wait(timeout=5) == -15
    finally:
        fixture.kill()


def test_restart_requires_active_service(restart_env) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    fixture = _start_fixture_process()
    (state_dir / "mainpid").write_text(f"{fixture.pid}\n")
    (state_dir / "inactive").write_text("1\n")
    try:
        assert not watcher.restart_kiosk(config)
        assert fixture.poll() is None
    finally:
        fixture.kill()
        fixture.wait()


def test_restart_rejects_bad_main_pid_values(restart_env) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    for value in ("0", "1", "oops", "-5", ""):
        (state_dir / "mainpid").write_text(f"{value}\n")
        assert not watcher.restart_kiosk(config), value


def test_restart_rejects_nonexistent_pid(restart_env) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    (state_dir / "mainpid").write_text("99999999\n")
    assert not watcher.restart_kiosk(config)


def test_restart_rejects_foreign_owner(restart_env, monkeypatch: pytest.MonkeyPatch) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    fixture = _start_fixture_process()
    (state_dir / "mainpid").write_text(f"{fixture.pid}\n")
    monkeypatch.setattr(os, "geteuid", lambda: 99999)
    try:
        assert not watcher.restart_kiosk(config)
        assert fixture.poll() is None
    finally:
        fixture.kill()
        fixture.wait()


def test_restart_requires_exact_cgroup_service(restart_env) -> None:
    watcher, config, state_dir, cgroup = restart_env
    fixture = _start_fixture_process()
    (state_dir / "mainpid").write_text(f"{fixture.pid}\n")
    try:
        for content in (
            "0::/user.slice/unrelated.service\n",
            "0::/system.slice/not-sushida-kiosk.service.extra\n",
        ):
            cgroup.write_text(content)
            assert not watcher.restart_kiosk(config), content
            assert fixture.poll() is None
        cgroup.unlink()
        assert not watcher.restart_kiosk(config)
        assert fixture.poll() is None
    finally:
        fixture.kill()
        fixture.wait()


def test_restart_rejects_systemctl_show_failure(restart_env) -> None:
    watcher, config, state_dir, _cgroup = restart_env
    fixture = _start_fixture_process()
    (state_dir / "mainpid").write_text(f"{fixture.pid}\n")
    (state_dir / "show-fail").write_text("1\n")
    try:
        assert not watcher.restart_kiosk(config)
        assert fixture.poll() is None
    finally:
        fixture.kill()
        fixture.wait()


# ── Main loop behavior ────────────────────────────────────────────────────


@pytest.fixture()
def loop_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    watcher = _load_watcher()
    monkeypatch.setenv("SUSHIDA_OS_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_OS_RUNTIME", str(tmp_path))
    monkeypatch.setenv("SUSHIDA_NAV_WATCH_POLL_SECONDS", "0.05")
    monkeypatch.setenv("SUSHIDA_NAV_WATCH_COOLDOWN_SECONDS", "30")
    monkeypatch.setenv("SUSHIDA_OS_MAX_ITERATIONS", "3")
    calls: list[str] = []
    monkeypatch.setattr(watcher, "restart_kiosk", lambda _config: (calls.append("term") or True))
    return watcher, tmp_path, calls


def test_loop_restarts_once_for_persistent_blocked_page(
    loop_env, capsys: pytest.CaptureFixture[str],
) -> None:
    watcher, tmp_path, calls = loop_env
    write_sessions(
        tmp_path,
        {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://evil.example/off"))},
    )
    assert watcher.main() == 0
    # Cooldown keeps a persistent block page from restarting repeatedly.
    assert calls == ["term"]
    out = capsys.readouterr().out
    assert "stage=blocked-page" in out
    assert "stage=kiosk-term" in out
    assert "evil.example" not in out
    assert "https://" not in out


def test_loop_restarts_again_after_cooldown(
    loop_env, monkeypatch: pytest.MonkeyPatch,
) -> None:
    watcher, tmp_path, calls = loop_env
    monkeypatch.setenv("SUSHIDA_NAV_WATCH_COOLDOWN_SECONDS", "0")
    write_sessions(
        tmp_path,
        {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "https://evil.example/off"))},
    )
    assert watcher.main() == 0
    assert calls == ["term", "term", "term"]


def test_loop_never_restarts_during_normal_gameplay(loop_env) -> None:
    watcher, tmp_path, calls = loop_env
    write_sessions(
        tmp_path,
        {
            "Session_1": snss_file(
                snss_record(b"\x01\x02\x03\x04", 0, "https://sushida.net/play.html"),
                snss_record(b"\x01\x02\x03\x04", 1, "https://sushida.net/play.html?course=1"),
            )
        },
    )
    assert watcher.main() == 0
    assert calls == []


def test_loop_ignores_unknown_state(loop_env) -> None:
    watcher, tmp_path, calls = loop_env
    assert watcher.main() == 0
    assert calls == []
    write_sessions(
        tmp_path, {"Session_1": snss_file(snss_record(b"\x01\x02\x03\x04", 0, "about:blank"))}
    )
    assert watcher.main() == 0
    assert calls == []


def test_loop_ignores_real_allowed_capture(loop_env) -> None:
    watcher, tmp_path, calls = loop_env
    write_sessions(
        tmp_path, {"Session_1": (FIXTURES / "allowed-file-url.bin").read_bytes()}
    )
    assert watcher.main() == 0
    assert calls == []


def test_loop_detects_real_blocked_capture(loop_env) -> None:
    watcher, tmp_path, calls = loop_env
    write_sessions(
        tmp_path, {"Session_1": (FIXTURES / "blocked-sametab.bin").read_bytes()}
    )
    assert watcher.main() == 0
    assert calls == ["term"]


def test_loop_detects_real_blocked_popup_capture(loop_env) -> None:
    watcher, tmp_path, calls = loop_env
    write_sessions(
        tmp_path, {"Session_1": (FIXTURES / "blocked-popup.bin").read_bytes()}
    )
    assert watcher.main() == 0
    assert calls == ["term"]


def test_config_overrides_require_test_mode(watcher, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUSHIDA_OS_TEST_MODE", raising=False)
    for name, value in (
        ("SUSHIDA_OS_RUNTIME", "/tmp/x"),
        ("SUSHIDA_NAV_WATCH_SYSTEMCTL", "/tmp/x"),
        ("SUSHIDA_OS_TEST_CGROUP_FILE", "/tmp/x"),
        ("SUSHIDA_NAV_WATCH_POLL_SECONDS", "1"),
        ("SUSHIDA_NAV_WATCH_COOLDOWN_SECONDS", "1"),
        ("SUSHIDA_OS_MAX_ITERATIONS", "1"),
    ):
        monkeypatch.setenv(name, value)
        with pytest.raises(SystemExit):
            watcher.load_config()
        monkeypatch.delenv(name)


def test_config_rejects_bad_values(watcher, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUSHIDA_OS_TEST_MODE", "1")
    for name, value in (
        ("SUSHIDA_NAV_WATCH_POLL_SECONDS", "0"),
        ("SUSHIDA_NAV_WATCH_POLL_SECONDS", "61"),
        ("SUSHIDA_NAV_WATCH_POLL_SECONDS", "abc"),
        ("SUSHIDA_NAV_WATCH_COOLDOWN_SECONDS", "601"),
        ("SUSHIDA_NAV_WATCH_COOLDOWN_SECONDS", "-1"),
        ("SUSHIDA_OS_MAX_ITERATIONS", "1x"),
        ("SUSHIDA_OS_RUNTIME", "/etc/passwd"),
        ("SUSHIDA_NAV_WATCH_SYSTEMCTL", "systemctl"),
    ):
        monkeypatch.setenv(name, value)
        with pytest.raises(SystemExit):
            watcher.load_config()
        monkeypatch.delenv(name)


# ── Production wiring and boundaries ──────────────────────────────────────


def test_unit_is_hardened_and_supervised() -> None:
    text = UNIT.read_text()
    assert "User=kiosk" in text
    assert "Group=kiosk" in text
    assert "PartOf=sushida-kiosk.service" in text
    assert "After=sushida-kiosk.service" in text
    assert "ExecStart=/usr/local/bin/sushida-navigation-watch" in text
    assert "Restart=always" in text
    assert "RestartSec=5" in text
    assert "StartLimitIntervalSec=0" in text
    assert "NoNewPrivileges=true" in text
    assert "CapabilityBoundingSet=" in text
    assert "AmbientCapabilities=" in text
    assert "ProtectSystem=strict" in text
    assert "ProtectHome=yes" in text
    assert "MemoryDenyWriteExecute=true" in text
    assert "RestrictAddressFamilies=AF_UNIX" in text
    assert "IPAddressAllow" not in text
    assert "ReadWritePaths" not in text
    assert "TimeoutStopSec=5" in text


def test_unit_is_enabled_and_image_validated() -> None:
    assert "systemctl enable sushida-navigation-watch.service" in ENABLE_HOOK.read_text()
    validate = VALIDATE_HOOK.read_text()
    assert "sushida-navigation-watch.service" in validate
    assert "/usr/local/bin/sushida-navigation-watch" in validate


def test_watcher_never_launches_browser_or_uses_debug_channels() -> None:
    text = WATCHER.read_text()
    for forbidden in (
        "--remote-debugging",
        "remote-debugging",
        "SingletonLock",
        "SingletonSocket",
        "SingletonCookie",
        "--kiosk",
        "devtools",
    ):
        assert forbidden not in text
    # The watcher may read the profile directory but never starts a browser:
    # no argv-style reference to a browser binary is permitted.
    assert '["chromium"' not in text
    assert ', "chromium"' not in text
    assert '"chromium" --' not in text
    assert "chromium --" not in text


def test_watcher_has_no_network_access() -> None:
    text = WATCHER.read_text()
    for forbidden in (
        "import socket",
        "import requests",
        "urllib.request",
        "http.client",
        "urlopen",
    ):
        assert forbidden not in text
    assert not re.search(r"\b(curl|wget|ping|dig|nslookup|traceroute|ncat)\b", text)


def test_watcher_only_reads_session_files() -> None:
    text = WATCHER.read_text()
    assert "write_bytes" not in text
    assert 'open("' not in text
    assert "os.replace" not in text
    assert "shutil" not in text
    # Only stage names are logged, never URLs or file contents.
    assert "_log(" in text
    assert "_log(state)" not in text
    assert "_log(url)" not in text


def test_watcher_profile_path_matches_session_helper() -> None:
    helper = SESSION_HELPER.read_text()
    assert '--user-data-dir="${XDG_RUNTIME_DIR%/xdg-runtime}/chromium"' in helper
    text = WATCHER.read_text()
    assert 'Path("chromium") / "Default" / "Sessions"' in text
    assert 'Path("/run/sushida-os")' in text
