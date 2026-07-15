param(
    [ValidateSet("docker", "podman")]
    [string]$Engine = "docker"
)

$ErrorActionPreference = "Stop"

$RepoWindows = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$RepoWsl = (& wsl.exe wslpath -a $RepoWindows).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($RepoWsl)) {
    throw "Could not translate the repository path for WSL2."
}
if ($RepoWsl.Contains("'")) {
    throw "Repository paths containing a single quote are not supported."
}

$EngineArgs = ""
if ($Engine -eq "podman") {
    $EngineArgs = "--cgroup-manager=cgroupfs"
}

$Command = @"
set -euo pipefail
cd '$RepoWsl'
$Engine $EngineArgs build -t sushida-os-builder:trixie -f builder/Dockerfile .
$Engine $EngineArgs run --rm --privileged -v '${RepoWsl}:/sushida-os' -w /sushida-os sushida-os-builder:trixie make iso
"@

& wsl.exe bash -lc $Command
if ($LASTEXITCODE -ne 0) {
    throw "WSL2 build failed with exit code $LASTEXITCODE."
}
