"""Connection-progress marker lifecycle (backlog BL-02).

The Wi-Fi coordinator publishes a content-free, world-readable marker
while a connection attempt is in flight, from its own dedicated status
directory, so the kiosk-user network watcher can observe progress without
any access to the private Wi-Fi runtime state.  Publication is opt-in for
tests and strictly best-effort: it must never affect the connection flow.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

# sys.path and dont_write_bytecode are prepared suite-wide in conftest.py.


@pytest.fixture()
def wifi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fresh coordinator/storage modules with marker publication opted in."""
    marker = Path("/tmp") / tmp_path.relative_to("/tmp") / "marker" \
        if str(tmp_path).startswith("/tmp") else tmp_path / "marker"
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_CONNECTION_MARKER", str(marker))
    for name in [n for n in sys.modules if n.startswith("sushida_os")]:
        del sys.modules[name]
    storage = importlib.import_module("sushida_os.wifi.storage")
    coordinator = importlib.import_module("sushida_os.wifi.coordinator")
    return storage, coordinator, marker


def test_marker_reflects_attempt_lifecycle(wifi) -> None:
    storage, coordinator, marker = wifi
    assert not marker.exists()
    assert coordinator.queue_connection("SSID", "password123")
    assert marker.exists(), "marker must appear when an attempt starts"
    assert marker.read_bytes() == b"", "marker must stay content-free"
    coordinator._publish_result(True, "ok")
    assert not marker.exists(), "marker must clear on a terminal result"


def test_marker_clears_when_failure_is_consumed(wifi) -> None:
    storage, coordinator, marker = wifi
    assert coordinator.enqueue_interactive("SSID", "password123")
    assert marker.exists()
    coordinator._publish_result(False, "ng")
    assert not marker.exists()
    # Consuming the failure keeps the marker absent (state returns to idle).
    coordinator.consume_failure()
    assert not marker.exists()


def test_marker_failure_never_breaks_the_flow(wifi, monkeypatch) -> None:
    storage, coordinator, marker = wifi

    def broken_marker(_active: bool) -> None:
        raise AssertionError("must not be reached")

    # Point the marker at an unwritable location instead: publication is
    # best-effort and the state machine must proceed regardless.
    monkeypatch.setenv(
        "SUSHIDA_WIFI_SETUP_CONNECTION_MARKER", "/tmp/no-such-dir-x/marker"
    )
    assert coordinator.queue_connection("SSID", "password123")
    state, _ = coordinator.connect_status()
    assert state == "connecting"


def test_marker_disabled_without_test_opt_in(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_TEST_MODE", "1")
    monkeypatch.delenv("SUSHIDA_WIFI_SETUP_CONNECTION_MARKER", raising=False)
    for name in [n for n in sys.modules if n.startswith("sushida_os")]:
        del sys.modules[name]
    storage = importlib.import_module("sushida_os.wifi.storage")
    assert storage.connection_marker_file() is None
    storage.set_connection_marker(True)  # must be a silent no-op


def test_marker_test_path_must_stay_under_tmp(monkeypatch) -> None:
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_CONNECTION_MARKER", "/etc/evil")
    for name in [n for n in sys.modules if n.startswith("sushida_os")]:
        del sys.modules[name]
    storage = importlib.import_module("sushida_os.wifi.storage")
    with pytest.raises(RuntimeError):
        storage.connection_marker_file()
