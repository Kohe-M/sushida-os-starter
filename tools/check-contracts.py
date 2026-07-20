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
import stat
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

    # Unsupported keyword detection — scans schema node only.  A recursive
    # pass is called separately before validation (see _scan_schema_keywords).
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
                _validate_value(item, items_def, contract_name, f"{ctx}.{key}", f"{key}[{i}]", result)
                if isinstance(item, dict) and items_def.get("properties", {}):
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

# Production sources the runtime adapters compare contract values against.
RUNTIME_SOURCE_FILES = {
    "launch": f"{PRODUCTION_ROOT}/usr/local/bin/sushida-launch",
    "netwatch": f"{PRODUCTION_ROOT}/usr/local/bin/sushida-network-watch",
    "navwatch": f"{PRODUCTION_ROOT}/usr/local/bin/sushida-navigation-watch",
    "session": f"{PRODUCTION_ROOT}/usr/local/libexec/sushida-session",
    "wifi": f"{PRODUCTION_ROOT}/usr/local/libexec/sushida-wifi-setup",
    "configprep": f"{PRODUCTION_ROOT}/usr/local/libexec/sushida-config-prepare",
}

# Timeout adapters: (contract field, source key, regex template, min matches).
# ``{value}`` is replaced by _num_pattern() so JSON integers match both the
# ``40`` and ``40.0`` literal forms used in the Python/shell sources.
_TIMEOUT_ADAPTERS = (
    ("wifi_command_default_timeout_seconds", "wifi",
     r"COMMAND_TIMEOUT_SECONDS\s*=\s*{value}\b", 1),
    # Both nmcli activation call sites must keep the contract values.
    ("wifi_activation_wait_seconds", "wifi",
     r'"--wait",\s*"{value}"', 2),
    ("wifi_activation_process_timeout_seconds", "wifi",
     r'"up"[\s\S]{0,160}?timeout={value}\b', 2),
    ("restore_backoff_min_seconds", "wifi",
     r"BACKOFF_MIN\s*=\s*{value}\b", 1),
    ("restore_backoff_max_seconds", "wifi",
     r"BACKOFF_MAX\s*=\s*{value}\b", 1),
    ("restore_max_retries", "wifi",
     r"MAX_RETRIES\s*=\s*{value}\b", 1),
    ("restore_deadline_seconds", "wifi",
     r"deadline\s*=\s*time\.monotonic\(\)\s*\+\s*{value}\b", 1),
    ("nav_poll_interval_seconds", "navwatch",
     r"DEFAULT_POLL_SECONDS\s*=\s*{value}\b", 1),
    ("nav_cooldown_seconds", "navwatch",
     r"DEFAULT_COOLDOWN_SECONDS\s*=\s*{value}\b", 1),
    ("http_read_timeout_seconds", "wifi",
     r"REQUEST_READ_TIMEOUT_SECONDS\s*=\s*{value}\b", 1),
    ("http_max_request_bytes", "wifi",
     r"MAX_REQUEST_BYTES\s*=\s*{value}\b", 1),
    ("session_audio_timeout_seconds", "session",
     r"_raw_at={value}\b", 1),
)


def _num_pattern(value: Any) -> str:
    """Regex fragment matching the production literal of a contract number.

    JSON integers may be written as either ``40`` or ``40.0`` in Python
    sources; non-integer floats keep their exact literal form.
    """
    if isinstance(value, bool):
        return re.escape(str(value))
    if isinstance(value, int):
        return rf"(?:{value}|{value}\.0)"
    if isinstance(value, float):
        if value.is_integer():
            return rf"(?:{int(value)}|{int(value)}\.0)"
        return re.escape(str(value))
    return re.escape(str(value))


