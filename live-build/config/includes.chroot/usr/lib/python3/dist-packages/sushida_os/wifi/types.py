"""Immutable connection types and credential validation for the Wi-Fi setup.

These are plain module-level string constants (immutable by convention) so
the public state strings stay byte-for-byte compatible with the pre-split
backend.  No mutable state lives here.
"""

from __future__ import annotations

CONNECTION_NAME = "sushida-os-wifi"

# ── Asynchronous connection state machine ─────────────────────────────────
CONNECT_IDLE = "idle"
CONNECT_WORKING = "connecting"
CONNECT_SUCCEEDED = "succeeded"
CONNECT_FAILED = "failed"


def _validate_ssid(ssid: str) -> str | None:
    if not ssid or "\ufffd" in ssid or len(ssid.encode("utf-8")) > 32:
        return "SSIDが不正です。"
    if any(ord(char) < 32 or ord(char) == 127 for char in ssid):
        return "制御文字を含むSSIDには対応していません。"


def _validate_password_shape(password: str) -> str | None:
    if "\x00" in password or "\n" in password or "\r" in password:
        return "パスワードに使用できない文字が含まれています。"


def validate_credentials(ssid: str, password: str) -> str | None:
    """Validate fields without trusting the browser's advertised security."""
    ssid_error = _validate_ssid(ssid)
    if ssid_error:
        return ssid_error
    password_error = _validate_password_shape(password)
    if password_error:
        return password_error
    password_bytes = password.encode("utf-8")
    raw_psk = len(password) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in password
    )
    if password and not (8 <= len(password_bytes) <= 63 or raw_psk):
        return "Wi-Fiパスワードは8〜63バイト、または64桁の16進数で入力してください。"
    return None
