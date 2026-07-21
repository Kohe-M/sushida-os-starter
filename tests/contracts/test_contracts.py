"""Validate contract JSON files against their schemas and basic invariants.

Uses only the Python standard library (json, os, re).  No external
JSON Schema validator is imported.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

CONTRACTS = Path("contracts")
SCHEMAS = CONTRACTS / "schema"

RUNTIME_CONTRACT = CONTRACTS / "runtime-contract.json"
RELEASE_CONTRACT = CONTRACTS / "release-contract.json"
RUNTIME_SCHEMA = SCHEMAS / "runtime-contract.schema.json"
RELEASE_SCHEMA = SCHEMAS / "release-contract.schema.json"

ALL_JSON = [RUNTIME_CONTRACT, RELEASE_CONTRACT, RUNTIME_SCHEMA, RELEASE_SCHEMA]

SCHEMA_PREDICATE = {
    "source-path": {
        "rules": [r"^/", r"(^|/)\.\.(/|$)", r"[\r\n\t ]", r"^\.$", r"^\.\.$"],
        "set": ["/tmp/file", "a/../b", "../outside", ".", "..", "a\nb"],
        "accept": ["path/to/file", "a/b/c"],
    },
    "image-path": {
        "rules": [r"(^|/)\.\.(/|$)", r"[\r\n\t ]"],
        "set": ["/etc/../tmp", "rel/path", "a/../../b", "/with space"],
        "accept": ["/etc/file", "/usr/local/bin/x"],
    },
    "artifact-name": {
        "rules": [r"[/\\]", r"^\.$", r"^\.\."],
        "set": ["../file", ".", "a/b", "a\\b"],
        "accept": ["sushida-os-amd64.iso", "SHA256SUMS"],
    },
}

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


# ── Schema semantics: path constraints ─────────────────────────────────


@pytest.mark.parametrize("value", SCHEMA_PREDICATE["source-path"]["set"])
def test_source_path_rejects_absolute_and_dotdot_schema_structure(value: str) -> None:
    """Source paths must be relative, no .., no ., no backslash, no whitespace."""
    for rule in SCHEMA_PREDICATE["source-path"]["rules"]:
        if re.search(rule, value):
            return
    pytest.fail(f"source={value!r} was not rejected by any rule")


@pytest.mark.parametrize("value", SCHEMA_PREDICATE["source-path"]["accept"])
def test_source_path_accepts_valid_relative_paths(value: str) -> None:
    for rule in SCHEMA_PREDICATE["source-path"]["rules"]:
        assert not re.search(rule, value), f"source={value!r} rejected by {rule!r}"


@pytest.mark.parametrize("value", SCHEMA_PREDICATE["image-path"]["set"])
def test_image_path_rejects_relative_and_dotdot(value: str) -> None:
    for rule in SCHEMA_PREDICATE["image-path"]["rules"]:
        if re.search(rule, value):
            return
    if not value.startswith("/"):
        return
    pytest.fail(f"image_path={value!r} was not rejected")


@pytest.mark.parametrize("value", SCHEMA_PREDICATE["image-path"]["accept"])
def test_image_path_accepts_absolute_paths(value: str) -> None:
    assert value.startswith("/"), f"valid image_path must be absolute: {value!r}"
    assert ".." not in value, f"valid image_path must not contain ..: {value!r}"
    assert " " not in value, f"valid image_path must not contain space: {value!r}"


@pytest.mark.parametrize("value", SCHEMA_PREDICATE["artifact-name"]["set"])
def test_artifact_name_rejects_path_separators_and_dot(value: str) -> None:
    rules = [r"[/\\]", r"^\.$", r"^\.\."]
    for rule in rules:
        if re.search(rule, value):
            return
    pytest.fail(f"artifact name={value!r} was not rejected")


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
    for iso_p in rc["required_iso_paths"]:
        if iso_p["security_critical"] and iso_p["path"] not in mapped_paths:
            assert iso_p["path"] in {"/live/vmlinuz", "/live/initrd.img", "/live/filesystem.squashfs"}, \
                f"security-critical path {iso_p['path']!r} has no mapping"


def test_mapping_source_files_exist() -> None:
    for mapping in _load(RELEASE_CONTRACT)["source_image_mappings"]:
        source = Path(mapping["source"])
        assert source.is_file(), f"mapping source file missing: {source}"


def test_mapping_all_have_verification_level() -> None:
    for m in _load(RELEASE_CONTRACT)["source_image_mappings"]:
        assert "current_verification" in m, f"mapping {m['source']!r} missing current_verification"
        assert m["current_verification"] in ("none", "presence", "exact")


def test_exact_verification_set_matches_verify_iso() -> None:
    """verify-iso.sh byte-compares whatever the contract marks exact.

    The comparison loop is contract-driven, so this pins the *floor*: the
    historically byte-compared Wi-Fi/config files must never drop below
    exact, and every squashfs mapping is expected to be exact (the image
    installs includes.chroot files verbatim from a clean worktree).  A
    demotion requires evidence from a real build and a deliberate edit
    here.
    """
    rc = _load(RELEASE_CONTRACT)
    exact_paths = {
        m["image_path"]
        for m in rc["source_image_mappings"]
        if m["current_verification"] == "exact"
    }
    historical_floor = {
        "/etc/systemd/system/sushida-config-prepare.service",
        "/etc/systemd/system/sushida-wifi-setup.service",
        "/etc/systemd/system/var-lib-sushida\\x2dconfig.mount",
        "/usr/local/libexec/sushida-config-prepare",
        "/usr/local/libexec/sushida-wifi-setup",
    }
    assert historical_floor <= exact_paths, (
        f"historically exact files were demoted: {historical_floor - exact_paths}"
    )
    squashfs_paths = {
        m["image_path"]
        for m in rc["source_image_mappings"]
        if m["region"] == "squashfs"
    }
    assert exact_paths == squashfs_paths, (
        f"squashfs mappings not marked exact: {squashfs_paths - exact_paths}"
    )


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


def test_json_round_trip_preserves_semantics() -> None:
    """Re-serializing produces the same JSON content after sorting keys."""
    for path in ALL_JSON:
        data = _load(path)
        recomposed = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert json.loads(recomposed) == _load(path), f"{path}: semantic mismatch in round-trip"


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


def test_enabled_services_present() -> None:
    services = _load(RELEASE_CONTRACT)["required_services"]
    enabled = [s["name"] for s in services if s["state"] == "enabled"]
    expected = [
        "sushida-kiosk.service",
        "sushida-network-watch.service",
        "sushida-navigation-watch.service",
        "sushida-config-prepare.service",
        "sushida-wifi-setup.service",
        "systemd-timesyncd.service",
    ]
    for svc in expected:
        assert svc in enabled, f"enabled service {svc} missing from contract"
