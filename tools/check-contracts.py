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


def _must_exist(root: Path, rel: str, desc: str, result: Result, contract_name: str) -> Path | None:
    """Return the resolved path, or record MISSING_SOURCE and return None."""
    path = root / rel
    if not path.is_file():
        result.error("MISSING_SOURCE", contract_name, rel, str(path),
                     f"required {desc} not found: {rel}")
        return None
    return path


# ── Schema validation ───────────────────────────────────────────────────

# Keywords this checker can process or at least recognise.
SUPPORTED_SCHEMA_KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "items",
    "const", "minimum", "maximum", "pattern", "enum", "minItems",
    "uniqueItems", "minLength", "format", "allOf", "if", "then", "else",
    "not", "description", "title", "$schema", "$id", "default",
}


def _validate_type(value: Any, expected: str, path: str) -> list[str]:
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
    """Validate contract data against schema restrictions."""
    props = schema.get("properties", {})
    req = schema.get("required", [])
    addl = schema.get("additionalProperties", True)
    contract_name = os.path.basename(ctx).replace(".schema.json", "")

    # Unsupported keyword detection
    for key in schema:
        if key not in SUPPORTED_SCHEMA_KEYWORDS:
            result.error("UNSUPPORTED_KEYWORD", contract_name, key, ctx,
                         f"keyword {key!r} is not implemented")

    # required
    for field in req:
        if field not in contract:
            result.error("SCHEMA_REQUIRED", contract_name, field, ctx,
                         f"missing required field: {field}")

    # additionalProperties
    if addl is False:
        for key in contract:
            if key not in props:
                result.error("SCHEMA_UNKNOWN", contract_name, key, ctx,
                             f"unknown field: {key}")

    # allOf
    for cond in schema.get("allOf", []):
        _check_schema(contract, cond, ctx, result)

    # not
    not_cond = schema.get("not")
    if not_cond:
        if _schema_cond_matches(contract, not_cond):
            result.error("SCHEMA_NOT", contract_name, "", ctx,
                         "contract matches a 'not' constraint")

    # if/then/else
    if_cond = schema.get("if")
    if if_cond:
        matched = _schema_cond_matches(contract, if_cond)
        if matched and "then" in schema:
            _check_schema(contract, schema["then"], ctx, result)
        elif not matched and "else" in schema:
            _check_schema(contract, schema["else"], ctx, result)

    # Validate each field
    for key, val in contract.items():
        if key not in props:
            continue
        pd = props[key]
        _validate_value(val, pd, contract_name, ctx, key, result)

    # Recurse sub-objects (from properties not yet handled)
    for key, val in contract.items():
        if key not in props:
            continue
        pd = props[key]
        if isinstance(val, dict) and pd.get("properties", {}):
            _check_schema(val, pd, f"{ctx}.{key}", result)
        items_def = pd.get("items", {})
        if isinstance(val, list) and items_def:
            for i, item in enumerate(val):
                if isinstance(item, dict):
                    _check_schema(item, items_def, f"{ctx}.{key}[{i}]", result)


