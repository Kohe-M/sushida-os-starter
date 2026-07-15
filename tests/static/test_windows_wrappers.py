"""Static checks for constrained WSL2 PowerShell wrappers."""

from pathlib import Path


BUILD = Path("scripts/windows/Build-In-WSL.ps1")
QEMU = Path("scripts/windows/Run-Qemu.ps1")


def test_wrappers_are_complete_and_fail_on_errors() -> None:
    for path in (BUILD, QEMU):
        text = path.read_text()
        assert "TODO" not in text
        assert '$ErrorActionPreference = "Stop"' in text
        assert "wsl.exe" in text
        assert "wslpath -a" in text
        assert "$LASTEXITCODE" in text
        assert "single quote" in text


def test_build_wrapper_constrains_engine_and_podman() -> None:
    text = BUILD.read_text()
    assert '[ValidateSet("docker", "podman")]' in text
    assert "--cgroup-manager=cgroupfs" in text
    assert "--privileged" in text
    assert "make iso" in text
    assert "/sushida-os" in text


def test_qemu_wrapper_constrains_firmware_and_supports_offline() -> None:
    text = QEMU.read_text()
    assert '[ValidateSet("bios", "uefi")]' in text
    assert "--firmware" in text
    assert "--offline" in text
    assert "run-qemu.sh" in text
