import subprocess
from pathlib import Path

LOCAL_DIR = Path("local")
GITIGNORE = Path(".gitignore")


def _git_ls_files(path: str = "local/") -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def test_wifi_nmconnection_not_tracked() -> None:
    tracked = _git_ls_files("local/wifi.nmconnection")
    assert "local/wifi.nmconnection" not in tracked


def test_wifi_nmconnection_in_gitignore() -> None:
    content = GITIGNORE.read_text()
    assert "/local/wifi.nmconnection" in content or \
           "local/wifi.nmconnection" in content


def test_only_allowed_tracked_in_local() -> None:
    tracked = _git_ls_files("local/")
    allowed = {
        "local/README.md",
        "local/wifi.nmconnection.example",
        "local/grub-password.example",
    }
    for f in tracked:
        assert f in allowed, f"Unexpected tracked file in local/: {f}"


def test_wifi_example_has_placeholders() -> None:
    content = (LOCAL_DIR / "wifi.nmconnection.example").read_text()
    assert "REPLACE_WITH_WIFI_SSID" in content
    assert "REPLACE_WITH_WIFI_PASSWORD" in content


def test_wifi_example_no_real_ssid() -> None:
    content = (LOCAL_DIR / "wifi.nmconnection.example").read_text()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("ssid="):
            val = line.split("=", 1)[1]
            assert val == "REPLACE_WITH_WIFI_SSID", (
                "Wi-Fi example contains a non-placeholder ssid"
            )


def test_wifi_example_no_real_password() -> None:
    content = (LOCAL_DIR / "wifi.nmconnection.example").read_text()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("psk="):
            val = line.split("=", 1)[1]
            assert val == "REPLACE_WITH_WIFI_PASSWORD", (
                "Wi-Fi example contains a non-placeholder psk"
            )


def test_grub_example_has_placeholder() -> None:
    content = (LOCAL_DIR / "grub-password.example").read_text()
    assert "REPLACE_WITH_GENERATED_HASH" in content


def test_grub_example_no_real_password() -> None:
    content = (LOCAL_DIR / "grub-password.example").read_text()
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("GRUB_PASSWORD_PBKDF2="):
            val = line.split("=", 1)[1]
            assert val == "REPLACE_WITH_GENERATED_HASH", (
                "GRUB example contains a non-placeholder hash"
            )