def _load_sources(root: Path, mapping: dict[str, str], result: Result,
                  contract_name: str, must_exist: bool = True) -> tuple[dict[str, str], dict[str, str]]:
    """Read production sources once; return (texts, labels) keyed identically."""
    texts: dict[str, str] = {}
    labels: dict[str, str] = {}
    for key, rel in mapping.items():
        if must_exist:
            path = _must_exist(root, rel, key, result, contract_name)
            if path is None:
                continue
        else:
            path = root / rel
            if not path.is_file():
                continue
        texts[key] = path.read_text(encoding="utf-8", errors="replace")
        labels[key] = rel
    return texts, labels


def _expect_pattern(texts: dict[str, str], labels: dict[str, str], key: str,
                    pattern: str, result: Result, code: str, field: str,
                    message: str, min_count: int = 1) -> None:
    """Record an error unless a production source matches pattern often enough."""
    text = texts.get(key)
    if text is None:
        return  # a missing source is reported separately
    found = len(re.findall(pattern, text, re.MULTILINE))
    if found < min_count:
        result.error(code, "runtime", field, labels.get(key, key),
                     f"{message} ({found} match(es), need {min_count})")


def _drift_urls(urls: dict, texts: dict[str, str], labels: dict[str, str],
                result: Result) -> None:
    setup = urls.get("setup_url", "")
    offline = urls.get("offline_url", "")
    for key in ("launch", "session"):
        if setup:
            _expect_pattern(texts, labels, key, re.escape(setup), result,
                            "DRIFT_URL", "urls.setup_url",
                            f"setup URL {setup!r} not found")
        if offline:
            _expect_pattern(texts, labels, key, re.escape(offline), result,
                            "DRIFT_URL", "urls.offline_url",
                            f"offline URL {offline!r} not found")
    # The Wi-Fi backend listen port must match the setup URL port.
    if setup:
        port = urlsplit(setup).port
        if port is not None:
            _expect_pattern(texts, labels, "wifi", rf"^PORT\s*=\s*{port}\b",
                            result, "DRIFT_URL", "urls.setup_url",
                            f"wifi backend PORT does not match setup URL port {port}")


