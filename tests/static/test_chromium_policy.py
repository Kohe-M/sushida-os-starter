import json
import urllib.parse
from pathlib import Path

POLICY_FILE = Path(
    "live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json"
)
CONFIG_ENV = Path(
    "live-build/config/includes.chroot/etc/sushida-os/config.env"
)
LAUNCHER = Path(
    "live-build/config/includes.chroot/usr/local/bin/sushida-launch"
)
SESSION_HELPER = Path(
    "live-build/config/includes.chroot/usr/local/libexec/sushida-session"
)
LIVE_BUILD_DIR = Path("live-build")

REQUIRED_POLICIES: dict[str, tuple] = {
    "DeveloperToolsAvailability": (2, int),
    "BrowserGuestModeEnabled": (False, bool),
    "IncognitoModeAvailability": (1, int),
    "BrowserSignin": (0, int),
    "PasswordManagerEnabled": (False, bool),
    "AutofillAddressEnabled": (False, bool),
    "AutofillCreditCardEnabled": (False, bool),
    "PrintingEnabled": (False, bool),
    "DownloadRestrictions": (3, int),
    "URLBlocklist": (["*"], list),
    "URLAllowlist": (list, list),
}

EXPECTED_ALLOWLIST = {
    "https://.sushida.net:443",
    "file:///usr/share/sushida-os/offline.html",
    "http://127.0.0.1:8787",
}

EXPECTED_BLOCKLIST = {"*", "view-source:*", "chrome://*", "chrome-untrusted://*", "devtools://*"}


def _policy_ordered_pairs() -> list[tuple[str, object]]:
    return json.loads(POLICY_FILE.read_text(), object_pairs_hook=list)


def _policy() -> dict:
    return dict(_policy_ordered_pairs())


def _config_url() -> str:
    for line in CONFIG_ENV.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("SUSHIDA_URL="):
            return stripped.split("=", 1)[1]
    raise AssertionError("SUSHIDA_URL not found in config.env")


def _launcher_patterns() -> list[str]:
    """Return individual URL patterns from the launcher and helper case
    clauses, splitting on | so each alternative is checked separately."""
    patterns: list[str] = []
    for path in (LAUNCHER, SESSION_HELPER):
        content = path.read_text()
        in_case = False
        for line in content.splitlines():
            stripped = line.strip()
            if "case " in stripped and "SUSHIDA_URL" in stripped:
                in_case = True
                continue
            if in_case:
                if stripped == ";;" or stripped.startswith(";;"):
                    continue
                if stripped == "esac" or stripped.startswith("*)") or stripped == "*)":
                    break
                if "https://" in stripped:
                    line_clean = stripped.split("#")[0].strip()
                    # Remove trailing semicolons and closing paren
                    line_clean = line_clean.replace(";;", "").rstrip(")").rstrip(";").strip()
                    for alt in line_clean.split("|"):
                        alt = alt.strip().rstrip(")").strip()
                        if alt.startswith("https://"):
                            patterns.append(alt)
    return patterns


def _relevant_files() -> list[Path]:
    skip = {".html", ".json", ".md"}
    files: list[Path] = []
    for p in LIVE_BUILD_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix in skip:
            continue
        if p.name == ".gitkeep":
            continue
        files.append(p)
    return files


def _has_search_term(term: str) -> list[Path]:
    matches: list[Path] = []
    for f in _relevant_files():
        if term in f.read_text(errors="replace"):
            matches.append(f)
    return matches


# ── valid JSON ──────────────────────────────────────────────────────────────


def test_policy_is_valid_json() -> None:
    p = _policy()
    assert isinstance(p, dict)
    assert len(p) > 0


def test_no_duplicate_keys() -> None:
    pairs = _policy_ordered_pairs()
    keys = [p[0] for p in pairs]
    assert len(keys) == len(set(keys)), f"Duplicate JSON keys: {keys}"


def test_no_comment_keys() -> None:
    p = _policy()
    for key in p:
        assert not key.startswith("_"), f"Non-standard key: {key}"


def test_no_todo_in_file() -> None:
    assert "TODO" not in POLICY_FILE.read_text()


# ── all required policies present with correct type/value ──────────────────


def test_all_required_policies_present() -> None:
    p = _policy()
    for key in REQUIRED_POLICIES:
        assert key in p, f"Missing policy: {key}"
        val, expected_type = REQUIRED_POLICIES[key]
        if isinstance(val, list) and key == "URLBlocklist":
            assert isinstance(p[key], list)
            assert "*" in p[key]
            continue
        if key == "URLAllowlist":
            assert isinstance(p[key], list)
            continue
        assert isinstance(p[key], expected_type), (
            f"{key}: expected {expected_type.__name__}, got {type(p[key]).__name__}"
        )
        if expected_type is bool:
            assert p[key] is val or p[key] == val, f"{key}: expected {val}, got {p[key]}"
        elif expected_type is not list:
            assert p[key] == val, f"{key}: expected {val}, got {p[key]}"


def test_developer_tools_disabled() -> None:
    assert _policy()["DeveloperToolsAvailability"] == 2
    assert type(_policy()["DeveloperToolsAvailability"]) is int


