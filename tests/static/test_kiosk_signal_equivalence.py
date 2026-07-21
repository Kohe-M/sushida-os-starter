"""Equivalence of the shell and Python kiosk-signal validation chains.

The kiosk restart signal exists twice by design (backlog BL-06): the
executable helper /usr/local/libexec/sushida-kiosk-signal for shell
callers and sushida_os.runtime.kiosk_signal for the navigation watcher.
This table drives both implementations through the same scenarios and
asserts they take the identical signal/refuse decision, so the two copies
of the validation chain (active service, numeric MainPID > 1, live
process, same owner UID, exact cgroup service name) cannot drift apart.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True

DIST_PACKAGES = Path(
    "live-build/config/includes.chroot/usr/lib/python3/dist-packages"
).resolve()
if str(DIST_PACKAGES) not in sys.path:
    sys.path.insert(0, str(DIST_PACKAGES))

from sushida_os.runtime import kiosk_signal  # noqa: E402

HELPER = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-kiosk-signal"
).resolve()

# (name, service_active, show_fail, mainpid_kind, foreign_uid,
#  cgroup_kind, expect_signal)
# mainpid_kind: fixture | zero | one | text | dead
# cgroup_kind: good | wrong | substring | missing
SCENARIOS = [
    ("valid target", True, False, "fixture", False, "good", True),
    ("inactive service", False, False, "fixture", False, "good", False),
    ("systemctl show failure", True, True, "fixture", False, "good", False),
    ("mainpid zero", True, False, "zero", False, "good", False),
    ("mainpid one", True, False, "one", False, "good", False),
    ("mainpid non-numeric", True, False, "text", False, "good", False),
    ("mainpid dead", True, False, "dead", False, "good", False),
    ("foreign owner uid", True, False, "fixture", True, "good", False),
    ("wrong cgroup", True, False, "fixture", False, "wrong", False),
    ("cgroup substring", True, False, "fixture", False, "substring", False),
    ("missing cgroup file", True, False, "fixture", False, "missing", False),
]

CGROUPS = {
    "good": "0::/system.slice/sushida-kiosk.service\n",
    "wrong": "0::/user.slice/unrelated.service\n",
    "substring": "0::/system.slice/not-sushida-kiosk.service.extra\n",
}


def _write_systemctl(tmp_path: Path, state_dir: Path) -> Path:
    script = tmp_path / "systemctl"
    script.write_text(
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *' is-active '*) [ ! -f '" + str(state_dir / "inactive") + "' ] || exit 1 ;;\n"
        "  *' show '*) [ ! -f '" + str(state_dir / "show-fail") + "' ] || exit 1; cat '"
        + str(state_dir / "mainpid") + "' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
        "exit 0\n"
    )
    script.chmod(0o755)
    return script


def _resolve_mainpid(kind: str, fixture: subprocess.Popen) -> str:
    return {
        "fixture": str(fixture.pid),
        "zero": "0",
        "one": "1",
        "text": "oops",
        "dead": "99999999",
    }[kind]


@pytest.mark.parametrize(
    ("name", "active", "show_fail", "mainpid_kind", "foreign_uid",
     "cgroup_kind", "expect_signal"),
    SCENARIOS,
    ids=[scenario[0] for scenario in SCENARIOS],
)
def test_shell_and_python_signal_decisions_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    name: str, active: bool, show_fail: bool, mainpid_kind: str,
    foreign_uid: bool, cgroup_kind: str, expect_signal: bool,
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    if not active:
        (state_dir / "inactive").write_text("1\n")
    if show_fail:
        (state_dir / "show-fail").write_text("1\n")
    systemctl = _write_systemctl(tmp_path, state_dir)
    cgroup = tmp_path / "cgroup"
    if cgroup_kind != "missing":
        cgroup.write_text(CGROUPS[cgroup_kind])

    # ── Python twin (in-process; foreign uid via patched geteuid) ────
    py_fixture = subprocess.Popen(["/usr/bin/sleep", "30"])
    try:
        (state_dir / "mainpid").write_text(
            _resolve_mainpid(mainpid_kind, py_fixture) + "\n"
        )
        if foreign_uid:
            monkeypatch.setattr(os, "geteuid", lambda: 99999)
        py_signalled = kiosk_signal.restart_kiosk(
            systemctl=str(systemctl),
            cgroup_override=cgroup,
        )
        monkeypatch.undo()
        py_terminated = py_fixture.wait(timeout=5) == -15 if py_signalled else (
            py_fixture.poll() is None
        )
        assert py_terminated, f"python fixture state inconsistent: {name}"
    finally:
        py_fixture.kill()
        py_fixture.wait()

    # ── Shell helper (subprocess; foreign uid via stat shim) ─────────
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "systemctl").write_text(
        '#!/bin/sh\nexec "' + str(systemctl) + '" "$@"\n'
    )
    (fake_bin / "systemctl").chmod(0o755)
    stat_shim = fake_bin / "stat"
    stat_shim.write_text(
        "#!/bin/sh\n"
        'if [ -n "${STAT_UID:-}" ]; then echo "$STAT_UID"; else exec /usr/bin/stat "$@"; fi\n'
    )
    stat_shim.chmod(0o755)

    sh_fixture = subprocess.Popen(["/usr/bin/sleep", "30"])
    try:
        (state_dir / "mainpid").write_text(
            _resolve_mainpid(mainpid_kind, sh_fixture) + "\n"
        )
        env = dict(os.environ)
        env.update({
            "PATH": f"{fake_bin}:{env['PATH']}",
            "SUSHIDA_OS_TEST_MODE": "1",
            "SUSHIDA_OS_TEST_CGROUP_FILE": str(cgroup),
        })
        if foreign_uid:
            env["STAT_UID"] = "99999"
        result = subprocess.run(
            [str(HELPER), "--reason", "route-mismatch"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        sh_signalled = result.returncode == 0 and "action=term" in result.stdout
        sh_terminated = sh_fixture.wait(timeout=5) == -15 if sh_signalled else (
            sh_fixture.poll() is None
        )
        assert sh_terminated, f"shell fixture state inconsistent: {name}"
    finally:
        sh_fixture.kill()
        sh_fixture.wait()

    # ── The decisions must be identical, and match the expectation ───
    assert py_signalled == sh_signalled == expect_signal, (
        f"{name}: python={py_signalled} shell={sh_signalled} "
        f"expected={expect_signal}"
    )