def _drift_runtime_paths(rpaths: dict, services: dict, texts: dict[str, str],
                         labels: dict[str, str], unit_texts: dict[str, str],
                         unit_labels: dict[str, str], result: Result) -> None:
    runtime_dir = rpaths.get("runtime_dir", "")
    if runtime_dir:
        for key in ("launch", "netwatch"):
            _expect_pattern(texts, labels, key,
                            rf'PROD_RUNTIME="{re.escape(runtime_dir)}"', result,
                            "DRIFT_PATH", "runtime_paths.runtime_dir",
                            f"runtime dir {runtime_dir!r} not declared")
        _expect_pattern(texts, labels, "navwatch",
                        rf'PROD_RUNTIME\s*=\s*Path\("{re.escape(runtime_dir)}"\)',
                        result, "DRIFT_PATH", "runtime_paths.runtime_dir",
                        f"runtime dir {runtime_dir!r} not declared")
        kiosk_unit = services.get("kiosk_service", "")
        if kiosk_unit:
            _expect_pattern(unit_texts, unit_labels, kiosk_unit,
                            rf"^RuntimeDirectory={re.escape(os.path.basename(runtime_dir))}$",
                            result, "DRIFT_PATH", "runtime_paths.runtime_dir",
                            f"kiosk unit RuntimeDirectory != {runtime_dir!r}")

    def _check_child_file(field: str, parent: str, readers: tuple[str, ...]) -> None:
        value = rpaths.get(field, "")
        if not value:
            return
        if parent and os.path.dirname(value) != parent:
            result.error("DRIFT_PATH", "runtime", f"runtime_paths.{field}", "contract",
                         f"{field} {value!r} is not inside {parent!r}")
        base = os.path.basename(value)
        for key in readers:
            _expect_pattern(texts, labels, key, re.escape(base), result,
                            "DRIFT_PATH", f"runtime_paths.{field}",
                            f"{field} basename {base!r} not referenced")

    _check_child_file("active_route_file", runtime_dir, ("launch", "netwatch"))
    _check_child_file("time_sync_marker", runtime_dir, ("launch", "netwatch"))

    wifi_setup_dir = rpaths.get("wifi_setup_runtime_dir", "")
    csrf_file = rpaths.get("csrf_token_file", "")
    if wifi_setup_dir and csrf_file and os.path.dirname(csrf_file) != wifi_setup_dir:
        result.error("DRIFT_PATH", "runtime", "runtime_paths.csrf_token_file", "contract",
                     f"csrf_token_file {csrf_file!r} is not inside {wifi_setup_dir!r}")
    if csrf_file:
        _expect_pattern(texts, labels, "wifi",
                        rf'CSRF_TOKEN_FILE\s*=\s*Path\("{re.escape(csrf_file)}"\)',
                        result, "DRIFT_PATH", "runtime_paths.csrf_token_file",
                        f"CSRF token file {csrf_file!r} not declared")
    if wifi_setup_dir:
        wifi_unit = services.get("wifi_setup_service", "")
        if wifi_unit:
            _expect_pattern(unit_texts, unit_labels, wifi_unit,
                            rf"^RuntimeDirectory={re.escape(os.path.basename(wifi_setup_dir))}$",
                            result, "DRIFT_PATH", "runtime_paths.wifi_setup_runtime_dir",
                            f"wifi-setup unit RuntimeDirectory != {wifi_setup_dir!r}")

    config_mount = rpaths.get("config_mount_path", "")
    if config_mount:
        _expect_pattern(texts, labels, "wifi",
                        rf'CONFIG_MOUNT\s*=\s*Path\("{re.escape(config_mount)}"\)',
                        result, "DRIFT_PATH", "runtime_paths.config_mount_path",
                        f"config mount {config_mount!r} not declared")
        _expect_pattern(texts, labels, "configprep",
                        rf'CONFIG_MOUNT="{re.escape(config_mount)}"',
                        result, "DRIFT_PATH", "runtime_paths.config_mount_path",
                        f"config mount {config_mount!r} not declared")
        mount_unit = services.get("config_mount_unit", "")
        if mount_unit:
            _expect_pattern(unit_texts, unit_labels, mount_unit,
                            rf"^Where={re.escape(config_mount)}$",
                            result, "DRIFT_PATH", "runtime_paths.config_mount_path",
                            f"mount unit Where= != {config_mount!r}")

    storage_status = rpaths.get("config_storage_status", "")
    if storage_status:
        _expect_pattern(texts, labels, "wifi",
                        rf'STORAGE_STATUS\s*=\s*Path\("{re.escape(storage_status)}"\)',
                        result, "DRIFT_PATH", "runtime_paths.config_storage_status",
                        f"storage status path {storage_status!r} not declared")
        _expect_pattern(texts, labels, "configprep",
                        rf'STATUS_DIR="{re.escape(os.path.dirname(storage_status))}"',
                        result, "DRIFT_PATH", "runtime_paths.config_storage_status",
                        "config-prepare STATUS_DIR mismatch")
        _expect_pattern(texts, labels, "configprep",
                        re.escape(os.path.basename(storage_status)),
                        result, "DRIFT_PATH", "runtime_paths.config_storage_status",
                        "config-prepare status file basename mismatch")

    credential = rpaths.get("credential_file", "")
    if credential and config_mount:
        rel = os.path.relpath(credential, config_mount)
        parts = rel.split("/")
        if rel.startswith("..") or len(parts) != 2:
            result.error("DRIFT_PATH", "runtime", "runtime_paths.credential_file",
                         "contract",
                         f"credential_file {credential!r} is not <config_mount>/<dir>/<file>")
        else:
            _expect_pattern(texts, labels, "wifi",
                            rf'CONFIG_DIR\s*=\s*CONFIG_MOUNT\s*/\s*"{re.escape(parts[0])}"',
                            result, "DRIFT_PATH", "runtime_paths.credential_file",
                            f"credential dir component {parts[0]!r} not declared")
            _expect_pattern(texts, labels, "wifi",
                            rf'CONFIG_FILE\s*=\s*CONFIG_DIR\s*/\s*"{re.escape(parts[1])}"',
                            result, "DRIFT_PATH", "runtime_paths.credential_file",
                            f"credential file component {parts[1]!r} not declared")

    profile_dir = rpaths.get("chromium_profile_dir", "")
    if profile_dir:
        if runtime_dir and os.path.dirname(profile_dir) != runtime_dir:
            result.error("DRIFT_PATH", "runtime", "runtime_paths.chromium_profile_dir",
                         "contract",
                         f"chromium_profile_dir {profile_dir!r} is not inside {runtime_dir!r}")
        profile_base = os.path.basename(profile_dir)
        _expect_pattern(texts, labels, "launch", re.escape(profile_base), result,
                        "DRIFT_PATH", "runtime_paths.chromium_profile_dir",
                        f"profile dir {profile_base!r} not created by launcher")
        _expect_pattern(texts, labels, "session",
                        rf"--user-data-dir=\S*{re.escape(profile_base)}\b", result,
                        "DRIFT_PATH", "runtime_paths.chromium_profile_dir",
                        f"--user-data-dir does not end in {profile_base!r}")

    sessions_dir = rpaths.get("chromium_sessions_dir", "")
    if sessions_dir and profile_dir:
        rel = os.path.relpath(sessions_dir, profile_dir)
        if rel.startswith(".."):
            result.error("DRIFT_PATH", "runtime", "runtime_paths.chromium_sessions_dir",
                         "contract",
                         f"chromium_sessions_dir {sessions_dir!r} is not inside {profile_dir!r}")
        else:
            segments = [os.path.basename(profile_dir), *rel.split("/")]
            pattern = rf'SESSIONS_SUBDIR\s*=\s*Path\("{re.escape(segments[0])}"\)'
            for segment in segments[1:]:
                pattern += rf'\s*/\s*"{re.escape(segment)}"'
            _expect_pattern(texts, labels, "navwatch", pattern, result,
                            "DRIFT_PATH", "runtime_paths.chromium_sessions_dir",
                            f"sessions dir chain {'/'.join(segments)!r} not declared")


