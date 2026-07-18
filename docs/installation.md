# Installation

## Before writing media

Verify the release artifacts in the supported Debian builder:

```bash
make verify
```

The guarded writer supports only USB flash memory of 128 GiB or less. USB SSDs,
internal SATA/NVMe drives, partitions, and raw names such as `/dev/sdb` are not
accepted. Identify the stable whole-device symlink first:

```bash
ls -l /dev/disk/by-id/usb-*
lsblk -o NAME,TYPE,TRAN,RM,HOTPLUG,SIZE,MODEL,SERIAL,MOUNTPOINTS
```

The supplied path must be a `/dev/disk/by-id/usb-*` symlink. The resolved
device must independently report `TYPE=disk`, `TRAN=usb`, `RM=1`, `HOTPLUG=1`,
`ID_BUS=usb` through udev, a non-empty serial number, and a capacity between the
ISO size and 128 GiB. The target and all descendants must be unmounted, absent
from active swap, and unused by device-mapper, LVM, RAID, or other holders.
The detected current system disk is always rejected by the system-disk
protection. Failure to determine any required property is a refusal, not a
warning.

## Guarded write

Run this yourself on a Linux deployment workstation, replacing the example
with the exact USB by-id whole-device symlink shown on your machine:

```bash
sudo ./scripts/flash.sh \
  /dev/disk/by-id/usb-SanDisk_Ultra_4C530001230101234567-0:0
```

The script displays the by-id path, resolved path, model, serial number,
capacity, transport, removable flag, and hot-plug flag. It asks for a
preliminary confirmation and then requires typing `ERASE USB <serial>` exactly.
After confirmation it repeats all device checks and refuses the write if the
resolved path, device major/minor number, or serial changed. Only then does it
run `dd`, call `sync`, and hash the written prefix against the ISO SHA-256.

`--yes` skips only the preliminary question. It does not bypass the serial
confirmation or any safety check. There is deliberately no `--force` escape
hatch. Some legitimate USB media may be rejected because USB bridges expose
`RM=0`, omit a serial, or otherwise lack the required attributes; use another
USB flash drive rather than weakening the checks. If WSL does not expose a
stable `/dev/disk/by-id/usb-*` entry, use a native Debian/Linux deployment
workstation and do not fall back to `/dev/sdX`.

No automated repository test writes a block device. The flash BATS suite uses
only small regular files inside an isolated test directory. Codex must never
run the production writer against a real device.

The ISO includes a small writable `SUSHIDA-CFG` partition for on-device Wi-Fi
credentials. This does not make the live root writable. Shut the kiosk down
normally before removing power when practical so ext4 can unmount cleanly. A
brief unmount warning referring to the read-only live medium or volatile live
overlay may be benign, but a failure naming `/var/lib/sushida-config` or
`SUSHIDA-CFG` must be recorded and investigated before relying on credential
persistence. Never remove the USB device while the machine is running.

## Firmware and physical deployment controls

After installing to the intended media, deployments should:

- set a UEFI administrator password;
- disable external/removable boot after installation;
- prioritize the internal kiosk disk;
- restrict firmware setup access;
- restrict physical access to the storage device and case.

The image cannot protect against an attacker who can remove or replace storage
or reset firmware policy. Secure Boot behavior and final hardware boot remain
manual acceptance checks.
