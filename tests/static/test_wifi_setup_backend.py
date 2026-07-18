"""Behavior tests for the constrained loopback Wi-Fi setup backend."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import socket
import stat
import subprocess
import threading
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

import pytest


BACKEND = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-wifi-setup"
)


def _load_backend():
    loader = importlib.machinery.SourceFileLoader("sushida_wifi_setup", str(BACKEND))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture()
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_backend()
    config_mount = tmp_path / "config"
    config_dir = config_mount / "network"
    status_file = tmp_path / "config-storage"
    csrf_token_file = tmp_path / "csrf-token"
    command_log = tmp_path / "nmcli.log"
    fake_nmcli = tmp_path / "nmcli"
    config_dir.mkdir(parents=True)
    config_dir.chmod(0o700)
    status_file.write_text("ready\n")
    fake_nmcli.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{command_log}'\n"
        "case \" $* \" in\n"
        "  *' -t -f STATE general '*) printf 'disconnected\\n' ;;\n"
        "  *' device wifi list '*) printf 'Cafe\\\\:Guest:91:WPA2\\nOpenNet:40:--\\n' ;;\n"
        "esac\n"
        "exit 0\n"
    )
    fake_nmcli.chmod(0o755)
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_CONFIG_MOUNT", str(config_mount))
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_STORAGE_STATUS", str(status_file))
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_CSRF_TOKEN_FILE", str(csrf_token_file))
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_NMCLI", str(fake_nmcli))
    module._command_log = command_log
    return module


def test_scan_unescapes_deduplicates_and_orders_networks(backend) -> None:
    assert backend.scan_networks() == [
        ("Cafe:Guest", 91, "WPA2"),
        ("OpenNet", 40, "--"),
    ]


def test_scan_skips_undecodable_ssid_bytes(backend) -> None:
    fake_nmcli = Path(backend.nmcli_path())
    fake_nmcli.write_bytes(
        b"#!/bin/sh\nprintf '\\377Bad:80:WPA2\\nGood:70:WPA2\\n'\n"
    )
    fake_nmcli.chmod(0o755)

    assert backend.scan_networks() == [("Good", 70, "WPA2")]


@pytest.mark.parametrize("connection_type", ["wifi", "802-11-wireless"])
def test_managed_wifi_active_matches_only_the_fixed_profile(
    backend, monkeypatch: pytest.MonkeyPatch, connection_type: str,
) -> None:
    monkeypatch.setattr(
        backend,
        "run_nmcli",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args,
            0,
            f"Other:wifi\n{backend.CONNECTION_NAME}:{connection_type}\n",
            "",
        ),
    )

    assert backend.managed_wifi_active()


@pytest.mark.parametrize(
    ("ssid", "password", "valid"),
    [
        ("Home", "correcthorse", True),
        ("Open", "", True),
        ("", "correcthorse", False),
        ("x" * 33, "correcthorse", False),
        ("bad\nssid", "correcthorse", False),
        ("Home", "short", False),
        ("Home", "日" * 8, True),
        ("Home", "日" * 22, False),
        ("Home", "a" * 64, True),
        ("Home", "x" * 64, False),
    ],
)
def test_credential_validation_is_bounded(backend, ssid: str, password: str, valid: bool) -> None:
    assert (backend.validate_credentials(ssid, password) is None) is valid


def test_persistence_is_private_atomic_and_loadable(backend) -> None:
    backend.persist_credentials("Home", "correcthorse")
    path = backend.config_file()
    assert path.is_file() and not path.is_symlink()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert backend.load_credentials() == ("Home", "correcthorse")
    assert not list(backend.config_dir().glob(".setup.*"))


def test_loader_rejects_symlink_and_wrong_mode(backend, tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"version":1,"ssid":"Home","password":"correcthorse"}')
    backend.config_file().symlink_to(outside)
    assert backend.load_credentials() is None
    backend.config_file().unlink()
    backend.config_file().write_text(
        '{"version":1,"ssid":"Home","password":"correcthorse"}'
    )
    backend.config_file().chmod(0o644)
    assert backend.load_credentials() is None


def test_persistent_storage_rejects_unsafe_status_or_directory_mode(backend) -> None:
    backend.storage_status().chmod(0o600)
    assert not backend.persistent_storage_ready()
    backend.storage_status().chmod(0o644)

    backend.config_dir().chmod(0o755)
    assert not backend.persistent_storage_ready()
    backend.config_dir().chmod(0o700)
    assert backend.persistent_storage_ready()


def test_connect_saves_only_after_nmcli_success(backend) -> None:
    success, message = backend.connect_wifi("Home", "correcthorse")
    assert success and "接続" in message
    assert backend.load_credentials() == ("Home", "correcthorse")
    commands = backend._command_log.read_text()
    assert "--ask --wait 30 device wifi connect Home name sushida-os-wifi" in commands
    assert "correcthorse" not in commands


def test_connect_passes_password_only_over_nmcli_stdin(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], str | None]] = []

    def fake_nmcli(
        *args: str, timeout: int = 40, input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        calls.append((args, input_text))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(backend, "run_nmcli", fake_nmcli)
    success, _message = backend.connect_wifi("Home", "correcthorse")

    assert success
    connect_args, connect_input = next(
        (args, input_text)
        for args, input_text in calls
        if "connect" in args
    )
    assert "--ask" in connect_args
    assert "correcthorse" not in connect_args
    assert connect_input == "correcthorse\n"


def test_autoconnect_timeout_after_success_does_not_break_response_or_persistence(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_run_nmcli = backend.run_nmcli

    def timeout_on_modify(
        *args: str, timeout: int = 40, input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ("connection", "modify"):
            raise subprocess.TimeoutExpired(args, timeout)
        return original_run_nmcli(*args, timeout=timeout, input_text=input_text)

    monkeypatch.setattr(backend, "run_nmcli", timeout_on_modify)
    success, message = backend.connect_wifi("Home", "correcthorse")

    assert success
    assert "接続しました" in message
    assert backend.load_credentials() == ("Home", "correcthorse")


def test_connect_operations_are_serialized(backend, monkeypatch: pytest.MonkeyPatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    active = 0
    maximum_active = 0

    def fake_connect(_ssid: str, _password: str) -> tuple[bool, str]:
        nonlocal active, maximum_active
        with state_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        entered.set()
        release.wait(timeout=5)
        with state_lock:
            active -= 1
        return True, "connected"

    monkeypatch.setattr(backend, "_connect_wifi", fake_connect)
    results: list[tuple[bool, str]] = []
    first = threading.Thread(
        target=lambda: results.append(backend.connect_wifi("One", "correcthorse"))
    )
    second = threading.Thread(
        target=lambda: results.append(backend.connect_wifi("Two", "correcthorse"))
    )
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    threading.Event().wait(0.1)
    assert maximum_active == 1
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive() and not second.is_alive()
    assert maximum_active == 1
    assert len(results) == 2


def test_saved_wifi_is_restored_even_when_wired_network_is_connected(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: list[tuple[str, str]] = []
    monkeypatch.setattr(
        backend, "load_credentials", lambda: ("Home", "correcthorse")
    )
    monkeypatch.setattr(backend, "network_connected", lambda: True)
    monkeypatch.setattr(backend, "managed_wifi_active", lambda: False)
    monkeypatch.setattr(
        backend,
        "connect_wifi",
        lambda ssid, password: (restored.append((ssid, password)) or (True, "ok")),
    )

    backend.restore_saved_connection()

    assert restored == [("Home", "correcthorse")]


def test_saved_wifi_restore_skips_an_already_active_managed_profile(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        backend, "load_credentials", lambda: ("Home", "correcthorse")
    )
    monkeypatch.setattr(backend, "managed_wifi_active", lambda: True)
    monkeypatch.setattr(
        backend,
        "connect_wifi",
        lambda _ssid, _password: pytest.fail("active profile must not reconnect"),
    )

    backend.restore_saved_connection()


def test_http_requires_same_origin_and_csrf_and_never_reflects_password(backend) -> None:
    server = backend.HTTPServer((backend.HOST, 0), backend.SetupHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(backend.HOST, server.server_port, timeout=10)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Cafe:Guest" in body
        assert "Content-Security-Policy" in response.headers
        assert '<input type="radio" name="ssid"' in body
        assert "<select" not in body
        assert 'action="/"' in body
        assert 'http-equiv="refresh"' not in body

        connection.request("GET", "/rescan")
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Cafe:Guest" in body

        connection.request("GET", "/rescan?")
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Cafe:Guest" in body

        connection.request("GET", "/rescan?unexpected=1")
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "Cafe:Guest" in body

        connection.request("GET", "/missing")
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        assert response.headers["Location"] == "/"

        payload = urlencode(
            {"csrf": backend.csrf_token(), "ssid": "Home", "password": "correcthorse"}
        )
        connection.request(
            "POST", "/connect", payload,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 403
        assert "ネットワーク設定" in body
        assert "接続要求を確認できませんでした" in body
        assert "Forbidden" not in body

        connection.request(
            "POST", "/connect", payload,
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Host": f"{backend.HOST}:{backend.PORT}",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "接続しました" in body

        connection.request(
            "POST", "/connect", payload,
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://attacker.invalid",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 403
        assert "ネットワーク設定" in body
        assert "correcthorse" not in body

        bad_payload = urlencode({"csrf": "bad", "ssid": "Home", "password": "correcthorse"})
        connection.request(
            "POST", "/connect", bad_payload,
            {"Content-Type": "application/x-www-form-urlencoded", "Origin": backend.ORIGIN},
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 403
        assert "設定画面の有効期限が切れました" in body
        assert "Forbidden" not in body
        assert "correcthorse" not in body

        connection.request(
            "POST", "/connect", payload,
            {"Content-Type": "application/x-www-form-urlencoded", "Origin": backend.ORIGIN},
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "接続しました" in body
        assert "correcthorse" not in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_unavailable_storage_keeps_controls_enabled_and_allows_session_connection(
    backend,
) -> None:
    backend.storage_status().write_text("unavailable\n")
    body = backend.render_page().decode()
    assert "設定保存領域を利用できない" in body
    assert "この起動中だけ接続" in body
    assert " disabled" not in body

    success, message = backend.connect_wifi("Home", "correcthorse")
    assert success
    assert "再起動後には保存されません" in message
    assert not backend.config_file().exists()
    commands = backend._command_log.read_text()
    assert "--ask --wait 30 device wifi connect Home name sushida-os-wifi" in commands
    assert "correcthorse" not in commands


def test_csrf_token_survives_backend_process_restart(backend) -> None:
    first_token = backend.csrf_token()
    token_path = backend.csrf_token_file()
    assert token_path.read_text().strip() == first_token
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600

    restarted_backend = _load_backend()
    assert restarted_backend.csrf_token() == first_token


def test_connected_state_keeps_all_visible_setup_controls_interactive(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend, "network_connected", lambda: True)
    body = backend.render_page().decode()

    assert "有線またはWi-Fiで接続済みです。" in body
    assert "Cafe:Guest" in body
    assert '<fieldset class="networks">' in body
    assert '<input type="radio" name="ssid"' in body
    assert 'name="password" type="password"' in body
    assert '<button type="submit">接続して保存</button>' in body
    assert " disabled" not in body


def test_connected_state_still_accepts_a_wifi_connection_request(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend, "network_connected", lambda: True)
    server = backend.HTTPServer((backend.HOST, 0), backend.SetupHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = urlencode(
            {
                "csrf": backend.csrf_token(),
                "ssid": "Home",
                "password": "correcthorse",
            }
        )
        connection = HTTPConnection(backend.HOST, server.server_port, timeout=10)
        connection.request(
            "POST", "/connect", payload,
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": backend.ORIGIN,
            },
        )
        response = connection.getresponse()
        body = response.read().decode()
        assert response.status == 200
        assert "接続しました" in body
        assert "接続が完了しました。寿司打画面への切り替えを待っています。" in body
        commands = backend._command_log.read_text()
        assert "--ask --wait 30 device wifi connect Home" in commands
        assert "correcthorse" not in commands
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_oversized_http_body_is_rejected_before_read(backend) -> None:
    server = backend.HTTPServer((backend.HOST, 0), backend.SetupHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection(backend.HOST, server.server_port, timeout=10)
        connection.request(
            "POST", "/connect", b"x",
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": str(backend.MAX_REQUEST_BYTES + 1),
                "Origin": backend.ORIGIN,
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 413
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_partial_http_body_times_out_without_blocking_later_requests(
    backend, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend, "REQUEST_READ_TIMEOUT_SECONDS", 0.1)
    server = backend.HTTPServer((backend.HOST, 0), backend.SetupHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.create_connection((backend.HOST, server.server_port), timeout=2) as client:
            client.sendall(
                b"POST /connect HTTP/1.1\r\n"
                + f"Host: {backend.HOST}:{server.server_port}\r\n".encode()
                + f"Origin: {backend.ORIGIN}\r\n".encode()
                + b"Content-Type: application/x-www-form-urlencoded\r\n"
                + b"Content-Length: 100\r\nConnection: close\r\n\r\ncsrf=x"
            )
            response = bytearray()
            while chunk := client.recv(4096):
                response.extend(chunk)
        assert b" 400 " in response
        assert "タイムアウト" in response.decode("utf-8")

        connection = HTTPConnection(backend.HOST, server.server_port, timeout=2)
        connection.request("GET", "/")
        later_response = connection.getresponse()
        later_response.read()
        assert later_response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