def _drift_timeouts(timeouts: dict, texts: dict[str, str], labels: dict[str, str],
                    result: Result) -> None:
    for field, key, template, min_count in _TIMEOUT_ADAPTERS:
        value = timeouts.get(field)
        if value is None:
            continue
        pattern = template.replace("{value}", _num_pattern(value))
        _expect_pattern(texts, labels, key, pattern, result,
                        "DRIFT_TIMEOUT", f"timeouts.{field}",
                        f"production literal for {field} != contract {value!r}",
                        min_count=min_count)


def _drift_routes(routes: list, texts: dict[str, str], labels: dict[str, str],
                  result: Result) -> None:
    expected = set(routes)
    if not expected:
        return
    launch = texts.get("launch")
    if launch is not None:
        found = set(re.findall(r'ACTIVE_ROUTE="([a-z][a-z-]*)"', launch))
        if found != expected:
            result.error("DRIFT_ROUTE", "runtime", "routes", labels["launch"],
                         f"launcher routes {sorted(found)} != contract {sorted(expected)}")
    netwatch = texts.get("netwatch")
    if netwatch is not None:
        found = set(re.findall(r"printf '%s\\n' ([a-z][a-z-]*)\b", netwatch))
        case_match = re.search(r'case\s+"\$route"\s+in\s+([a-z|]+)\)', netwatch)
        if case_match:
            found |= set(case_match.group(1).split("|"))
        if found != expected:
            result.error("DRIFT_ROUTE", "runtime", "routes", labels["netwatch"],
                         f"network watcher routes {sorted(found)} != contract {sorted(expected)}")


