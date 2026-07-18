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


def test_requires_root_and_stable_usb_by_id_whole_disk() -> None:
    text = _text()
    assert 'EUID" -eq 0' in text
    assert "an explicit target device is required" in text
    assert "/dev/disk/by-id/usb-*" in text
    assert '-L "$supplied"' in text
    assert '-b "$resolved"' in text
    assert 'lsblk -dnro TYPE "$resolved"' in text
    assert "target must be a whole disk" in text


def test_requires_multiple_independent_usb_properties() -> None:
    text = _text()
    assert 'lsblk -dnro TRAN "$resolved"' in text
    assert 'lsblk -dnro RM "$resolved"' in text
    assert 'lsblk -dnro HOTPLUG "$resolved"' in text
    assert 'udevadm info --query=property --name="$resolved"' in text
    assert '"$transport" = "usb"' in text
    assert '"$id_bus" = "usb"' in text
    assert '"$removable" = "1"' in text
    assert '"$hotplug" = "1"' in text
    assert "USB serial number is unavailable" in text
    assert "128 GiB safety limit" in text
    assert "target is smaller than the ISO" in text


def test_fails_closed_against_system_mounted_swap_and_held_disks() -> None:
    text = _text()
    assert "findmnt -nro SOURCE /" in text
    assert "lsblk -ndo PKNAME" in text
    assert '"$resolved" != "$SYSTEM_DISK"' in text
    assert "refusing to overwrite the current system disk" in text
    assert "target or one of its partitions is mounted" in text
    assert "swapon --show=NAME --noheadings --raw" in text
    assert "target or one of its partitions is active swap" in text
    assert '"/sys/class/block/$base/holders"' in text
    assert "device-mapper, LVM, RAID" in text
    assert "cannot determine the physical system disk" in text


def test_displays_identity_and_requires_exact_serial_confirmation() -> None:
    text = _text()
    assert 'lsblk -dnro MODEL "$resolved"' in text
    assert 'lsblk -bdnro SIZE "$resolved"' in text
    assert "Target by-id" in text
    assert "Resolved path" in text
    assert "Device model" in text
    assert "Serial number" in text
    assert "Capacity" in text
    assert 'required_confirmation="ERASE USB $SERIAL"' in text
    assert "--yes only skips the preliminary" in text


def test_revalidates_identity_immediately_before_verified_write() -> None:
    text = _text()
    assert "source image checksum mismatch" in text
    assert text.count('validate_usb_target "$TARGET') == 2
    assert '"$TARGET" = "$validated_target"' in text
    assert '"$DEVICE_NUMBER" = "$validated_device_number"' in text
    assert '"$SERIAL" = "$validated_serial"' in text
    assert 'dd if="$IMAGE" of="$TARGET_BY_ID"' in text
    assert "sync" in text
    assert 'head -c "$IMAGE_SIZE" "$TARGET_BY_ID" | sha256sum' in text
    assert "written image verification failed" in text


def test_no_partition_format_bootloader_or_shutdown_commands() -> None:
    text = _text()
    for command in ("mkfs", "parted", "fdisk", "grub-install", "efibootmgr", "reboot", "shutdown"):
        assert command not in text
