param(
    [ValidateSet("bios", "uefi")]
    [string]$Firmware = "bios",
    [switch]$Offline
)

$ErrorActionPreference = "Stop"

$RepoWindows = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoWsl = (& wsl.exe wslpath -a $RepoWindows).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RepoWsl)) {
    throw "Could not translate the repository path for WSL2."
}

$OfflineArg = ""
if ($Offline) {
    $OfflineArg = "--offline"
}
$Command = "set -euo pipefail; cd '$RepoWsl'; ./scripts/run-qemu.sh --firmware '$Firmware' $OfflineArg"

& wsl.exe bash -lc $Command
if ($LASTEXITCODE -ne 0) {
    throw "QEMU failed with exit code $LASTEXITCODE."
}
