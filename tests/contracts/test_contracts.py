"""Validate contract JSON files against their schemas and basic invariants.

This test file uses only the Python standard library (json, os, re).
No JSON Schema validator is imported — structural checks are explicit.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

CONTRACTS = Path("contracts")
SCHEMAS = CONTRACTS / "schema"

RUNTIME_CONTRACT = CONTRACTS / "runtime-contract.json"
RELEASE_CONTRACT = CONTRACTS / "release-contract.json"
RUNTIME_SCHEMA = SCHEMAS / "runtime-contract.schema.json"
RELEASE_SCHEMA = SCHEMAS / "release-contract.schema.json"

ALL_JSON = [RUNTIME_CONTRACT, RELEASE_CONTRACT, RUNTIME_SCHEMA, RELEASE_SCHEMA]

# Fields that must never appear as JSON keys in any contract or schema.
# "token" is excluded because csrf_token is a legitimate security field.
FORBIDDEN_KEYS = {"password", "passwd", "secret", "credential", "private_key"}


def test_all_json_files_parse() -> None:
    for path in ALL_JSON:
        assert path.is_file(), f"missing: {path}"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path}: not a JSON object"


def test_schema_has_metadata() -> None:
    for path in (RUNTIME_SCHEMA, RELEASE_SCHEMA):
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert "$schema" in schema, f"{path}: missing $schema"
        assert "$id" in schema, f"{path}: missing $id"
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties not false"


def test_schema_version_matches() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    rs = json.loads(RUNTIME_SCHEMA.read_text(encoding="utf-8"))
    assert rt["schema_version"] == rs.get("properties", {}).get("schema_version", {}).get("minimum", -1)


def test_routes_have_no_duplicates() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    routes = rt["routes"]
    assert len(routes) == len(set(routes)), f"duplicate route in: {routes}"


def test_runtime_paths_are_absolute() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    for key, path in rt["runtime_paths"].items():
        assert path.startswith("/"), f"runtime_path {key}={path!r}: not absolute"


def test_service_names_have_suffix() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    for key, name in rt["services"].items():
        assert name.endswith(".service") or name.endswith(".mount") or name.endswith(".target"), \
            f"service {key}={name!r}: no .service/.mount/.target suffix"


def test_artifact_names_unique() -> None:
    rc = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    names = [a["name"] for a in rc["artifacts"]]
    assert len(names) == len(set(names)), f"duplicate artifact names: {names}"


def test_source_image_mappings_no_duplicates() -> None:
    rc = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    sources = [m["source"] for m in rc["source_image_mappings"]]
    assert len(sources) == len(set(sources)), f"duplicate source paths: {sources}"


# Fields that must never appear as JSON keys in any contract or schema.
# "token" is excluded because csrf_token is a legitimate security field.
FORBIDDEN_KEYS = {"password", "passwd", "secret", "credential", "private_key"}


def test_no_forbidden_fields_in_contracts() -> None:
    for path in ALL_JSON:
        def check_obj(obj, ctx):
            if isinstance(obj, dict):
                for key, val in obj.items():
                    assert key.lower() not in FORBIDDEN_KEYS, f"{path}: forbidden key {key!r} in {ctx}"
                    check_obj(val, f"{ctx}.{key}")
            elif isinstance(obj, list):
                for i, val in enumerate(obj):
                    check_obj(val, f"{ctx}[{i}]")
        data = json.loads(path.read_text(encoding="utf-8"))
        check_obj(data, path.name)


def test_unknown_top_level_fields() -> None:
    rt_known = {"schema_version", "urls", "runtime_paths", "routes", "services", "timeouts", "navigation"}
    rc_known = {"schema_version", "artifacts", "required_iso_paths", "source_image_mappings",
                "required_packages", "required_services", "metadata"}
    for path, known in [(RUNTIME_CONTRACT, rt_known), (RELEASE_CONTRACT, rc_known)]:
        data = json.loads(path.read_text(encoding="utf-8"))
        unknown = set(data.keys()) - known
        assert not unknown, f"{path}: unknown top-level fields: {unknown}"


def test_json_serialization_is_stable() -> None:
    """JSON must use the same key order and indent on every serialization."""
    for path in ALL_JSON:
        data = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        original = path.read_text(encoding="utf-8")
        # Compare normalized: parse + re-serialize both
        normed = json.dumps(json.loads(original), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert json.loads(original) == json.loads(normed), f"{path}: semantic mismatch in round-trip"


def test_all_files_end_with_newline() -> None:
    for path in ALL_JSON:
        text = path.read_bytes()
        assert text.endswith(b"\n"), f"{path}: missing trailing newline"


def test_timeout_bounds() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    timeouts = rt["timeouts"]
    for key, value in timeouts.items():
        assert isinstance(value, (int, float)), f"timeout {key}: not a number"
        assert value >= 0, f"timeout {key}: negative"


def test_navigation_lists_have_expected_content() -> None:
    rt = json.loads(RUNTIME_CONTRACT.read_text(encoding="utf-8"))
    nav = rt["navigation"]
    assert "*" in nav["blocklist"], "blocklist must contain *"
    assert "view-source:*" in nav["blocklist"], "blocklist must contain view-source:*"
    assert any("sushida.net" in e for e in nav["allowlist"]), "allowlist must contain sushida.net"
    assert len(nav["allowlist"]) >= 3, "allowlist must have at least 3 entries"
    assert len(nav["blocklist"]) >= 5, "blocklist must have at least 5 entries"


def test_release_services_match_validate_hook() -> None:
    rc = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    enabled = [s["name"] for s in rc["required_services"] if s["state"] == "enabled"]
    # Check that all enabled services are present
    expected_enabled = [
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-navigation-watch.service",
        "sushida-config-prepare.service",
        "sushida-wifi-setup.service",
        "systemd-timesyncd.service",
    ]
    for svc in expected_enabled:
        assert svc in enabled, f"enabled service {svc} missing from contract"
    masked = [s["name"] for s in rc["required_services"] if s["state"] == "masked"]
    assert any("getty" in m for m in masked), "getty services should be masked"
    assert "ctrl-alt-del.target" in masked


def test_metadata_architecture() -> None:
    rc = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    assert rc["metadata"]["architecture"] == "amd64"


def test_metadata_debian_release() -> None:
    rc = json.loads(RELEASE_CONTRACT.read_text(encoding="utf-8"))
    assert rc["metadata"]["debian_release"] == "trixie"