def _drift_runtime(contract: dict, root: Path, result: Result) -> None:
    c = contract
    urls = c.get("urls", {})
    rpaths = c.get("runtime_paths", {})
    services = c.get("services", {})
    timeouts = c.get("timeouts", {})

    # Production URL from config.env
    # The production launcher and network-watch parse config.env verbatim:
    # only CR is stripped; quotes and leading whitespace are NOT removed.
    # Unknown keys, lines without '=', and duplicate keys all cause a startup
    # failure, so the checker must reject them too.
    #
    # Error messages must never include config.env line content or values
    # because they could contain secrets.  Report line numbers only.
    config_env = _must_exist(root, f"{PRODUCTION_ROOT}/etc/sushida-os/config.env",
                             "config.env", result, "runtime")
    if config_env:
        allowed = {"SUSHIDA_URL", "NETWORK_CHECK_INTERVAL_SECONDS", "NETWORK_SETUP_GRACE_SECONDS"}
        seen: set[str] = set()
        for line_number, raw_line in enumerate(
                config_env.read_text().splitlines(), start=1):
            line = raw_line.rstrip("\r")
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                result.error("DRIFT_CONFIG_FORMAT", "runtime", "config.env",
                             str(config_env),
                             f"invalid config line without '=' at line {line_number}")
                continue
            key, value = line.split("=", 1)
            if key not in allowed:
                result.error("DRIFT_CONFIG_KEY", "runtime", "config.env",
                             str(config_env),
                             f"unknown config key at line {line_number}")
                continue
            if key in seen:
                result.error("DRIFT_CONFIG_DUPLICATE", "runtime", key,
                             str(config_env),
                             f"duplicate config key: {key}")
                continue
            seen.add(key)
            if key == "SUSHIDA_URL":
                expected = urls.get("sushida_url", "")
                if value != expected:
                    result.error("RUNTIME_URL_MISMATCH", "runtime",
                                 "urls.sushida_url", str(config_env),
                                 "config.env SUSHIDA_URL does not match the runtime contract")
            elif key == "NETWORK_CHECK_INTERVAL_SECONDS":
                expected = str(timeouts.get("network_check_interval_seconds", ""))
                if value != expected:
                    result.error("DRIFT_TIMEOUT", "runtime", "timeouts.network_check_interval_seconds",
                                 str(config_env), "config.env NETWORK_CHECK_INTERVAL_SECONDS does not match the runtime contract")
            elif key == "NETWORK_SETUP_GRACE_SECONDS":
                expected = str(timeouts.get("network_setup_grace_seconds", ""))
                if value != expected:
                    result.error("DRIFT_TIMEOUT", "runtime", "timeouts.network_setup_grace_seconds",
                                 str(config_env), "config.env NETWORK_SETUP_GRACE_SECONDS does not match the runtime contract")
        if "SUSHIDA_URL" not in seen:
            result.error("DRIFT_URL", "runtime", "urls.sushida_url", str(config_env),
                         "config.env missing SUSHIDA_URL")
        if "NETWORK_CHECK_INTERVAL_SECONDS" not in seen:
            result.error("DRIFT_TIMEOUT", "runtime", "timeouts.network_check_interval_seconds",
                         str(config_env), "config.env missing NETWORK_CHECK_INTERVAL_SECONDS")
        if "NETWORK_SETUP_GRACE_SECONDS" not in seen:
            result.error("DRIFT_TIMEOUT", "runtime", "timeouts.network_setup_grace_seconds",
                         str(config_env), "config.env missing NETWORK_SETUP_GRACE_SECONDS")

    # Production runtime sources shared by the adapters below.  Unit files are
    # loaded silently: their existence is enforced by the services loop.
    texts, labels = _load_sources(root, RUNTIME_SOURCE_FILES, result, "runtime")
    unit_map = {
        name: f"{PRODUCTION_ROOT}/etc/systemd/system/{name}"
        for name in services.values()
    }
    unit_texts, unit_labels = _load_sources(root, unit_map, result, "runtime",
                                            must_exist=False)

    _drift_urls(urls, texts, labels, result)
    _drift_runtime_paths(rpaths, services, texts, labels, unit_texts, unit_labels, result)
    _drift_timeouts(timeouts, texts, labels, result)
    _drift_routes(c.get("routes", []), texts, labels, result)

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

    # Service names — check custom unit files exist
    system_services = {"systemd-timesyncd.service", "NetworkManager.service"}
    for key, service_name in services.items():
        if service_name in system_services:
            continue  # installed by Debian package, not in includes.chroot
        unit_path = root / PRODUCTION_ROOT / "etc/systemd/system" / service_name
        if not unit_path.is_file() and not unit_path.is_symlink():
            result.error("RUNTIME_SERVICE_MISSING", "runtime",
                         f"services.{key}", str(unit_path),
                         f"service file not found: {unit_path}")


