"""Static safety boundaries for removable-media writing."""

import os
import stat
from pathlib import Path


FLASH = Path("scripts/flash.sh")


def _text() -> str:
    return FLASH.read_text()


def test_flash_script_is_executable_strict_and_complete() -> None:
    assert FLASH.is_file()
    assert FLASH.stat().st_mode & stat.S_IXUSR
    assert os.access(FLASH, os.X_OK)
    text = _text()
    assert "set -euo pipefail" in text
    assert "TODO" not in text
    assert "eval" not in text


def test_requires_root_explicit_whole_block_device() -> None:
    text = _text()
    assert 'EUID" -eq 0' in text
    assert "an explicit target device is required" in text
    assert '-b "$TARGET"' in text
    assert 'lsblk -ndo TYPE "$TARGET"' in text
    assert "target must be a whole disk" in text


def test_fails_closed_against_system_and_mounted_disks() -> None:
    text = _text()
    assert "findmnt -nro SOURCE /" in text
    assert "lsblk -ndo PKNAME" in text
    assert '"$TARGET" != "$SYSTEM_DISK"' in text
    assert "refusing to overwrite the current system disk" in text
    assert "target or one of its partitions is mounted" in text
    assert "cannot determine the physical system disk" in text


def test_displays_model_capacity_and_requires_exact_final_confirmation() -> None:
    text = _text()
    assert 'lsblk -dn -o MODEL "$TARGET"' in text
    assert 'lsblk -dn -o SIZE "$TARGET"' in text
    assert "Device model" in text
    assert "Capacity" in text
    assert 'required_confirmation="WRITE $TARGET"' in text
    assert "--yes only skips the preliminary" in text


def test_verifies_before_and_after_write_and_syncs() -> None:
    text = _text()
    assert "source image checksum mismatch" in text
    assert 'dd if="$IMAGE" of="$TARGET"' in text
    assert "sync" in text
    assert 'head -c "$image_size" "$TARGET" | sha256sum' in text
    assert "written image verification failed" in text


def test_no_partition_format_bootloader_or_shutdown_commands() -> None:
    text = _text()
    for command in ("mkfs", "parted", "fdisk", "grub-install", "efibootmgr", "reboot", "shutdown"):
        assert command not in text
