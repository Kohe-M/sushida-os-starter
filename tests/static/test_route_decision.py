"""Table-driven tests for the pure route decision model."""

from __future__ import annotations

import re
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

from sushida_os.runtime import routes  # noqa: E402

LAUNCHER = Path("live-build/config/includes.chroot/usr/local/bin/sushida-launch")


# connectivity × time sync × setup service × force-offline → expected route.
# The table mirrors the historical launcher/network-watcher behavior exactly.
ROUTE_MATRIX = [
    # (force_offline, time_sync_pending, nm_ok, nm_state, nm_connectivity,
    #  setup_active, expected_route, expected_reason)
    (False, False, True, "connected", "full", True, "online", "online-full"),
    (False, False, True, "connected", "full", False, "online", "online-full"),
    (False, False, True, "connected", "limited", True, "setup", "setup-available"),
    (False, False, True, "connected", "local", True, "setup", "setup-available"),
    (False, False, True, "connected", "site", True, "setup", "setup-available"),
    (False, False, True, "connecting", "none", True, "setup", "setup-available"),
    (False, False, True, "disconnected", "none", True, "setup", "setup-available"),
    (False, False, True, "unknown", "unknown", True, "setup", "setup-available"),
    (False, False, True, "disconnected", "none", False, "offline", "offline-fallback"),
    # NetworkManager query failure: fall back to setup when the backend runs.
    (False, False, False, "", "", True, "setup", "setup-available"),
    (False, False, False, "", "", False, "offline", "offline-fallback"),
    # An unsynchronized clock holds the kiosk offline regardless of network.
    (False, True, True, "connected", "full", True, "offline", "time-sync-pending"),
    (False, True, False, "", "", False, "offline", "time-sync-pending"),
    # QEMU force-offline wins over everything.
    (True, False, True, "connected", "full", True, "offline", "force-offline"),
    (True, True, True, "connected", "full", True, "offline", "force-offline"),
    # Unknown/garbled NetworkManager values fail closed away from online.
    (False, False, True, "connected", "", True, "setup", "setup-available"),
    (False, False, True, "", "full", False, "offline", "offline-fallback"),
    (False, False, True, "CONNECTED", "FULL", False, "offline", "offline-fallback"),
]


@pytest.mark.parametrize(
    ("force_offline", "time_sync_pending", "nm_ok", "nm_state",
     "nm_connectivity", "setup_active", "expected_route", "expected_reason"),
    ROUTE_MATRIX,
)
def test_route_matrix(
    force_offline: bool, time_sync_pending: bool, nm_ok: bool, nm_state: str,
    nm_connectivity: str, setup_active: bool,
    expected_route: str, expected_reason: str,
) -> None:
    decision = routes.decide(routes.RouteInputs(
        force_offline=force_offline,
        time_sync_pending=time_sync_pending,
        nm_ok=nm_ok,
        nm_state=nm_state,
        nm_connectivity=nm_connectivity,
        setup_service_active=setup_active,
    ))
    assert decision.route == expected_route
    assert decision.reason == expected_reason


def test_route_is_never_empty_or_unknown() -> None:
    for entry in ROUTE_MATRIX:
        decision = routes.decide(routes.RouteInputs(*entry[:6]))
        assert decision.route in routes.ROUTES
        assert decision.reason in routes.REASONS


def test_default_inputs_fail_closed_to_offline() -> None:
    decision = routes.decide(routes.RouteInputs())
    assert decision.route == "offline"


def test_restart_needed_only_for_known_route_changes() -> None:
    assert routes.restart_needed("online", "setup")
    assert routes.restart_needed("setup", "online")
    assert routes.restart_needed("offline", "online")
    assert not routes.restart_needed("online", "online")
    assert not routes.restart_needed("setup", "setup")
    assert not routes.restart_needed("offline", "offline")
    # Missing or invalid active route fails closed without a signal.
    assert not routes.restart_needed(None, "online")
    assert not routes.restart_needed("", "online")
    assert not routes.restart_needed("ONLINE", "setup")
    assert not routes.restart_needed("time-sync", "online")
    # An unknown desired route must never trigger a restart either.
    assert not routes.restart_needed("online", "")
    assert not routes.restart_needed("online", "broken")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sushida_os.runtime.routes", *args],
        capture_output=True, text=True, timeout=10,
        env={"PYTHONPATH": str(DIST_PACKAGES), "PYTHONDONTWRITEBYTECODE": "1",
             "PATH": "/usr/bin:/bin"},
    )


def test_cli_prints_route_for_fixed_flags() -> None:
    result = _run_cli("--nm-ok", "--nm-state", "connected",
                      "--nm-connectivity", "full")
    assert result.returncode == 0
    assert result.stdout == "online\n"
    result = _run_cli("--setup-active")
    assert result.stdout == "setup\n"
    result = _run_cli()
    assert result.stdout == "offline\n"
    result = _run_cli("--force-offline", "--nm-ok", "--nm-state", "connected",
                      "--nm-connectivity", "full")
    assert result.stdout == "offline\n"
    result = _run_cli("--time-sync-pending", "--nm-ok", "--nm-state",
                      "connected", "--nm-connectivity", "full",
                      "--setup-active")
    assert result.stdout == "offline\n"


def test_cli_rejects_unknown_flags_without_output() -> None:
    for bad in (["--pid", "1"], ["--signal", "KILL"], ["--evil"],
                ["--nm-state"], ["--nm-connectivity"]):
        result = _run_cli(*bad)
        assert result.returncode != 0
        assert result.stdout == ""


def test_launcher_route_page_mapping_matches_model() -> None:
    """The launcher's route→page pairs must mirror the model's route names."""
    text = LAUNCHER.read_text()
    for route in routes.ROUTES:
        assert f'ACTIVE_ROUTE="{route}"' in text
    # Each route is paired with its fixed page kind in the launcher.
    pairs = {
        "online": r'START_URL="\$SUSHIDA_URL"\s*\n\s*ACTIVE_ROUTE="online"',
        "setup": r'START_URL="\$SETUP_URL"\s*\n\s*ACTIVE_ROUTE="setup"',
        "offline": r'START_URL="\$OFFLINE_URL"\s*\n\s*ACTIVE_ROUTE="offline"',
    }
    for route, pattern in pairs.items():
        assert re.search(pattern, text), route


def test_launcher_publishes_runtime_state_protocol() -> None:
    text = LAUNCHER.read_text()
    assert "sushida_os.runtime.runtime_state" in text
    assert '--route "$ACTIVE_ROUTE"' in text
    assert "--time-sync-required" in text
    # BL-01: the state protocol is authoritative; the legacy files are gone
    # (the --time-sync-required CLI flag legitimately remains).
    assert "/active-route" not in text
    assert '"$BASE_RUNTIME/time-sync-required"' not in text
