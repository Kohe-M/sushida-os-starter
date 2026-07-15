# Installation

## Before writing media

Verify the release artifacts in the supported Debian builder:

```bash
make verify
```

The guarded writer accepts one explicit *whole-disk* block device. Determine
the removable disk with `lsblk`; do not select a partition such as `/dev/sdb1`.
The script rejects symlinks, partitions, mapper devices, mounted targets, a
checksum mismatch, non-root execution, and the detected current system disk.
If the physical system disk cannot be determined, it fails closed.

## Guarded write

Run this yourself on a Linux deployment workstation, replacing the example
with the exact removable whole-disk path:

```bash
sudo ./scripts/flash.sh /dev/sdX
```

The script displays the target model, capacity, and transport, asks for a
preliminary confirmation, and then requires typing `WRITE /dev/sdX` exactly.
`--yes` skips only the preliminary question; it does not bypass the exact final
confirmation, mounted-device rejection, checksum validation, or system-disk
protection. After `dd`, the script calls `sync` and hashes the written prefix to
compare it with the ISO SHA-256.

No automated repository test writes a block device. The flash BATS suite uses
only small regular files inside an isolated test directory. Codex must never
run the production writer against a real device.

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