def test_guest_mode_disabled() -> None:
    val = _policy()["BrowserGuestModeEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_incognito_disabled() -> None:
    val = _policy()["IncognitoModeAvailability"]
    assert val == 1
    assert type(val) is int


def test_browser_signin_disabled() -> None:
    val = _policy()["BrowserSignin"]
    assert val == 0
    assert type(val) is int


def test_password_manager_disabled() -> None:
    val = _policy()["PasswordManagerEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_autofill_address_disabled() -> None:
    val = _policy()["AutofillAddressEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_autofill_credit_card_disabled() -> None:
    val = _policy()["AutofillCreditCardEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_printing_disabled() -> None:
    val = _policy()["PrintingEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_downloads_blocked() -> None:
    val = _policy()["DownloadRestrictions"]
    assert val == 3
    assert type(val) is int


# ── URL blocklist — exact entries ──────────────────────────────────────────


def test_url_blocklist_entries() -> None:
    bl = _policy()["URLBlocklist"]
    assert isinstance(bl, list)
    assert set(bl) == EXPECTED_BLOCKLIST, (
        f"URLBlocklist = {set(bl)}, expected {EXPECTED_BLOCKLIST}"
    )
    assert len(bl) == len(EXPECTED_BLOCKLIST)
    assert "chrome://*" in bl
    assert "devtools://*" in bl
    assert "chrome-untrusted://*" in bl


# ── URL allowlist — exact entries ──────────────────────────────────────────


def test_url_allowlist_is_minimal() -> None:
    al = _policy()["URLAllowlist"]
    assert isinstance(al, list)
    assert set(al) == EXPECTED_ALLOWLIST, (
        f"URLAllowlist = {set(al)}, expected {EXPECTED_ALLOWLIST}"
    )
    assert len(al) == len(EXPECTED_ALLOWLIST)


def test_no_loading_html() -> None:
    for entry in _policy()["URLAllowlist"]:
        assert "loading.html" not in entry


def test_only_fixed_loopback_setup_origin_uses_http() -> None:
    for entry in _policy()["URLAllowlist"]:
        if entry.startswith("http://"):
            assert entry == "http://127.0.0.1:8787"


def test_file_filter_has_empty_authority_and_exact_path() -> None:
    for entry in _policy()["URLAllowlist"]:
        if entry.startswith("file://"):
            assert entry == "file:///usr/share/sushida-os/offline.html"
            assert not entry.startswith("file://localhost/")


def test_https_filter_has_exact_host_dot() -> None:
    """The HTTPS filter must use a leading dot for exact host matching."""
    for entry in _policy()["URLAllowlist"]:
        if entry.startswith("https://"):
            assert entry.startswith("https://."), (
                f"HTTPS filter must start with leading dot: {entry}"
            )


def test_https_filter_has_explicit_port() -> None:
    """The HTTPS filter must specify port 443 explicitly."""
    for entry in _policy()["URLAllowlist"]:
        if entry.startswith("https://"):
            assert ":443" in entry, (
                f"HTTPS filter must specify port 443: {entry}"
            )


def test_https_filter_no_path_wildcard() -> None:
    """The HTTPS filter must not carry a path pattern
    (path omitted = all paths in Chromium URL filter format)."""
    for entry in _policy()["URLAllowlist"]:
        if entry.startswith("https://"):
            # After host:port there must be no /path or /*
            host_port = entry.split("://", 1)[1]
            assert "/" not in host_port, (
                f"HTTPS filter must not have explicit path: {entry}"
            )


def test_https_filter_single_entry() -> None:
    https_entries = [
        e for e in _policy()["URLAllowlist"] if e.startswith("https://")
    ]
    assert len(https_entries) == 1, (
        f"Expected exactly 1 HTTPS filter, got {len(https_entries)}: {https_entries}"
    )


# ── config.env boundary — structured URL parsing ──────────────────────────


def test_config_env_default_url_structure() -> None:
    """The default SUSHIDA_URL must be within the official origin."""
    url = _config_url()
    parsed = urllib.parse.urlsplit(url)
    assert parsed.scheme == "https", f"Scheme must be https: {url}"
    assert parsed.hostname == "sushida.net", f"Host must be sushida.net: {url}"
    assert parsed.port is None or parsed.port == 443, (
        f"Port must be default (443): {url}"
    )
    assert parsed.username is None, f"Username in URL: {url}"
    assert parsed.password is None, f"Password in URL: {url}"
    assert parsed.fragment == "", f"Fragment in URL: {url}"


# ── launcher patterns — exact alternatives ─────────────────────────────────


def test_launcher_exact_patterns() -> None:
    """The launcher must accept exactly three https://sushida.net patterns."""
    pats = _launcher_patterns()
    expected = {"https://sushida.net", "https://sushida.net/", "https://sushida.net/*"}
    assert set(pats) == expected, (
        f"Launcher patterns = {set(pats)}, expected {expected}"
    )


def test_launcher_no_http() -> None:
    for pat in _launcher_patterns():
        assert not pat.startswith("http://"), f"http:// in launcher: {pat}"


def test_launcher_no_subdomain() -> None:
    for pat in _launcher_patterns():
        assert pat.startswith("https://sushida.net"), (
            f"Unexpected host in launcher: {pat}"
        )


def test_launcher_no_file() -> None:
    for pat in _launcher_patterns():
        assert not pat.startswith("file://")


def test_launcher_no_javascript() -> None:
    for pat in _launcher_patterns():
        assert not pat.startswith("javascript:")


def test_launcher_no_data() -> None:
    for pat in _launcher_patterns():
        assert not pat.startswith("data:")


# ── forbidden flags in build config ────────────────────────────────────────


def test_no_no_sandbox_in_build_config() -> None:
    matches = _has_search_term("--no-sandbox")
    assert len(matches) == 0, f"--no-sandbox found in: {matches}"


def test_no_disable_gpu_in_build_config() -> None:
    matches = _has_search_term("--disable-gpu")
    assert len(matches) == 0, f"--disable-gpu found in: {matches}"
