"""Completeness checks for operator and acceptance documentation."""

from pathlib import Path


README = Path("README.md")
DOCS = Path("docs")
REQUIRED = {
    "architecture.md",
    "threat-model.md",
    "build.md",
    "installation.md",
    "networking.md",
    "maintenance.md",
    "hardware-compatibility.md",
    "acceptance-tests.md",
}


def test_required_documents_exist_without_placeholders() -> None:
    assert REQUIRED <= {path.name for path in DOCS.glob("*.md")}
    for path in [README, *(DOCS / name for name in REQUIRED)]:
        text = path.read_text()
        assert len(text) > 200
        assert "TODO" not in text
        assert "starter layout" not in text


def test_build_documents_all_supported_paths_and_podman_boundary() -> None:
    text = (DOCS / "build.md").read_text()
    for value in (
        "Docker on Linux",
        "Podman on Linux",
        "--cgroup-manager=cgroupfs",
        "Docker Engine inside WSL2",
        "Direct Debian 13 host",
        "--privileged",
        "make iso",
        "make test-qemu",
    ):
        assert value in text


def test_maintenance_documents_update_rollback_diagnostics_and_recovery() -> None:
    text = (DOCS / "maintenance.md").read_text().lower()
    for value in ("update", "rollback", "recovery", "sushida-diagnostics", "volatile"):
        assert value in text


def test_threat_model_has_four_required_classes_and_physical_controls() -> None:
    text = (DOCS / "threat-model.md").read_text()
    for value in (
        "Accidental input",
        "Deliberate kiosk escape",
        "Privilege escalation",
        "Physical attacker",
        "UEFI administrator password",
        "disable external/removable boot",
    ):
        assert value in text


def test_hardware_evidence_has_no_invented_threshold() -> None:
    text = (DOCS / "hardware-compatibility.md").read_text()
    for value in ("Input latency", "Power loss", "WebGL", "Audio", "artifact SHA-256"):
        assert value in text
    assert "does not invent a universal pass threshold" in text


def test_installation_requires_human_confirmation_and_system_disk_protection() -> None:
    text = (DOCS / "installation.md").read_text()
    assert "/dev/disk/by-id/usb-*" in text
    assert "ERASE USB <serial>" in text
    assert "128 GiB" in text
    assert "no `--force`" in text
    assert "does not bypass" in text
    assert "system-disk" in text
    assert "never" in text.lower() and "real device" in text.lower()


def test_acceptance_maps_every_definition_of_done_item() -> None:
    text = (DOCS / "acceptance-tests.md").read_text()
    for number in range(1, 22):
        assert f"| D{number:02d} |" in text
    for evidence in ("Input latency", "GPU/WebGL", "Audio", "Power loss", "Representative hardware"):
        assert evidence in text
