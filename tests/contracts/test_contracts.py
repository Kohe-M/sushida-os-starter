"""Validate contract JSON files against their schemas and basic invariants.

Uses only the Python standard library (json, os, re).  No external
JSON Schema validator is imported.
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
FORBIDDEN_KEYS = {"password", "passwd", "secret", "credential", "private_key"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Parse and schema structure ──────────────────────────────────────────


def test_all_json_files_parse() -> None:
    for path in ALL_JSON:
        assert path.is_file(), f"missing: {path}"
        data = _load(path)
        assert isinstance(data, dict), f"{path}: not a JSON object"


def test_schema_has_metadata() -> None:
    for path in (RUNTIME_SCHEMA, RELEASE_SCHEMA):
        schema = _load(path)
        assert "$schema" in schema, f"{path}: missing $schema"
        assert "$id" in schema, f"{path}: missing $id"
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties not false"


def test_schema_version_is_const_1() -> None:
    for path in (RUNTIME_SCHEMA, RELEASE_SCHEMA):
        schema = _load(path)
        ver = schema.get("properties", {}).get("schema_version", {})
        assert ver.get("const") == 1, f"{path}: schema_version must be const 1"


def test_schema_version_matches() -> None:
    for contract, schema in [(RUNTIME_CONTRACT, RUNTIME_SCHEMA), (RELEASE_CONTRACT, RELEASE_SCHEMA)]:
        c = _load(contract)
        s = _load(schema)
        c_ver = c.get("schema_version")
        s_ver = s.get("properties", {}).get("schema_version", {}).get("const")
        assert c_ver == s_ver, f"{contract.name} version {c_ver} != {schema.name} const {s_ver}"


# ── Contract schema compliance ──────────────────────────────────────────


def test_contract_fields_exist_in_schema() -> None:
    for contract, schema_file in [(RUNTIME_CONTRACT, RUNTIME_SCHEMA), (RELEASE_CONTRACT, RELEASE_SCHEMA)]:
        c = _load(contract)
        s = _load(schema_file)
        props = s.get("properties", {})
        for key in c:
            assert key in props, f"{contract.name}: field {key!r} not in schema properties"


def test_schema_required_fields_exist_in_contract() -> None:
    for contract, schema_file in [(RUNTIME_CONTRACT, RUNTIME_SCHEMA), (RELEASE_CONTRACT, RELEASE_SCHEMA)]:
        c = _load(contract)
        s = _load(schema_file)
        required = s.get("required", [])
        for req in required:
            assert req in c, f"{contract.name}: missing schema-required field {req!r}"


# ── Routes ──────────────────────────────────────────────────────────────


def test_routes_have_no_duplicates() -> None:
    routes = _load(RUNTIME_CONTRACT)["routes"]
    assert len(routes) == len(set(routes)), f"duplicate route in: {routes}"


# ── Runtime paths ───────────────────────────────────────────────────────


def test_runtime_paths_are_absolute() -> None:
    for key, path in _load(RUNTIME_CONTRACT)["runtime_paths"].items():
        assert path.startswith("/"), f"runtime_path {key}={path!r}: not absolute"


# ── Services ────────────────────────────────────────────────────────────


def test_service_names_have_suffix() -> None:
    for key, name in _load(RUNTIME_CONTRACT)["services"].items():
        assert name.endswith(".service") or name.endswith(".mount") or name.endswith(".target"), \
            f"service {key}={name!r}: no .service/.mount/.target suffix"


def test_service_state_names_are_unique() -> None:
    services = _load(RELEASE_CONTRACT)["required_services"]
    names = [s["name"] for s in services]
    assert len(names) == len(set(names)), f"duplicate service names: {names}"


# ── Artifacts ───────────────────────────────────────────────────────────


def test_artifact_names_unique() -> None:
    names = [a["name"] for a in _load(RELEASE_CONTRACT)["artifacts"]]
    assert len(names) == len(set(names)), f"duplicate artifact names: {names}"


def test_artifact_name_no_path_separator() -> None:
    for a in _load(RELEASE_CONTRACT)["artifacts"]:
        assert "/" not in a["name"] and "\\" not in a["name"], \
            f"artifact name must be basename only: {a['name']!r}"


# ── ISO paths ───────────────────────────────────────────────────────────


def test_required_iso_paths_unique_by_region_and_path() -> None:
    paths = _load(RELEASE_CONTRACT)["required_iso_paths"]
    pairs = [(p["region"], p["path"]) for p in paths]
    assert len(pairs) == len(set(pairs)), f"duplicate (region, path) in required_iso_paths"


def test_required_iso_paths_absolute() -> None:
    for p in _load(RELEASE_CONTRACT)["required_iso_paths"]:
        assert p["path"].startswith("/"), f"ISO path not absolute: {p['path']!r}"


# ── Source/image mappings ───────────────────────────────────────────────


def test_source_image_mappings_no_duplicates() -> None:
    sources = [m["source"] for m in _load(RELEASE_CONTRACT)["source_image_mappings"]]
    assert len(sources) == len(set(sources)), f"duplicate source paths: {sources}"


def test_mapping_image_paths_absolute() -> None:
    for m in _load(RELEASE_CONTRACT)["source_image_mappings"]:
        assert m["image_path"].startswith("/"), f"image_path not absolute: {m['image_path']!r}"


def test_mapping_sources_not_absolute() -> None:
    for m in _load(RELEASE_CONTRACT)["source_image_mappings"]:
        assert not m["source"].startswith("/"), f"source must be relative: {m['source']!r}"


def test_mapping_no_dotdot() -> None:
    for m in _load(RELEASE_CONTRACT)["source_image_mappings"]:
        assert ".." not in m["source"], f"source contains .. : {m['source']!r}"
        assert ".." not in m["image_path"], f"image_path contains .. : {m['image_path']!r}"


def test_security_critical_mapped_or_generated() -> None:
    rc = _load(RELEASE_CONTRACT)
    mapped_paths = {m["image_path"] for m in rc["source_image_mappings"] if m["security_critical"]}
    iso_paths = {p["path"] for p in rc["required_iso_paths"] if p["security_critical"]}
    # Every security-critical required_iso_path should be either mapped or
    # explicitly noted as generated.
    for iso_p in rc["required_iso_paths"]:
        if iso_p["security_critical"] and iso_p["path"] not in mapped_paths:
            assert iso_p["path"] in {"/live/vmlinuz", "/live/initrd.img", "/live/filesystem.squashfs"}, \
                f"security-critical path {iso_p['path']!r} has no mapping"


# ── Packages ────────────────────────────────────────────────────────────


def test_required_packages_unique() -> None:
    pkgs = _load(RELEASE_CONTRACT)["required_packages"]
    assert len(pkgs) == len(set(pkgs)), f"duplicate packages: {pkgs}"


def test_package_count_matches() -> None:
    pkgs = _load(RELEASE_CONTRACT)["required_packages"]
    assert len(pkgs) == 38, f"expected 38 packages, got {len(pkgs)}"


# ── Forbidden keys ──────────────────────────────────────────────────────


def test_no_forbidden_fields_in_contracts() -> None:
    for path in ALL_JSON:
        def _check(obj, ctx):
            if isinstance(obj, dict):
                for key in obj:
                    assert key.lower() not in FORBIDDEN_KEYS, \
                        f"{path}: forbidden key {key!r} in {ctx}"
                    _check(obj[key], f"{ctx}.{key}")
            elif isinstance(obj, list):
                for i, val in enumerate(obj):
                    _check(val, f"{ctx}[{i}]")
        _check(_load(path), path.name)


# ── Navigation ──────────────────────────────────────────────────────────


def test_navigation_allowlist_has_required_entries() -> None:
    nav = _load(RUNTIME_CONTRACT)["navigation"]
    assert any("sushida.net" in e for e in nav["allowlist"]), "allowlist must contain sushida.net"
    assert len(nav["allowlist"]) >= 3, "allowlist must have at least 3 entries"


def test_navigation_blocklist_has_required_entries() -> None:
    nav = _load(RUNTIME_CONTRACT)["navigation"]
    assert "*" in nav["blocklist"], "blocklist must contain *"
    assert "view-source:*" in nav["blocklist"], "blocklist must contain view-source:*"
    assert len(nav["blocklist"]) >= 5, "blocklist must have at least 5 entries"


# ── Timeouts ────────────────────────────────────────────────────────────


def test_timeout_values_are_positive() -> None:
    for key, value in _load(RUNTIME_CONTRACT)["timeouts"].items():
        assert isinstance(value, (int, float)), f"timeout {key}: not a number"
        assert value >= 0, f"timeout {key}: negative"


# ── Metadata ────────────────────────────────────────────────────────────


def test_metadata_required_fields_are_not_empty() -> None:
    meta = _load(RELEASE_CONTRACT)["metadata"]
    assert len(meta["required_fields"]) >= 9, f"expected >=9 fields, got {len(meta['required_fields'])}"


def test_metadata_static_values() -> None:
    meta = _load(RELEASE_CONTRACT)["metadata"]
    assert meta.get("static_values", {}).get("architecture") == "amd64"
    assert meta.get("static_values", {}).get("debian_release") == "trixie"


# ── JSON format ─────────────────────────────────────────────────────────


def test_json_serialization_is_stable() -> None:
    """Re-serializing with sorted keys produces the same semantic content."""
    for path in ALL_JSON:
        data = _load(path)
        original_raw = path.read_text(encoding="utf-8")
        canonical = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert json.loads(original_raw) == json.loads(canonical), \
            f"{path}: semantic mismatch in round-trip"


def test_all_files_end_with_newline() -> None:
    for path in ALL_JSON:
        text = path.read_bytes()
        assert text.endswith(b"\n"), f"{path}: missing trailing newline"


# ─── Services masked list ────────────────────────────────────────────────


def test_masked_services_present() -> None:
    services = _load(RELEASE_CONTRACT)["required_services"]
    masked = [s["name"] for s in services if s["state"] == "masked"]
    assert any("getty" in m for m in masked), "getty services should be masked"
    assert "ctrl-alt-del.target" in masked