def _validate_value(val: Any, pd: dict, contract_name: str, ctx: str, key: str, result: Result) -> None:
    """Validate a single value against its property definition, recursing into allOf/not/if/then."""
    fctx = f"{ctx}.{key}"

    # const
    c = pd.get("const")
    if c is not None:
        if val != c:
            result.error("SCHEMA_CONST", contract_name, key, ctx, f"expected const {c!r}, got {val!r}")
        return

    # allOf — every sub-condition must pass
    for cond in pd.get("allOf", []):
        _validate_value(val, cond, contract_name, fctx, key, result)

    # not — must fail
    n = pd.get("not")
    if n:
        nr = Result()
        _validate_value(val, n, contract_name, fctx, key, nr)
        if nr.ok:
            result.error("SCHEMA_NOT", contract_name, key, ctx, "value matches 'not' constraint")

    # if/then/else
    ifc = pd.get("if")
    if ifc:
        matched = True
        if isinstance(val, dict):
            for f in ifc.get("required", []):
                if f not in val:
                    matched = False
            for fk, fpd in ifc.get("properties", {}).items():
                fv = val.get(fk)
                if fv is not None:
                    fc = fpd.get("const")
                    if fc is not None and fv != fc:
                        matched = False
        if matched and "then" in pd:
            _validate_value(val, pd["then"], contract_name, fctx, key, result)
        elif not matched and "else" in pd:
            _validate_value(val, pd["else"], contract_name, fctx, key, result)

    # type
    et = pd.get("type")
    if et:
        errs = _validate_type(val, et, fctx)
        for e in errs:
            result.error("SCHEMA_TYPE", contract_name, key, ctx, e)
        if errs:
            return

    # minLength
    ml = pd.get("minLength")
    if ml is not None and isinstance(val, str) and len(val) < ml:
        result.error("SCHEMA_MINLENGTH", contract_name, key, ctx, f"len {len(val)} < min {ml}")

    # pattern / format
    if isinstance(val, str):
        pat = pd.get("pattern")
        if pat and not re.search(pat, val):
            result.error("SCHEMA_PATTERN", contract_name, key, ctx, f"value {val!r} does not match {pat!r}")
        fmt = pd.get("format")
        if fmt == "uri" and not (val.startswith("http") or val.startswith("file") or val.startswith("/") or val.startswith("chrome")):
            result.error("SCHEMA_FORMAT", contract_name, key, ctx, f"value {val!r} is not a valid URI")

    # enum
    enum = pd.get("enum")
    if enum and val not in enum:
        result.error("SCHEMA_ENUM", contract_name, key, ctx, f"value {val!r} not in {enum}")

    # bounds
    if isinstance(val, (int, float)):
        pmin = pd.get("minimum")
        pmax = pd.get("maximum")
        if pmin is not None and val < pmin:
            result.error("SCHEMA_BOUND", contract_name, key, ctx, f"{val} < min {pmin}")
        if pmax is not None and val > pmax:
            result.error("SCHEMA_BOUND", contract_name, key, ctx, f"{val} > max {pmax}")

    # minItems / uniqueItems (object arrays via canonical JSON)
    if isinstance(val, list):
        mi = pd.get("minItems")
        if mi is not None and len(val) < mi:
            result.error("SCHEMA_MINITEMS", contract_name, key, ctx, f"expected >= {mi}, got {len(val)}")
        ui = pd.get("uniqueItems", False)
        if ui:
            seen = set()
            for item in val:
                sig = json.dumps(item, sort_keys=True, separators=(",", ":")) if not isinstance(item, str) else item
                if sig in seen:
                    result.error("SCHEMA_DUPLICATE", contract_name, key, ctx, "duplicate in array")
                seen.add(sig)


def _schema_cond_matches(data: dict, cond: dict) -> bool:
    """Check whether data matches a conditional schema node (if/not)."""
    required = cond.get("required", [])
    for field in required:
        if field not in data:
            return False
    cprops = cond.get("properties", {})
    for key, pd in cprops.items():
        if key not in data:
            return False
        val = data[key]
        c = pd.get("const")
        if c is not None and val != c:
            return False
        enum = pd.get("enum")
        if enum and val not in enum:
            return False
        pat = pd.get("pattern")
        if pat and isinstance(val, str) and not re.search(pat, val):
            return False
    return True


# ── Drift inspection: runtime ──────────────────────────────────────────


