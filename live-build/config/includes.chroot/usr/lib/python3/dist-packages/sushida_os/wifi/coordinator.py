"""Connection state coordinator for the Wi-Fi setup backend.

A network interface change aborts any in-flight browser request, including
loopback ones (ERR_NETWORK_CHANGED).  The HTTP response to a connection
request must therefore be completed before NetworkManager is touched.  The
handler queues the credential, replies immediately, and only then wakes a
single worker thread that performs the staged nmcli operations.  The
browser learns the outcome through the read-only /status.json endpoint,
which never contains the SSID or password.

All connection state (current attempt, pending request, latest-wins
pending-interactive credential, restore cancellation) lives inside
``ConnectionCoordinator``; the NetworkManager operation is injected as a
callable so the coordinator never talks to nmcli directly.  The default
module-level instance resolves the connect callable late through the nmcli
module attribute so tests can patch ``nmcli.connect_wifi``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from sushida_os.wifi import nmcli, storage
from sushida_os.wifi.types import (
    CONNECT_FAILED,
    CONNECT_IDLE,
    CONNECT_SUCCEEDED,
    CONNECT_WORKING,
)


class ConnectionCoordinator:
    """Serialize connection attempts and publish their secret-free state."""

    def __init__(self, connect: Callable[[str, str], tuple[bool, str]]) -> None:
        self._connect = connect
        self._state_lock = threading.Lock()
        self._connect_state = CONNECT_IDLE
        self._state_message = ""
        self._pending_request: tuple[str, str] | None = None
        self._pending_interactive: tuple[str, str] | None = None
        self._request_event = threading.Event()
        self._restore_cancelled = threading.Event()

    def connect_status(self) -> tuple[str, str]:
        """Return a snapshot of the public, secret-free connection state."""
        with self._state_lock:
            return self._connect_state, self._state_message

    def _mirror_progress(self) -> None:
        """Publish the content-free in-progress marker (best effort)."""
        with self._state_lock:
            active = self._connect_state == CONNECT_WORKING
        storage.set_connection_marker(active)

    def queue_connection(self, ssid: str, password: str) -> bool:
        """Accept at most one connection request at a time.

        Returns False when an attempt is already pending or running; the
        caller must drop its copy of the credential immediately in that case.
        """
        with self._state_lock:
            if self._connect_state != CONNECT_IDLE:
                return False
            self._connect_state = CONNECT_WORKING
            self._state_message = ""
            self._pending_request = (ssid, password)
        self._mirror_progress()
        return True

    def enqueue_interactive(self, ssid: str, password: str) -> bool:
        """Submit (or queue for later execution) an interactive request.

        Never sets the request event, because the worker must not be woken
        before the HTTP response is written.  The response-order guarantee is
        always enforced by the caller: write the body, flush, *then* call
        start_after_response() which sets the event.

        Returns True when the request could be started immediately (state was
        IDLE).  Returns False when the request was deferred as
        pending-interactive; the worker will pick it up after the current
        attempt finishes.
        """
        self._restore_cancelled.set()
        with self._state_lock:
            if self._connect_state == CONNECT_IDLE:
                self._connect_state = CONNECT_WORKING
                self._state_message = ""
                self._pending_request = (ssid, password)
                self._pending_interactive = None
                started = True
            else:
                self._pending_interactive = (ssid, password)
                started = False
        if started:
            self._mirror_progress()
        return started

    def start_after_response(self) -> None:
        """Wake the worker.  Called only after the HTTP response is written."""
        self._request_event.set()

    def take_pending(self) -> tuple[str, str] | None:
        with self._state_lock:
            pending = self._pending_request
            self._pending_request = None
        return pending

    def publish_result(self, success: bool, message: str) -> None:
        with self._state_lock:
            self._connect_state = CONNECT_SUCCEEDED if success else CONNECT_FAILED
            self._state_message = message
        self._mirror_progress()

    def consume_failure(self) -> str | None:
        """Reset a published failure when the setup form is rendered again."""
        with self._state_lock:
            if self._connect_state != CONNECT_FAILED:
                return None
            message = self._state_message
            self._connect_state = CONNECT_IDLE
            self._state_message = ""
        self._mirror_progress()
        return message

    def reset_succeeded(self) -> None:
        """Forget a stale success once the network is gone again."""
        with self._state_lock:
            if self._connect_state == CONNECT_SUCCEEDED:
                self._connect_state = CONNECT_IDLE
                self._state_message = ""
        self._mirror_progress()

    def reset_failure(self) -> None:
        """Clear a failed attempt so the restore loop may retry."""
        with self._state_lock:
            if self._connect_state == CONNECT_FAILED:
                self._connect_state = CONNECT_IDLE

    def interactive_pending(self) -> bool:
        """Report whether an interactive credential is waiting for the worker."""
        with self._state_lock:
            return self._pending_interactive is not None

    def restore_cancelled(self) -> bool:
        """Report whether an interactive request permanently stopped restore."""
        return self._restore_cancelled.is_set()

    def run_worker(self) -> None:
        """Single serialized worker; the only caller of the nmcli stage chain.

        After each completed attempt the worker checks whether an interactive
        request arrived while a previous restore-attempt was running and, if
        so, processes it immediately instead of waiting for the next event.
        """
        while True:
            # Check for a pending interactive request that arrived during the
            # previous attempt.  The outer lock ensures the state transition
            # and credential handover are atomic.
            with self._state_lock:
                if self._pending_interactive is not None:
                    if self._connect_state in (CONNECT_FAILED, CONNECT_SUCCEEDED):
                        # Consume the stale terminal state left by the previous
                        # attempt so queue_connection will accept the
                        # interactive request below.
                        self._connect_state = CONNECT_IDLE
                        self._state_message = ""
                    if self._connect_state == CONNECT_IDLE:
                        ssid, password = self._pending_interactive
                        self._pending_interactive = None
                        self._connect_state = CONNECT_WORKING
                        self._pending_request = (ssid, password)

            pending = self.take_pending()
            if pending is None:
                self._request_event.wait()
                self._request_event.clear()
                continue
            ssid, password = pending
            try:
                success, message = self._connect(ssid, password)
            except Exception:  # noqa: BLE001 - never leak internals to the page
                nmcli._log_stage("internal", 8, None)
                success = False
                message = "Wi-Fi接続処理で内部エラーが発生しました。もう一度接続してください。"
            finally:
                password = ""
                pending = None
            # Publish the result atomically: if a pending-interactive request
            # arrived during this attempt, hand off directly without exposing
            # the stale terminal state to status pollers.
            with self._state_lock:
                if self._pending_interactive is not None:
                    ssid2, password2 = self._pending_interactive
                    self._pending_interactive = None
                    self._connect_state = CONNECT_WORKING
                    self._state_message = ""
                    self._pending_request = (ssid2, password2)
                    self._request_event.set()
                else:
                    self._connect_state = (
                        CONNECT_SUCCEEDED if success else CONNECT_FAILED
                    )
                    self._state_message = message
            self._mirror_progress()


# The default coordinator resolves connect_wifi through the nmcli module
# attribute at call time, keeping the adapter injectable and patchable.
_coordinator = ConnectionCoordinator(
    connect=lambda ssid, password: nmcli.connect_wifi(ssid, password),
)


def connect_status() -> tuple[str, str]:
    """Return a snapshot of the public, secret-free connection state."""
    return _coordinator.connect_status()


def queue_connection(ssid: str, password: str) -> bool:
    return _coordinator.queue_connection(ssid, password)


def enqueue_interactive(ssid: str, password: str) -> bool:
    return _coordinator.enqueue_interactive(ssid, password)


def start_queued_connection() -> None:
    """Wake the worker.  Called only after the HTTP response is written."""
    _coordinator.start_after_response()


def _take_pending() -> tuple[str, str] | None:
    return _coordinator.take_pending()


def _publish_result(success: bool, message: str) -> None:
    _coordinator.publish_result(success, message)


def consume_failure() -> str | None:
    return _coordinator.consume_failure()


def reset_succeeded() -> None:
    return _coordinator.reset_succeeded()


def _reset_failure() -> None:
    _coordinator.reset_failure()


def interactive_pending() -> bool:
    return _coordinator.interactive_pending()


def restore_cancelled() -> bool:
    return _coordinator.restore_cancelled()


def _connect_worker() -> None:
    _coordinator.run_worker()
