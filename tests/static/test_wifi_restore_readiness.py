"""Restore supervisor defers to Wi-Fi adapter readiness (field bug fix).

On real hardware the saved-credential restore thread starts together with
NetworkManager, while the Wi-Fi adapter is still loading firmware or being
taken over ("unmanaged"/"unavailable").  A connect attempt in that window
always fails with an empty scan ("SSID not found") and used to burn all
restore retries, leaving the setup page stuck on a failure message after
every reboot.  These tests pin the deferral gate and the retry budget.
"""

from __future__ import annotations

import pytest

from sushida_os.wifi import coordinator, nmcli, restore, storage
from sushida_os.wifi.types import CONNECT_FAILED, CONNECT_SUCCEEDED


class FakeClock:
    """Deterministic monotonic clock advanced only by sleep()."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture()
def quiet_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coordinator, "restore_cancelled", lambda: False)
    monkeypatch.setattr(coordinator, "interactive_pending", lambda: False)
    monkeypatch.setattr(coordinator, "_reset_failure", lambda: None)
    monkeypatch.setattr(nmcli, "managed_wifi_active", lambda: False)


def test_restore_waits_while_device_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, quiet_coordinator: None
) -> None:
    clock = FakeClock()
    waiting = iter([True, True, True])
    monkeypatch.setattr(
        nmcli, "wifi_device_waiting", lambda: next(waiting, False)
    )
    monkeypatch.setattr(storage, "load_credentials", lambda: ("SSID", "pw123456"))
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        coordinator, "queue_connection",
        lambda ssid, password: queued.append((ssid, password)) or True,
    )
    monkeypatch.setattr(coordinator, "start_queued_connection", lambda: None)
    monkeypatch.setattr(
        coordinator, "connect_status", lambda: (CONNECT_SUCCEEDED, "")
    )

    restore.restore_saved_connection(
        monotonic=clock.monotonic, sleep=clock.sleep
    )

    assert queued == [("SSID", "pw123456")]
    # Three not-ready polls deferred without consuming the single attempt.
    assert clock.sleeps[:3] == [2.0, 2.0, 2.0]


def test_restore_gives_up_at_deadline_when_device_never_readies(
    monkeypatch: pytest.MonkeyPatch, quiet_coordinator: None
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(nmcli, "wifi_device_waiting", lambda: True)
    monkeypatch.setattr(
        storage, "load_credentials",
        lambda: pytest.fail("must not load credentials while deferring"),
    )
    monkeypatch.setattr(
        coordinator, "queue_connection",
        lambda *args: pytest.fail("must not attempt while deferring"),
    )

    restore.restore_saved_connection(
        monotonic=clock.monotonic, sleep=clock.sleep
    )

    # Deferred right up to the fixed 120-second deadline, then stopped.
    assert clock.now >= 120.0
    assert set(clock.sleeps) == {2.0}


def test_restore_retry_budget_is_eight_within_the_deadline(
    monkeypatch: pytest.MonkeyPatch, quiet_coordinator: None
) -> None:
    clock = FakeClock()
    monkeypatch.setattr(nmcli, "wifi_device_waiting", lambda: False)
    monkeypatch.setattr(storage, "load_credentials", lambda: ("SSID", "pw123456"))
    attempts: list[int] = []
    monkeypatch.setattr(
        coordinator, "queue_connection",
        lambda ssid, password: attempts.append(1) or True,
    )
    monkeypatch.setattr(coordinator, "start_queued_connection", lambda: None)
    monkeypatch.setattr(
        coordinator, "connect_status", lambda: (CONNECT_FAILED, "ng")
    )

    restore.restore_saved_connection(
        monotonic=clock.monotonic, sleep=clock.sleep
    )

    assert len(attempts) == 8
    assert clock.now < 120.0


def test_wifi_device_waiting_parses_device_states(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "nmcli"
    assert str(fake).startswith("/tmp"), "pytest tmp_path must be under /tmp"
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_TEST_MODE", "1")
    monkeypatch.setenv("SUSHIDA_WIFI_SETUP_NMCLI", str(fake))

    cases = [
        ("eth0:ethernet:connected\nwlan0:wifi:unavailable\n", 0, True),
        ("wlan0:wifi:unmanaged\n", 0, True),
        ("wlan0:wifi:disconnected\n", 0, False),
        ("wlan0:wifi:connected\n", 0, False),
        ("eth0:ethernet:connected\n", 0, False),  # no Wi-Fi device at all
        ("wlan0:wifi:unavailable\n", 1, False),  # nmcli failure fails open
    ]
    for stdout, code, expected in cases:
        fake.write_text(
            "#!/bin/sh\nprintf '{}'\nexit {}\n".format(
                stdout.replace("\n", "\\n"), code
            )
        )
        fake.chmod(0o755)
        assert nmcli.wifi_device_waiting() is expected, (stdout, code)