def _drift_runtime(contract: dict, root: Path, result: Result) -> None:
    c = contract
    # Production URL from config.env
    config_env = _must_exist(root, f"{PRODUCTION_ROOT}/etc/sushida-os/config.env",
                             "config.env", result, "runtime")
    if config_env:
        for line in config_env.read_text().splitlines():
            line = line.strip()
            if line.startswith("SUSHIDA_URL="):
                val = line.split("=", 1)[1].strip("\"'")
                expected = c.get("urls", {}).get("sushida_url", "")
                if val != expected:
                    result.error("RUNTIME_URL_MISMATCH", "runtime",
                                 "urls.sushida_url", str(config_env),
                                 f"config.env has {val!r}, contract expects {expected!r}")

    # Chromium managed policy URL allowlist and blocklist
    policy_file = _must_exist(root, f"{PRODUCTION_ROOT}/etc/chromium/policies/managed/sushida-os.json",
                              "Chromium policy", result, "runtime")
    if policy_file:
        policy = _load_json(policy_file)
        nav = c.get("navigation", {})
        contract_allow = set(nav.get("allowlist", []))
        policy_allow = set(policy.get("URLAllowlist", []))
        if contract_allow != policy_allow:
            result.error("RUNTIME_ALLOWLIST_MISMATCH", "runtime",
                         "navigation.allowlist", str(policy_file),
                         f"contract allowlist {contract_allow} != policy {policy_allow}")

        contract_block = set(nav.get("blocklist", []))
        policy_block = set(policy.get("URLBlocklist", []))
        if contract_block != policy_block:
            result.error("RUNTIME_BLOCKLIST_MISMATCH", "runtime",
                         "navigation.blocklist", str(policy_file),
                         f"contract blocklist {contract_block} != policy {policy_block}")

    # Routes — check that valid route values are known
    valid_routes = {"online", "setup", "offline"}
    for route in c.get("routes", []):
        if route not in valid_routes:
            result.error("RUNTIME_UNKNOWN_ROUTE", "runtime", f"routes.{route}",
                         "contract", f"unknown route {route!r}")

    # Navigation content sanity
    allow = c.get("navigation", {}).get("allowlist", [])
    block = c.get("navigation", {}).get("blocklist", [])
    if "*" not in block:
        result.error("RUNTIME_BLOCKLIST_CONTENT", "runtime", "navigation.blocklist",
                     "contract", "blocklist must contain '*'")
    if not any("sushida.net" in e for e in allow):
        result.error("RUNTIME_ALLOWLIST_CONTENT", "runtime", "navigation.allowlist",
                     "contract", "allowlist must contain sushida.net")

    # Route file path referenced in launcher
    runtime_paths = c.get("runtime_paths", {})
    launcher = _must_exist(root, f"{PRODUCTION_ROOT}/usr/local/bin/sushida-launch",
                           "launcher script", result, "runtime")
    if launcher:
        text = launcher.read_text()
        route_file = runtime_paths.get("active_route_file", "")
        if route_file:
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
    build_sh = _must_exist(root, "scripts/build.sh", "build.sh", result, "release")
    if build_sh:
        text = build_sh.read_text()
        for artifact in rc.get("artifacts", []):
            name = artifact["name"]
            if name not in text:
                result.warn("RELEASE_ARTIFACT", "release", f"artifacts.{name}",
                            str(build_sh), f"artifact {name!r} not found in build.sh")

    # Flash script ISO name
    flash_sh = _must_exist(root, "scripts/flash.sh", "flash.sh", result, "release")
    if flash_sh:
        flash_text = flash_sh.read_text()
        iso_name = "sushida-os-amd64.iso"
        if iso_name not in flash_text:
            result.warn("RELEASE_ISO_NAME", "release", "artifacts.iso_name",
                        str(flash_sh), f"ISO name {iso_name!r} not in flash.sh")

    # Package list
    pkg_list = _must_exist(root, "live-build/config/package-lists/kiosk.list.chroot",
                           "package list", result, "release")
    if pkg_list:
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

    # Required service enable and mask from hooks
    enable_hook = _must_exist(root, "live-build/config/hooks/live/020-enable-services.hook.chroot",
                              "enable hook", result, "release")
    if enable_hook:
        etext = enable_hook.read_text()
        for svc in rc.get("required_services", []):
            name = svc["name"]
            state = svc["state"]
            if state == "enabled" and name not in etext:
                result.error("DRIFT_SERVICE_ENABLE", "release", f"required_services.{name}",
                             str(enable_hook), f"service {name} not enabled in hook")

    validate_hook = _must_exist(root, "live-build/config/hooks/live/090-validate-image.hook.chroot",
                                "validate hook", result, "release")
    if validate_hook:
        vtext = validate_hook.read_text()
        for svc in rc.get("required_services", []):
            name = svc["name"]
            state = svc["state"]
            if state == "masked" and name not in vtext:
                result.error("DRIFT_SERVICE_MASK", "release", f"required_services.{name}",
                             str(validate_hook), f"service {name} not found in validate hook")

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

    rt_path = Path(args.runtime_contract) if args.runtime_contract else \
        contracts_dir / RUNTIME_CONTRACT
    rc_path = Path(args.release_contract) if args.release_contract else \
        contracts_dir / RELEASE_CONTRACT
    rt_schema_path = contracts_dir / RUNTIME_SCHEMA
    rc_schema_path = contracts_dir / RELEASE_SCHEMA

    for p in (rt_path, rc_path, rt_schema_path, rc_schema_path):
        if not p.is_file():
            msg = f"file not found: {p}"
            if args.json:
                report = {"ok": False, "errors": [{"code": "FILE_NOT_FOUND", "contract": "", "field": "", "file": str(p), "message": msg}], "warnings": []}
                print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
            else:
                print(f"ERROR: {msg}", file=sys.stderr)
            return 2

    result = Result()

    # Wrap everything in a try/except so --json always produces valid JSON
    try:
        runtime = _load_json(rt_path)
        release = _load_json(rc_path)
        rt_schema = _load_json(rt_schema_path)
        rc_schema = _load_json(rc_schema_path)
    except RuntimeError as exc:
        if args.json:
            report = result.json_report()
            report["ok"] = False
            report["errors"].append({"code": "PARSE_ERROR", "contract": "", "field": "", "file": "", "message": str(exc)})
            print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        _check_schema(runtime, rt_schema, "runtime-contract", result)
        _check_schema(release, rc_schema, "release-contract", result)

        for name, contract, schema in [
            ("runtime", runtime, rt_schema),
            ("release", release, rc_schema),
        ]:
            c_ver = contract.get("schema_version")
            s_ver = schema.get("properties", {}).get("schema_version", {}).get("const")
            if c_ver != s_ver:
                result.error("SCHEMA_VERSION", name, "schema_version", f"{name}-contract.json",
                             f"contract version {c_ver} != schema const {s_ver}")

        for name, data in [("runtime", runtime), ("release", release),
                            ("runtime-schema", rt_schema), ("release-schema", rc_schema)]:
            _check_secrets(data, f"{name}.json", name, result)

        _drift_runtime(runtime, root, result)
        _drift_release(release, root, result)

        handled_runtime_fields = {
            "schema_version", "urls", "runtime_paths", "routes",
            "services", "timeouts", "navigation",
        }
        for key in runtime:
            if key not in handled_runtime_fields:
                result.warn("UNHANDLED_RUNTIME_FIELD", "runtime", key, "runtime-contract.json",
                            f"checker does not inspect field {key!r}")
    except Exception as exc:
        result.error("INTERNAL_ERROR", "", "", "", f"unexpected error: {exc}")

    if args.json:
        report_data = result.json_report()
        report_data["schema_version"] = 1
        print(json.dumps(report_data, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        sys.stdout.write(result.human_report())

    # Exit 2 for internal errors, 1 for contract/drift, 0 for clean
    has_internal = any(e["code"] == "INTERNAL_ERROR" for e in result.errors)
    if has_internal:
        return 2
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