# ── Drift inspection: release ──────────────────────────────────────────

KNOWN_METADATA_FORMATS = {"git-sha", "date-time", "sha256"}


def _drift_release_mappings(rc: dict, root: Path, result: Result) -> None:
    """Static consistency of source_image_mappings (check-only, no ISO access)."""
    for mapping in rc.get("source_image_mappings", []):
        src_rel = mapping["source"]
        image_path = mapping["image_path"]
        region = mapping["region"]
        label = f"source_image_mappings.{src_rel}"
        if region == "squashfs":
            # source must be exactly includes.chroot + image_path
            expected_src = f"{PRODUCTION_ROOT}{image_path}"
            if src_rel != expected_src:
                result.error("DRIFT_MAPPING_PATH", "release", label, src_rel,
                             f"source {src_rel!r} does not correspond to image path "
                             f"{image_path!r} (expected {expected_src!r})")
            # includes.chroot files are installed as root:root by live-build
            if mapping.get("owner") != "root" or mapping.get("group") != "root":
                result.error("DRIFT_MAPPING_OWNER", "release", label, src_rel,
                             "squashfs mappings must declare owner/group root:root")
        if mapping.get("current_verification") == "exact" and \
                mapping.get("comparison") not in ("cmp", "sha256"):
            result.error("DRIFT_COMPARISON", "release", label, src_rel,
                         "current_verification 'exact' requires content comparison "
                         f"(cmp/sha256), got {mapping.get('comparison')!r}")
        src = root / src_rel
        if not src.is_file() or src.is_symlink():
            continue  # existence is reported by the source-existence check
        actual_mode = f"{stat.S_IMODE(src.stat().st_mode):04o}"
        if actual_mode != mapping.get("mode"):
            result.error("DRIFT_MAPPING_MODE", "release", label, src_rel,
                         f"source mode {actual_mode} != contract {mapping.get('mode')!r}")


