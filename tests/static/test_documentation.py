"""Completeness and drift checks for operator and acceptance documentation."""

import json
import re
import subprocess
import sys
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
    "wifi-state-machine.md",
    "runtime-routes.md",
    "reproducible-builds.md",
    "documentation-map.md",
    "change-checklist.md",
    "contract-inventory.md",
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
        "make test-qemu-powerdown",
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


def test_contract_allows_only_constrained_wifi_provisioning() -> None:
    contract = Path("AGENTS.md").read_text()
    tasks = Path("TASKS.md").read_text()
    local = Path("local/README.md").read_text()
    for text in (contract, tasks, local):
        assert "loopback" in text.lower()
        assert "general" in text.lower()
    assert "general-purpose Wi-Fi settings GUI" in contract
    assert "general Wi-Fi settings GUI" in tasks
    assert "not a general NetworkManager settings GUI" in local


def test_acceptance_maps_every_definition_of_done_item() -> None:
    text = (DOCS / "acceptance-tests.md").read_text()
    for number in range(1, 23):
        assert f"| D{number:02d} |" in text
    for evidence in ("Input latency", "GPU/WebGL", "Audio", "Power loss", "Representative hardware"):
        assert evidence in text


# ── Documentation ↔ code drift (Stage F-09) ────────────────────────────


def test_readme_mentions_only_real_make_targets() -> None:
    """Every `make <target>` the README shows must exist in the Makefile."""
    phony_line = next(
        line for line in Path("Makefile").read_text().splitlines()
        if line.startswith(".PHONY:")
    )
    targets = set(phony_line.split()[1:])
    mentioned = set(re.findall(r"\bmake ([a-z][a-z0-9-]*)\b", README.read_text()))
    unknown = mentioned - targets
    assert not unknown, f"README mentions nonexistent make targets: {sorted(unknown)}"


def test_docs_service_names_match_runtime_contract() -> None:
    """sushida-* unit names in docs must exist in the runtime contract."""
    contract = json.loads(Path("contracts/runtime-contract.json").read_text())
    known_units = set(contract.get("services", {}).values())
    for path in sorted(DOCS.glob("*.md")) + [README, Path("AGENTS.md")]:
        for unit in set(re.findall(r"\bsushida-[a-z-]+\.service\b", path.read_text())):
            assert unit in known_units, f"{path}: unknown service {unit}"


def test_readme_artifact_names_match_release_contract() -> None:
    contract = json.loads(Path("contracts/release-contract.json").read_text())
    names = {artifact["name"] for artifact in contract["artifacts"]}
    text = README.read_text()
    for name in names:
        assert name in text, f"README missing artifact {name}"


def test_structure_index_is_fresh() -> None:
    result = subprocess.run(
        [sys.executable, "tools/gen-structure.py", "--check"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_tasks_done_rows_carry_evidence() -> None:
    text = Path("TASKS.md").read_text()
    for line in text.splitlines():
        if re.match(r"^\| T\d+ \|", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            assert len(cells) >= 4, line
            status, evidence = cells[2], cells[3]
            if status == "DONE":
                assert evidence, f"DONE without evidence: {line}"
    # Backlog records must carry an explicit status from the vocabulary.
    for match in re.finditer(r"^### (BL-\d+)", text, re.MULTILINE):
        block = text[match.start():match.start() + 400]
        assert re.search(
            r"Status: (BACKLOG|READY|IN_PROGRESS|BLOCKED|REVIEW|DONE|DEFERRED)",
            block,
        ), f"{match.group(1)} has no status"


def test_acceptance_registry_rows_are_traceable() -> None:
    """Every recorded run needs a commit, a 64-hex ISO SHA, and a date."""
    text = (DOCS / "acceptance-tests.md").read_text()
    rows = [line for line in text.splitlines() if re.match(r"^\| R\d+ \|", line)]
    for row in rows:
        assert re.search(r"`[0-9a-f]{7,40}`", row), f"registry row missing commit: {row}"
        assert re.search(r"[0-9a-f]{64}", row), f"registry row missing ISO SHA: {row}"
        assert re.search(r"\d{4}-\d{2}-\d{2}", row), f"registry row missing date: {row}"
        assert " PASS " in row or " FAIL " in row, f"registry row missing result: {row}"
    # Secrets never enter evidence rows.
    for row in rows:
        assert "psk" not in row.lower() and "password" not in row.lower()


def test_docs_make_no_stale_credential_discard_claim() -> None:
    """The credential persists on SUSHIDA-CFG; docs must not claim disposal.

    The refactoring work order is excluded: it quotes the forbidden phrase
    as part of this very check's task description.
    """
    for path in sorted(DOCS.glob("*.md")) + [README, Path("AGENTS.md")]:
        if path.name == "refactoring-work-order.md":
            continue
        text = path.read_text()
        assert "資格情報は破棄" not in text, path
        assert "credentials are discarded" not in text.lower(), path
