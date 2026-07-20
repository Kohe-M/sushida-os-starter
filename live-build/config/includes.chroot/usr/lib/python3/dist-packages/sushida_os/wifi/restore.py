"""Saved-connection restore supervisor for the Wi-Fi setup backend.

Retries restoration of the persisted credential with bounded backoff while
deferring to interactive requests.  Talks to the connection state machine
only through the coordinator public API, and reaches nmcli/storage through
module attributes so tests can patch the defining module.  The clock and
sleep functions are injectable for tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sushida_os.wifi import coordinator, nmcli, storage
from sushida_os.wifi.types import CONNECT_SUCCEEDED, CONNECT_WORKING


def restore_saved_connection(
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Retry saved credential restoration with bounded backoff.

    Each retry reloads the persisted credential so a replacement written by
    an interactive request is picked up.  A failed attempt resets the
    shared state to IDLE explicitly before the next queue attempt.  When an
    interactive POST succeeds (CONNECT_SUCCEEDED) or sets the cancellation
    event, the restore loop terminates permanently for this boot.
    """
    BACKOFF_MIN = 2.0
    BACKOFF_MAX = 16.0
    MAX_RETRIES = 5
    backoff = BACKOFF_MIN
    retries = 0
    deadline = monotonic() + 120.0

    while monotonic() < deadline and retries < MAX_RETRIES:
        if coordinator.restore_cancelled():
            return
        if nmcli.managed_wifi_active():
            return
        # If an interactive request was submitted while we were in backoff
        # or about to retry, stop immediately — the worker will handle it.
        if coordinator.interactive_pending():
            return
        saved = storage.load_credentials()
        if saved is None:
            return
        # If the shared state was left in FAILED by a previous restore
        # attempt that did not pass through the HTTP handler, clear it so
        # queue_connection will accept the next retry.
        coordinator._reset_failure()
        if not coordinator.queue_connection(*saved):
            # Another request is in flight.  Check the outcome.
            state, _msg = coordinator.connect_status()
            if state == CONNECT_SUCCEEDED:
                return
            sleep(1.0)
            continue
        coordinator.start_queued_connection()
        retries += 1

        # Wait for the worker to complete this attempt.
        while monotonic() < deadline:
            sleep(1.0)
            if coordinator.restore_cancelled():
                return
            if nmcli.managed_wifi_active():
                return
            if coordinator.interactive_pending():
                return
            state, _msg = coordinator.connect_status()
            if state == CONNECT_WORKING:
                continue
            if state == CONNECT_SUCCEEDED:
                return
            # IDLE or FAILED — the attempt concluded.
            break

        sleep(backoff)
        backoff = min(backoff * 1.5, BACKOFF_MAX)