def _drift_release_iso_paths(rc: dict, verify_text: str, result: Result) -> None:
    """required_iso_paths ↔ mappings consistency and iso-root coverage."""
    mappings_by_image: dict[str, dict] = {}
    for mapping in rc.get("source_image_mappings", []):
        mappings_by_image.setdefault(mapping["image_path"], mapping)
    for entry in rc.get("required_iso_paths", []):
        path = entry["path"]
        label = f"required_iso_paths.{path}"
        if entry.get("match_type") == "regex":
            pattern = entry.get("path_pattern", "")
            try:
                rx = re.compile(pattern)
            except re.error as exc:
                result.error("DRIFT_PATH_PATTERN", "release", label, "contract",
                             f"invalid path_pattern: {exc}")
            else:
                if not rx.search(path):
                    result.error("DRIFT_PATH_PATTERN", "release", label, "contract",
                                 f"path_pattern {pattern!r} does not match path {path!r}")
        if entry["region"] == "squashfs":
            mapping = mappings_by_image.get(path)
            if mapping is None:
                result.error("DRIFT_ISO_PATH", "release", label, "contract",
                             f"required squashfs path {path!r} has no source image mapping")
                continue
            for attr in ("region", "file_type", "required", "security_critical"):
                if mapping.get(attr) != entry.get(attr):
                    result.error("DRIFT_ISO_PATH_ATTR", "release", label, "contract",
                                 f"mapping {attr}={mapping.get(attr)!r} != "
                                 f"iso path {attr}={entry.get(attr)!r}")
        elif entry["region"] == "iso-root":
            # verify-iso.sh writes initrd/squashfs in regex-escaped form
            if path not in verify_text and re.escape(path) not in verify_text:
                result.error("DRIFT_ISO_PATH", "release", label, "scripts/verify-iso.sh",
                             f"required ISO path {path!r} not referenced by verify-iso.sh")


def _drift_release_metadata(meta: dict, result: Result) -> None:
    """static_values/formats key consistency (value drift is checked separately)."""
    req_fields = meta.get("required_fields", [])
    for field in meta.get("static_values", {}):
        if field not in req_fields:
            result.error("DRIFT_METADATA_STATIC", "release",
                         f"metadata.static_values.{field}", "contract",
                         f"static value declared for non-required field {field!r}")
    for field, fmt in meta.get("formats", {}).items():
        if field not in req_fields:
            result.error("DRIFT_METADATA_FORMAT", "release",
                         f"metadata.formats.{field}", "contract",
                         f"format declared for non-required field {field!r}")
        if fmt not in KNOWN_METADATA_FORMATS:
            result.error("DRIFT_METADATA_FORMAT", "release",
                         f"metadata.formats.{field}", "contract",
                         f"unknown format {fmt!r} (known: {sorted(KNOWN_METADATA_FORMATS)})")


