"""Pure route decision model for the kiosk.

The launcher and the network watcher select between exactly three routes:
``online`` (the HTTPS game), ``setup`` (the loopback Wi-Fi page), and
``offline`` (the packaged local page).  This module holds the single
decision table as a pure function over an explicit input snapshot; callers
gather NetworkManager, service, and clock state themselves and never pass
URLs, SSIDs, or credentials in.  Every unknown or partial input fails
closed to ``offline`` and a route is always returned, never an empty
value.

Shell callers invoke ``python3 -m sushida_os.runtime.routes`` with the
fixed flags parsed by :func:`main`; the process prints the route name only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

ROUTE_ONLINE = "online"
ROUTE_SETUP = "setup"
ROUTE_OFFLINE = "offline"
# time-sync is represented as a reason for the offline route today; it is
# reserved here so a future dedicated route keeps a stable name.
ROUTES = (ROUTE_ONLINE, ROUTE_SETUP, ROUTE_OFFLINE)

REASON_FORCE_OFFLINE = "force-offline"
REASON_TIME_SYNC_PENDING = "time-sync-pending"
REASON_ONLINE_FULL = "online-full"
REASON_SETUP_AVAILABLE = "setup-available"
REASON_OFFLINE_FALLBACK = "offline-fallback"
REASONS = (
    REASON_FORCE_OFFLINE,
    REASON_TIME_SYNC_PENDING,
    REASON_ONLINE_FULL,
    REASON_SETUP_AVAILABLE,
    REASON_OFFLINE_FALLBACK,
)


@dataclass(frozen=True)
class RouteInputs:
    """Snapshot of the observations that determine the desired route.

    ``nm_ok`` is False whenever the NetworkManager query itself failed;
    ``nm_state``/``nm_connectivity`` are only meaningful when it is True.
    ``time_sync_pending`` is True when the launcher marked the clock as
    unusable and it has not been NTP-synchronized yet.
    """

    force_offline: bool = False
    time_sync_pending: bool = False
    nm_ok: bool = False
    nm_state: str = ""
    nm_connectivity: str = ""
    setup_service_active: bool = False


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str


def decide(inputs: RouteInputs) -> RouteDecision:
    """Map an input snapshot to the desired route.

    Mirrors the historical network-watcher decision exactly:
    QEMU force-offline first, then the time-sync hold, then full
    connectivity, then the running setup service, then offline.
    """
    if inputs.force_offline:
        return RouteDecision(ROUTE_OFFLINE, REASON_FORCE_OFFLINE)
    if inputs.time_sync_pending:
        return RouteDecision(ROUTE_OFFLINE, REASON_TIME_SYNC_PENDING)
    if (
        inputs.nm_ok
        and inputs.nm_state == "connected"
        and inputs.nm_connectivity == "full"
    ):
        return RouteDecision(ROUTE_ONLINE, REASON_ONLINE_FULL)
    if inputs.setup_service_active:
        return RouteDecision(ROUTE_SETUP, REASON_SETUP_AVAILABLE)
    return RouteDecision(ROUTE_OFFLINE, REASON_OFFLINE_FALLBACK)


def restart_needed(active_route: str | None, desired_route: str) -> bool:
    """Report whether the kiosk should be signalled for a route change.

    Fails closed: a missing, empty, or unknown active route never triggers
    a restart (matching the watcher's historical read_active_route guard),
    and an unknown desired route is treated as no-change.
    """
    if active_route not in ROUTES:
        return False
    if desired_route not in ROUTES:
        return False
    return active_route != desired_route


def main(argv: list[str]) -> int:
    """Fixed-flag CLI for shell callers; prints the route name only.

    Unknown flags or malformed values exit non-zero without output so the
    shell caller falls back to offline.  No dynamic strings are echoed.
    """
    force_offline = False
    time_sync_pending = False
    nm_ok = False
    nm_state = ""
    nm_connectivity = ""
    setup_active = False
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag == "--force-offline":
            force_offline = True
        elif flag == "--time-sync-pending":
            time_sync_pending = True
        elif flag == "--nm-ok":
            nm_ok = True
        elif flag == "--setup-active":
            setup_active = True
        elif flag == "--nm-state":
            index += 1
            if index >= len(argv):
                return 2
            nm_state = argv[index]
        elif flag == "--nm-connectivity":
            index += 1
            if index >= len(argv):
                return 2
            nm_connectivity = argv[index]
        else:
            return 2
        index += 1
    decision = decide(RouteInputs(
        force_offline=force_offline,
        time_sync_pending=time_sync_pending,
        nm_ok=nm_ok,
        nm_state=nm_state,
        nm_connectivity=nm_connectivity,
        setup_service_active=setup_active,
    ))
    print(decision.route)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
