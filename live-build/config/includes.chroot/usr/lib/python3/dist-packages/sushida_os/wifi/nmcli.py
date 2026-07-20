"""NetworkManager command adapter for the Wi-Fi setup backend.

Owns every subprocess call to nmcli: scanning, security classification,
profile create/delete/activation, the staged connect chain, timeout and
error-reason classification.  Passwords never appear in argv; the PSK is
handed over exclusively through an inherited /proc/self/fd descriptor.
Collaborators from other modules are referenced as module attributes
(``storage.persist_credentials``) so tests can patch the defining module.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from contextlib import contextmanager
from collections.abc import Iterator

from sushida_os.wifi import storage
from sushida_os.wifi.types import (
    CONNECTION_NAME,
    _validate_password_shape,
    _validate_ssid,
    validate_credentials,
)

NMCLI = "/usr/bin/nmcli"
COMMAND_TIMEOUT_SECONDS = 40

CONNECT_LOCK = threading.Lock()


def nmcli_path() -> str:
    if os.environ.get("SUSHIDA_WIFI_SETUP_TEST_MODE") == "1":
        value = os.environ.get("SUSHIDA_WIFI_SETUP_NMCLI")
        if not value or not value.startswith("/tmp/"):
            raise RuntimeError("unsafe test nmcli path")
        return value
    return NMCLI


def run_nmcli(
    *args: str,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    pass_fds: tuple[int, ...] = (),
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [nmcli_path(), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        pass_fds=tuple(pass_fds),
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
    )


def network_connected() -> bool:
    try:
        result = run_nmcli("-t", "-f", "STATE,CONNECTIVITY", "general", timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    state, separator, connectivity = result.stdout.strip().partition(":")
    return separator == ":" and state == "connected" and connectivity == "full"


def managed_wifi_active() -> bool:
    """Return true only when this boot already activated our Wi-Fi profile."""
    try:
        result = run_nmcli(
            "-t", "--escape", "yes", "-f", "NAME,TYPE",
            "connection", "show", "--active", timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        fields = _split_escaped(line)
        if len(fields) == 2 and fields[0] == CONNECTION_NAME and fields[1] in (
            "wifi", "802-11-wireless",
        ):
            return True
    return False


def _split_escaped(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line.rstrip("\n"):
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def scan_networks() -> list[tuple[str, int, str]]:
    try:
        result = run_nmcli(
            "-t", "--escape", "yes", "-f", "SSID,SIGNAL,SECURITY",
            "device", "wifi", "list", "--rescan", "yes", timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []

    strongest: dict[str, tuple[int, str]] = {}
    for line in result.stdout.splitlines():
        fields = _split_escaped(line)
        if len(fields) != 3:
            continue
        ssid, raw_signal, security = fields
        if not ssid or "\ufffd" in ssid or len(ssid.encode("utf-8")) > 32:
            continue
        if any(ord(char) < 32 or ord(char) == 127 for char in ssid):
            continue
        try:
            signal = max(0, min(100, int(raw_signal)))
        except ValueError:
            continue
        if ssid not in strongest or signal > strongest[ssid][0]:
            strongest[ssid] = (signal, security)
    return sorted(
        ((ssid, signal, security) for ssid, (signal, security) in strongest.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )


def classify_security(security: str) -> str:
    """Classify only the two Wi-Fi modes this kiosk can provision safely."""
    normalized = " ".join(security.upper().split())
    tokens = set(normalized.split())
    if normalized in ("", "--"):
        return "open"
    if "WEP" in normalized:
        return "wep"
    if (
        "802.1X" in normalized
        or "802-1X" in normalized
        or "EAP" in normalized
        or "ENTERPRISE" in normalized
    ):
        return "enterprise"
    if "OWE" in normalized:
        return "owe"
    # The profile deliberately uses wpa-psk.  A WPA2/WPA3 transition
    # advertisement remains compatible because it contains a WPA2 fallback;
    # SAE-only WPA3 must not be silently downgraded to WPA-PSK.
    if "SAE" in tokens and not tokens.intersection({"WPA", "WPA1", "WPA2"}):
        return "unsupported"
    if tokens.intersection({"WPA", "WPA1", "WPA2"}):
        return "wpa-personal"
    if "WPA3" in tokens:
        return "unsupported"
    return "unsupported"


def connect_wifi(ssid: str, password: str) -> tuple[bool, str]:
    error = _validate_ssid(ssid) or _validate_password_shape(password)
    if error:
        return False, error
    # The saved-credential restore thread and an interactive POST may arrive
    # together during boot.  Serialize delete/create operations for the fixed
    # NetworkManager connection name so they cannot tear down each other's
    # newly-created profile.
    with CONNECT_LOCK:
        return _connect_wifi(ssid, password)


@contextmanager
def _temporary_fd(payload: bytes) -> Iterator[tuple[str, int]]:
    """Expose a 0600 anonymous file only through an inherited proc fd."""
    with tempfile.TemporaryFile(mode="w+b") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        descriptor = stream.fileno()
        yield f"/proc/self/fd/{descriptor}", descriptor


def _log_stage(stage: str, exit_code: int, reason: int | None) -> None:
    # Keep service logs useful for diagnosis while excluding command output,
    # SSIDs, device names, and all credential material.
    # NetworkManager uses reason 0 for an unspecified/no-reason state; keep
    # every emitted reason field numeric without exposing command output.
    numeric_reason = reason if reason is not None else 0
    print(
        f"wifi-setup: stage={stage} nmcli_exit={exit_code} reason={numeric_reason}",
        flush=True,
    )


def _wifi_reason() -> int | None:
    """Read only the numeric reason from the current Wi-Fi device."""
    try:
        devices = run_nmcli(
            "-t", "--escape", "yes", "-f", "DEVICE,TYPE",
            "device", "status", timeout=5,
        )
        if devices.returncode != 0:
            return None
        device_name: str | None = None
        for line in devices.stdout.splitlines():
            fields = _split_escaped(line)
            if len(fields) == 2 and fields[1] in ("wifi", "802-11-wireless"):
                device_name = fields[0]
                break
        if not device_name:
            return None
        details = run_nmcli(
            "-t", "-f", "GENERAL.REASON", "device", "show", device_name,
            timeout=5,
        )
        if details.returncode != 0:
            return None
        for line in details.stdout.splitlines():
            match = re.search(r"GENERAL\.REASON:(\d+)", line)
            if match:
                return int(match.group(1))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return None


def _failure_message(exit_code: int, reason: int | None) -> str:
    if exit_code == 3:
        return "Wi-Fi接続がタイムアウトしました。しばらく待ってから再試行してください。"
    if exit_code == 8:
        return "NetworkManagerが停止しています。管理者に状態を確認してもらってください。"
    if reason in (5, 15, 16, 17):
        return "IPアドレスを取得できませんでした。アクセスポイントのDHCP設定を確認してください。"
    if reason == 7:
        return "接続情報を提供できない内部構成エラーです。もう一度接続を試してください。"
    if reason in (8, 9, 10, 11):
        return "認証に失敗しました。パスワードまたはアクセスポイント設定を確認してください。"
    if reason == 35:
        return "Wi-Fiファームウェアが不足しています。管理者に確認してください。"
    if reason == 53:
        return "SSIDが見つかりません。再スキャンして選び直してください。"
    return "Wi-Fi接続に失敗しました。アクセスポイント設定を確認してください。"


def _run_nmcli_stage(
    stage: str,
    *args: str,
    timeout: int,
    pass_fds: tuple[int, ...] = (),
) -> str | None:
    try:
        result = run_nmcli(*args, timeout=timeout, pass_fds=pass_fds)
    except subprocess.TimeoutExpired:
        _log_stage(stage, 3, None)
        return _failure_message(3, None)
    except OSError:
        _log_stage(stage, 8, None)
        return _failure_message(8, None)
    if result.returncode == 0:
        return None
    reason = _wifi_reason()
    _log_stage(stage, result.returncode, reason)
    return _failure_message(result.returncode, reason)


def _profile_exists() -> bool | None:
    try:
        result = run_nmcli(
            "-t", "--escape", "yes", "-f", "NAME",
            "connection", "show", timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return any(
        _split_escaped(line) == [CONNECTION_NAME]
        for line in result.stdout.splitlines()
    )


def _delete_old_profile() -> str | None:
    try:
        result = run_nmcli(
            "--wait", "5", "connection", "delete", "id", CONNECTION_NAME,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        _log_stage("profile-delete", 3, None)
        return _failure_message(3, None)
    except OSError:
        _log_stage("profile-delete", 8, None)
        return _failure_message(8, None)
    if result.returncode == 0 or _profile_exists() is False:
        return None
    reason = _wifi_reason()
    _log_stage("profile-delete", result.returncode, reason)
    return _failure_message(result.returncode, reason)


def _cleanup_profile() -> None:
    try:
        result = run_nmcli(
            "--wait", "5", "connection", "delete", "id", CONNECTION_NAME,
            timeout=8,
        )
    except subprocess.TimeoutExpired:
        _log_stage("profile-cleanup", 3, None)
        return
    except OSError:
        _log_stage("profile-cleanup", 8, None)
        return
    if result.returncode != 0 and _profile_exists() is not False:
        _log_stage("profile-cleanup", result.returncode, _wifi_reason())


def _verify_autoconnect(security_mode: str) -> str | None:
    fields = ["connection.autoconnect"]
    if security_mode == "wpa-personal":
        fields.append("802-11-wireless-security.psk-flags")
    try:
        result = run_nmcli(
            "-t", "--escape", "yes", "-f", ",".join(fields),
            "connection", "show", "id", CONNECTION_NAME, timeout=8,
        )
    except subprocess.TimeoutExpired:
        _log_stage("autoconnect-check", 3, None)
        return _failure_message(3, None)
    except OSError:
        _log_stage("autoconnect-check", 8, None)
        return _failure_message(8, None)
    if result.returncode != 0:
        reason = _wifi_reason()
        _log_stage("autoconnect-check", result.returncode, reason)
        return _failure_message(result.returncode, reason)
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip()
    if values.get("connection.autoconnect") != "yes":
        _log_stage("autoconnect-check", 0, None)
        return "NetworkManagerの自動再接続を確認できませんでした。もう一度接続してください。"
    if (
        security_mode == "wpa-personal"
        and values.get("802-11-wireless-security.psk-flags") != "0"
    ):
        _log_stage("autoconnect-check", 0, None)
        return "現在の起動中に自動再接続用のWi-Fi秘密情報を保持できませんでした。もう一度接続してください。"
    return None


def _connect_wifi(ssid: str, password: str) -> tuple[bool, str]:
    # Re-scan before changing any NetworkManager state.  The browser submits
    # only an SSID; its security field is never trusted.
    selected = next((item for item in scan_networks() if item[0] == ssid), None)
    if selected is None:
        return False, "指定したSSIDが見つかりません。隠しSSIDや範囲外のSSIDには対応していません。再スキャンして選び直してください。"
    security_mode = classify_security(selected[2])
    unsupported_messages = {
        "wep": "このWi-FiはWEP方式のため対応していません。WPA PersonalまたはオープンSSIDを使用してください。",
        "enterprise": "このWi-Fiは802.1X/Enterprise方式のため対応していません。WPA PersonalまたはオープンSSIDを使用してください。",
        "owe": "このWi-FiはOWE方式のため対応していません。WPA PersonalまたはオープンSSIDを使用してください。",
        "unsupported": "このWi-Fiの暗号方式には対応していません。WPA PersonalまたはオープンSSIDを使用してください。",
    }
    if security_mode in unsupported_messages:
        return False, unsupported_messages[security_mode]
    if security_mode == "open" and password:
        return False, "オープンSSIDではパスワードを空欄にしてください。"
    if security_mode == "wpa-personal":
        if not password:
            return False, "WPA Personalにはパスワードが必要です。"
        password_error = validate_credentials(ssid, password)
        if password_error:
            return False, password_error

    profile_created = False
    failure: str | None = None
    try:
        radio = _run_nmcli_stage("radio-on", "radio", "wifi", "on", timeout=5)
        if radio is not None:
            return False, radio

        deleted = _delete_old_profile()
        if deleted is not None:
            return False, deleted

        # LoadConnections is root-only and asks the NetworkManager daemon to
        # open the path itself, so neither a non-root caller nor /proc/self/fd
        # can safely be used for profile creation.  `connection add` is the
        # Polkit-authorized API; the SSID is not a credential and may be an
        # argument, while the PSK remains exclusively in the passwd-file FD.
        created_result = _run_nmcli_stage(
            "profile-create", "connection", "add", "type", "wifi",
            "ifname", "*", "con-name", CONNECTION_NAME, "ssid", ssid,
            timeout=10,
        )
        if created_result is not None:
            return False, created_result
        profile_created = True

        modify_args = [
            "connection", "modify", CONNECTION_NAME,
            "connection.autoconnect", "yes",
        ]
        if security_mode == "wpa-personal":
            modify_args.extend([
                "802-11-wireless-security.key-mgmt", "wpa-psk",
                # Keep the secret in NetworkManager's current-boot runtime
                # profile so autoconnect can recover after a link flap.  The
                # profile disappears with the read-only live boot; setup.json
                # is the separate, explicitly protected reboot recovery path.
                "802-11-wireless-security.psk-flags", "0",
            ])
        modified = _run_nmcli_stage(
            "profile-configure", *modify_args, timeout=10,
        )
        if modified is not None:
            failure = modified

        if failure is None and security_mode == "wpa-personal":
            with _temporary_fd(
                f"802-11-wireless-security.psk:{password}\n".encode("utf-8")
            ) as (passwd_path, passwd_fd):
                activated = _run_nmcli_stage(
                    "activation", "--wait", "30", "connection", "up",
                    "id", CONNECTION_NAME, "passwd-file", passwd_path,
                    timeout=35, pass_fds=(passwd_fd,),
                )
        elif failure is None:
            activated = _run_nmcli_stage(
                "activation", "--wait", "30", "connection", "up",
                "id", CONNECTION_NAME, timeout=35,
            )
        if failure is None and activated is not None:
            failure = activated

        if failure is None:
            autoconnect = _verify_autoconnect(security_mode)
            if autoconnect is not None:
                failure = autoconnect
    except (OSError, subprocess.TimeoutExpired):
        _log_stage("internal", 3, None)
        failure = "Wi-Fi接続処理がタイムアウトしました。"

    if failure is not None:
        if profile_created:
            _cleanup_profile()
        return False, failure

    if not storage.persistent_storage_ready():
        return True, "接続しました。この接続は再起動後には保存されません。"
    try:
        storage.persist_credentials(ssid, password)
    except OSError:
        return True, "接続しましたが、再起動後に使う設定は保存できませんでした。"
    return True, "接続しました。寿司打画面へ切り替えます。"
