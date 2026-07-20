"""In-process validated kiosk restart signal for Python watchers.

Python twin of /usr/local/libexec/sushida-kiosk-signal: sends SIGTERM to
the MainPID of the fixed sushida-kiosk.service only after the exact
validation chain both watchers have always used — active service, numeric
MainPID > 1, same owner UID, and the exact service name inside the
process cgroup.  Callers cannot choose a PID, a signal, or a service
name; only the systemctl binary path and the test-only cgroup override
are injectable, mirroring the navigation watcher's historical test
surface.  URLs, SSIDs, and secrets never enter this module.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
from pathlib import Path

KIOSK_SERVICE = "sushida-kiosk.service"
_STATE_TIMEOUT = 10


def _run_systemctl(
    systemctl: str, *args: str
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [systemctl, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_STATE_TIMEOUT,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def restart_kiosk(systemctl: str, cgroup_override: Path | None) -> bool:
    """Send TERM to the kiosk MainPID only after the same validations as the
    network route watcher: active service, numeric MainPID > 1, same owner,
    and the exact service name inside the process cgroup."""
    active = _run_systemctl(systemctl, "-q", "is-active", KIOSK_SERVICE)
    if active is None or active.returncode != 0:
        return False
    shown = _run_systemctl(
        systemctl, "show", "--property", "MainPID", "--value", KIOSK_SERVICE
    )
    if shown is None or shown.returncode != 0:
        return False
    pid_text = shown.stdout.strip()
    if not pid_text.isdigit():
        return False
    pid = int(pid_text)
    if pid <= 1:
        return False
    try:
        if os.stat(f"/proc/{pid}").st_uid != os.geteuid():
            return False
    except OSError:
        return False
    cgroup_path = cgroup_override or Path(f"/proc/{pid}/cgroup")
    try:
        cgroup = cgroup_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not re.search(r"(^|/)sushida-kiosk\.service($|/)", cgroup, re.MULTILINE):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True