def _drift_release(contract: dict, root: Path, result: Result) -> None:
    rc = contract

    # Build script artifact names
    build_sh = _must_exist(root, "scripts/build.sh", "build.sh", result, "release")
    if build_sh:
        text = build_sh.read_text()
        for artifact in rc.get("artifacts", []):
            name = artifact["name"]
            if name not in text:
                result.error("RELEASE_ARTIFACT", "release", f"artifacts.{name}",
                            str(build_sh), f"artifact {name!r} not found in build.sh")

    # Flash script ISO name
    flash_sh = _must_exist(root, "scripts/flash.sh", "flash.sh", result, "release")
    if flash_sh:
        flash_text = flash_sh.read_text()
        iso_name = "sushida-os-amd64.iso"
        if iso_name not in flash_text:
            result.error("RELEASE_ISO_NAME", "release", "artifacts.iso_name",
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

    # Verify-iso.sh, clean.sh, run-qemu.sh — check artifact references by boolean
    _scripts_checks = [
        ("verify-iso.sh", "scripts/verify-iso.sh", "verify"),
        ("clean.sh", "scripts/clean.sh", "clean"),
        ("run-qemu.sh", "scripts/run-qemu.sh", None),
    ]
    _script_texts: dict[str, str] = {}
    for script_name, script_rel, boolean_key in _scripts_checks:
        sp = _must_exist(root, script_rel, script_name, result, "release")
        if sp:
            _text = sp.read_text()
            _script_texts[script_name] = _text
            for artifact in rc.get("artifacts", []):
                name = artifact["name"]
                # run-qemu.sh should reference the ISO
                if boolean_key is None:
                    if "iso" in name and name not in _text:
                        result.error("RELEASE_ARTIFACT_REF", "release", f"artifacts.{name}",
                                     str(sp), f"ISO artifact {name!r} not in {script_name}")
                elif artifact.get(boolean_key, False) and name not in _text:
                    result.error("RELEASE_ARTIFACT_REF", "release", f"artifacts.{name}",
                                 str(sp), f"artifact {name!r} ({boolean_key}) not in {script_name}")
                elif not artifact.get(boolean_key, False) and name in _text:
                    result.error("RELEASE_ARTIFACT_REF_UNEXPECTED", "release", f"artifacts.{name}",
                                str(sp), f"artifact {name!r} ({boolean_key}=false) appears in {script_name}")

    # Artifact checksum and publish verification
    for artifact in rc.get("artifacts", []):
        name = artifact["name"]
        if artifact.get("checksum") and "sha256sum" not in (build_sh.read_text() if build_sh else ""):
            result.error("RELEASE_CHECKSUM", "release", f"artifacts.{name}.checksum",
                         "contract", f"artifact {name!r} requires checksum but no sha256sum in build.sh")
        if artifact.get("publish") and "artifacts" not in (build_sh.read_text() if build_sh else ""):
            result.error("RELEASE_PUBLISH", "release", f"artifacts.{name}.publish",
                         "contract", f"artifact {name!r} requires publish but no artifacts/ in build.sh")

    # Metadata required_fields — dictionary-based adapter
    meta = rc.get("metadata", {})
    static_vals = meta.get("static_values", {})
    req_fields = meta.get("required_fields", [])
    metadata_tokens: dict[str, tuple[str, ...]] = {
        "git_commit": ("rev-parse",),
        "git_dirty": ("git_dirty",),
        "build_timestamp": ("date -u",),
        "architecture": (),
        "debian_release": (),
        "chromium_version": ("chromium_version", "package_version chromium"),
        "cage_version": ("cage_version", "package_version cage"),
        "live_build_version": ("lb --version", "live_build_version"),
        "iso_sha256": ("sha256sum",),
    }
    if build_sh:
        btext = build_sh.read_text()
        for field in req_fields:
            if field in static_vals:
                expected_val = str(static_vals[field])
                # Match the field/value pair in either production form:
                #   architecture=amd64
                #   --arg architecture "amd64"   (jq argument style in build.sh)
                patterns = (
                    rf"\b{re.escape(field)}\s*=\s*['\"]?{re.escape(expected_val)}['\"]?(?=\s|$)",
                    rf"--arg\s+{re.escape(field)}\s+['\"]{re.escape(expected_val)}['\"]",
                )
                if not any(re.search(pattern, btext, re.MULTILINE) for pattern in patterns):
                    result.error("DRIFT_METADATA_STATIC", "release",
                                 f"metadata.static_values.{field}", str(build_sh),
                                 f"static value {expected_val!r} for field {field!r} "
                                 "not found as a field/value pair in build.sh")
                continue
            tokens = metadata_tokens.get(field)
            if tokens is None:
                result.error("DRIFT_METADATA_UNSUPPORTED", "release",
                             f"metadata.required_fields.{field}",
                             str(build_sh),
                             f"field {field!r} has no adapter; implement or remove")
            elif tokens:
                if not any(tok in btext for tok in tokens):
                    result.error("DRIFT_METADATA", "release",
                                 f"metadata.required_fields.{field}",
                                 str(build_sh),
                                 f"field {field!r} generation not found in build.sh")

    # Source-image mappings: check source files exist
    for mapping in rc.get("source_image_mappings", []):
        src = root / mapping["source"]
        if not src.is_file() and not src.is_symlink():
            result.error("RELEASE_MAPPING_SOURCE", "release",
                         f"source_image_mappings.{mapping['source']}", str(src),
                         f"mapping source not found: {mapping['source']}")

    _drift_release_mappings(rc, root, result)
    _drift_release_iso_paths(rc, _script_texts.get("verify-iso.sh", ""), result)
    _drift_release_metadata(meta, result)


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
