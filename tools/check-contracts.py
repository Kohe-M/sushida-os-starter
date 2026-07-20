#!/usr/bin/env python3
"""Check-only contract validator for Sushi-da OS.

Verifies that the runtime-contract.json and release-contract.json files
are self-consistent and that the current production source code has not
drifted from the declared contracts.

Exit codes:
  0  All checks pass
  1  Contract validation error or drift detected
  2  Usage error, unreadable file, or internal error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

CONTRACTS_SUBDIR = "contracts"
RUNTIME_CONTRACT = "runtime-contract.json"
RELEASE_CONTRACT = "release-contract.json"
RUNTIME_SCHEMA = "schema/runtime-contract.schema.json"
RELEASE_SCHEMA = "schema/release-contract.schema.json"

PRODUCTION_ROOT = "live-build/config/includes.chroot"
SCRIPTS_DIR = "scripts"
TEST_STATIC_DIR = "tests/static"

# Secret-like JSON keys that must never appear.
FORBIDDEN_FIELD_NAMES = {"password", "passwd", "secret", "credential", "private_key"}


# ── Reporting ──────────────────────────────────────────────────────────


class Result:
    """Collect errors and warnings deterministically."""

    def __init__(self) -> None:
        self.errors: list[dict[str, str]] = []
        self.warnings: list[dict[str, str]] = []

    def error(self, code: str, contract: str, field: str, file: str, message: str) -> None:
        self.errors.append({
            "code": code, "contract": contract, "field": field,
            "file": file, "message": message,
        })

    def warn(self, code: str, contract: str, field: str, file: str, message: str) -> None:
        self.warnings.append({
            "code": code, "contract": contract, "field": field,
            "file": file, "message": message,
        })

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def human_report(self) -> str:
        lines: list[str] = []
        if self.ok and not self.warnings:
            lines.append("runtime_contract=PASS")
            lines.append("release_contract=PASS")
            lines.append("contract_drift=PASS")
        else:
            for entry in self.errors + self.warnings:
                kind = "ERROR" if entry in self.errors else "WARN"
                code = entry["code"]
                file_field = f"{entry['file']}:{entry['field']}" if entry["field"] else entry["file"]
                lines.append(f"{kind} [{code}] {file_field}")
                lines.append(f"  {entry['message']}")
            if self.errors:
                lines.append(f"contract_drift=FAIL ({len(self.errors)} error(s))")
            else:
                lines.append("contract_drift=PASS")
        return "\n".join(lines) + "\n"

    def json_report(self) -> dict:
        return {
            "ok": self.ok,
            "errors": sorted(self.errors, key=lambda e: (e["code"], e["field"])),
            "warnings": sorted(self.warnings, key=lambda w: (w["code"], w["field"])),
        }


# ── Helpers ────────────────────────────────────────────────────────────


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON: {path}: {exc}") from exc


# ── Schema validation ───────────────────────────────────────────────────


def _validate_type(value: Any, expected: str, path: str) -> list[str]:
    """Return a list of error messages for a type mismatch."""
    if expected == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array, got {type(value).__name__}"]
    elif expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
    elif expected == "string":
        if not isinstance(value, str):
            return [f"{path}: expected string, got {type(value).__name__}"]
    elif expected == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{path}: expected integer, got {type(value).__name__}"]
    elif expected == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return [f"{path}: expected number, got {type(value).__name__}"]
    elif expected == "boolean":
        if not isinstance(value, bool):
            return [f"{path}: expected boolean, got {type(value).__name__}"]
    return []


def _check_schema(contract: dict, schema: dict, ctx: str, result: Result) -> None:
    """Validate contract data against sketch schema restrictions."""
    props = schema.get("properties", {})
    req = schema.get("required", [])
    addl_props = schema.get("additionalProperties", True)
    contract_name = os.path.basename(ctx).replace(".schema.json", "")

    # Check required fields exist
    for field in req:
        if field not in contract:
            result.error("SCHEMA_REQUIRED", contract_name, field, ctx,
                         f"missing required field: {field}")

    # Check unknown fields
    if addl_props is False:
        for key in contract:
            if key not in props:
                result.error("SCHEMA_UNKNOWN_FIELD", contract_name, key, ctx,
                             f"unknown field: {key}")

    # Validate type + constraints
    for key, val in contract.items():
        if key not in props:
            continue
        prop_def = props[key]

        # Handle const (no type)
        if "const" in prop_def:
            if val != prop_def["const"]:
                result.error("SCHEMA_CONST", contract_name, key, ctx,
                             f"expected const {prop_def['const']!r}, got {val!r}")
            continue

        errs = _validate_type(val, prop_def.get("type", "object"), f"{ctx}.{key}")
        for e in errs:
            result.error("SCHEMA_TYPE", contract_name, key, ctx, e)

        # integer/number constraints
        if isinstance(val, (int, float)):
            pmin = prop_def.get("minimum")
            pmax = prop_def.get("maximum")
            if pmin is not None and val < pmin:
                result.error("SCHEMA_BOUND", contract_name, key, ctx,
                             f"value {val} < minimum {pmin}")
            if pmax is not None and val > pmax:
                result.error("SCHEMA_BOUND", contract_name, key, ctx,
                             f"value {val} > maximum {pmax}")

        # string pattern
        if isinstance(val, str):
            pattern = prop_def.get("pattern")
            if pattern and not re.search(pattern, val):
                result.error("SCHEMA_PATTERN", contract_name, key, ctx,
                             f"value {val!r} does not match pattern {pattern!r}")

        # enum
        enum = prop_def.get("enum")
        if enum and val not in enum:
            result.error("SCHEMA_ENUM", contract_name, key, ctx,
                         f"value {val!r} not in enum {enum}")

        # minItems / uniqueItems
        if isinstance(val, list):
            min_items = prop_def.get("minItems")
            if min_items is not None and len(val) < min_items:
                result.error("SCHEMA_MINITEMS", contract_name, key, ctx,
                             f"expected >= {min_items} items, got {len(val)}")
            unique = prop_def.get("uniqueItems", False)
            if unique:
                seen = set()
                for item in val:
                    if isinstance(item, str):
                        if item in seen:
                            result.error("SCHEMA_DUPLICATE", contract_name, key, ctx,
                                         f"duplicate {item!r}")
                        seen.add(item)

        # Recurse sub-objects
        sub_props = prop_def.get("properties", {})
        if isinstance(val, dict) and sub_props:
            _check_schema(val, prop_def, f"{ctx}.{key}", result)

        # Recurse array items
        items_def = prop_def.get("items", {})
        if isinstance(val, list) and items_def:
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    _check_schema(item, items_def, f"{ctx}.{key}[{i}]", result)
                elif isinstance(item, str):
                    item_pat = items_def.get("pattern")
                    if item_pat and not re.search(item_pat, item):
                        result.error("SCHEMA_PATTERN", contract_name, f"{key}[{i}]", ctx,
                                     f"value {item!r} does not match pattern {item_pat!r}")


# ── Drift inspection: runtime ──────────────────────────────────────────


def _drift_runtime(contract: dict, root: Path, result: Result) -> None:
    c = contract
    # Production URL from config.env
    config_env = root / PRODUCTION_ROOT / "etc/sushida-os/config.env"
    if config_env.is_file():
        for line in config_env.read_text().splitlines():
            line = line.strip()
            if line.startswith("SUSHIDA_URL="):
                val = line.split("=", 1)[1].strip("\"'")
                expected = c.get("urls", {}).get("sushida_url", "")
                if val != expected:
                    result.error("RUNTIME_URL_MISMATCH", "runtime",
                                 "urls.sushida_url", str(config_env),
                                 f"config.env has {val!r}, contract expects {expected!r}")

    # Chromium managed policy URL allowlist
    policy_file = root / PRODUCTION_ROOT / "etc/chromium/policies/managed/sushida-os.json"
    if policy_file.is_file():
        policy = _load_json(policy_file)
        nav = c.get("navigation", {})
        contract_allow = set(nav.get("allowlist", []))
        policy_allow = set(policy.get("URLAllowlist", []))
        if contract_allow != policy_allow:
            result.error("RUNTIME_ALLOWLIST_MISMATCH", "runtime",
                         "navigation.allowlist", str(policy_file),
                         f"contract has {contract_allow}, policy has {policy_allow}")

    # Route file paths
    runtime_paths = c.get("runtime_paths", {})
    launcher = root / PRODUCTION_ROOT / "usr/local/bin/sushida-launch"
    if launcher.is_file():
        text = launcher.read_text()
        route_file = runtime_paths.get("active_route_file", "")
        if route_file:
            # Check for the filename part, since the full path is constructed
            route_name = os.path.basename(route_file)
            if route_name not in text:
                result.warn("RUNTIME_PATH", "runtime", "runtime_paths.active_route_file",
                            str(launcher), f"{route_name!r} not found in launcher")

    # Service names — check custom unit files exist
    system_services = {"systemd-timesyncd.service", "NetworkManager.service"}
    services = c.get("services", {})
    for key, service_name in services.items():
        if service_name in system_services:
            continue  # installed by Debian package, not in includes.chroot
        unit_path = root / PRODUCTION_ROOT / "etc/systemd/system" / service_name
        if not unit_path.is_file() and not unit_path.is_symlink():
            result.error("RUNTIME_SERVICE_MISSING", "runtime",
                         f"services.{key}", str(unit_path),
                         f"service file not found: {unit_path}")


# ── Drift inspection: release ──────────────────────────────────────────


def _drift_release(contract: dict, root: Path, result: Result) -> None:
    rc = contract

    # Build script artifact names
    build_sh = root / SCRIPTS_DIR / "build.sh"
    if build_sh.is_file():
        text = build_sh.read_text()
        for artifact in rc.get("artifacts", []):
            name = artifact["name"]
            if name not in text:
                result.warn("RELEASE_ARTIFACT", "release", f"artifacts.{name}",
                            str(build_sh), f"artifact {name!r} not found in build.sh")

    # Flash script ISO name
    flash_sh = root / SCRIPTS_DIR / "flash.sh"
    if flash_sh.is_file():
        flash_text = flash_sh.read_text()
        iso_name = "sushida-os-amd64.iso"
        if iso_name not in flash_text:
            result.warn("RELEASE_ISO_NAME", "release", "artifacts.iso_name",
                        str(flash_sh), f"ISO name {iso_name!r} not in flash.sh")

    # Package list
    pkg_list = root / "live-build/config/package-lists/kiosk.list.chroot"
    if pkg_list.is_file():
        pkgs = set()
        for line in pkg_list.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                pkgs.add(s.split()[0])
        required = set(rc.get("required_packages", []))
        missing = required - pkgs
        if missing:
            result.error("RELEASE_PACKAGE_MISSING", "release",
                         "required_packages", str(pkg_list),
                         f"packages not in package list: {sorted(missing)}")

    # Required service enable/mask from validate hook
    validate_hook = root / "live-build/config/hooks/live/090-validate-image.hook.chroot"
    if validate_hook.is_file():
        hook_text = validate_hook.read_text()
        for svc in rc.get("required_services", []):
            name = svc["name"]
            state = svc["state"]
            # Simple check: enabled services appear in enable hook or validate
            enable_hook = root / "live-build/config/hooks/live/020-enable-services.hook.chroot"
            if enable_hook.is_file():
                enable_text = enable_hook.read_text()
                if state == "enabled" and name not in enable_text:
                    result.warn("RELEASE_SERVICE", "release", f"required_services.{name}",
                                str(enable_hook), f"service {name} not enabled in hook")

    # Source-image mappings: check source files exist
    for mapping in rc.get("source_image_mappings", []):
        src = root / mapping["source"]
        if not src.is_file() and not src.is_symlink():
            result.error("RELEASE_MAPPING_SOURCE", "release",
                         f"source_image_mappings.{mapping['source']}", str(src),
                         f"mapping source not found: {mapping['source']}")


# ── Secret check ───────────────────────────────────────────────────────


def _check_secrets(data: Any, ctx: str, path: str, result: Result) -> None:
    if isinstance(data, dict):
        for key, val in data.items():
            if key.lower() in FORBIDDEN_FIELD_NAMES:
                result.error("FORBIDDEN_KEY", path, key, ctx,
                             f"forbidden key {key!r}")
            _check_secrets(val, ctx, f"{path}.{key}", result)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _check_secrets(item, ctx, f"{path}[{i}]", result)


# ── Main ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Sushi-da OS contracts")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--root", default=".", help="repository root (default: .)")
    parser.add_argument("--runtime-contract", help="path to runtime contract")
    parser.add_argument("--release-contract", help="path to release contract")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    contracts_dir = root / CONTRACTS_SUBDIR

    # Resolve contract paths
    rt_path = Path(args.runtime_contract) if args.runtime_contract else \
        contracts_dir / RUNTIME_CONTRACT
    rc_path = Path(args.release_contract) if args.release_contract else \
        contracts_dir / RELEASE_CONTRACT
    rt_schema_path = contracts_dir / RUNTIME_SCHEMA
    rc_schema_path = contracts_dir / RELEASE_SCHEMA

    # Validate files are readable
    for p in (rt_path, rc_path, rt_schema_path, rc_schema_path):
        if not p.is_file():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 2

    result = Result()

    try:
        runtime = _load_json(rt_path)
        release = _load_json(rc_path)
        rt_schema = _load_json(rt_schema_path)
        rc_schema = _load_json(rc_schema_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Schema validation
    _check_schema(runtime, rt_schema, "runtime-contract", result)
    _check_schema(release, rc_schema, "release-contract", result)

    # Schema version consistency
    for name, contract, schema in [
        ("runtime", runtime, rt_schema),
        ("release", release, rc_schema),
    ]:
        c_ver = contract.get("schema_version")
        s_ver = schema.get("properties", {}).get("schema_version", {}).get("const")
        if c_ver != s_ver:
            result.error("SCHEMA_VERSION", name, "schema_version", f"{name}-contract.json",
                         f"contract version {c_ver} != schema const {s_ver}")

    # Secret check
    for name, data in [("runtime", runtime), ("release", release),
                        ("runtime-schema", rt_schema), ("release-schema", rc_schema)]:
        _check_secrets(data, f"{name}.json", name, result)

    # Runtime drift
    _drift_runtime(runtime, root, result)

    # Release drift
    _drift_release(release, root, result)

    # Unused field tracking (checker must reference contract fields)
    # Fields below are explicitly handled; anything else should be warned.
    handled_runtime_fields = {
        "schema_version", "urls", "runtime_paths", "routes",
        "services", "timeouts", "navigation",
    }
    for key in runtime:
        if key not in handled_runtime_fields:
            result.warn("UNHANDLED_RUNTIME_FIELD", "runtime", key, "runtime-contract.json",
                        f"checker does not inspect field {key!r}")

    # Output
    if args.json:
        report_data = result.json_report()
        report_data["schema_version"] = 1
        print(json.dumps(report_data, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        sys.stdout.write(result.human_report())

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
