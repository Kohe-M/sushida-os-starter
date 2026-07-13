import json
from pathlib import Path

POLICY_FILE = Path(
    "live-build/config/includes.chroot/etc/chromium/policies/managed/sushida-os.json"
)
LIVE_BUILD_DIR = Path("live-build")


def _policy() -> dict:
    with open(POLICY_FILE) as f:
        return json.load(f)


def _relevant_files() -> list[Path]:
    """Return files under live-build that could contain Chromium launch arguments.

    Skips files that are web content (.html), Chromium policy (.json),
    documentation (.md), or empty markers (.gitkeep).
    Raises OSError if a relevant file cannot be read.
    """
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
    """Search relevant files for *term*.  OSError/ValueError propagates."""
    matches: list[Path] = []
    for f in _relevant_files():
        if term in f.read_text(errors="replace"):
            matches.append(f)
    return matches


def test_policy_is_valid_json() -> None:
    p = _policy()
    assert isinstance(p, dict)
    assert len(p) > 0


def test_developer_tools_disabled() -> None:
    p = _policy()
    val = p["DeveloperToolsAvailability"]
    assert val == 2
    assert type(val) is int


def test_guest_mode_disabled() -> None:
    p = _policy()
    val = p["BrowserGuestModeEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_incognito_disabled() -> None:
    p = _policy()
    val = p["IncognitoModeAvailability"]
    assert val == 1
    assert type(val) is int


def test_browser_signin_disabled() -> None:
    p = _policy()
    val = p["BrowserSignin"]
    assert val == 0
    assert type(val) is int


def test_password_manager_disabled() -> None:
    p = _policy()
    val = p["PasswordManagerEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_autofill_address_disabled() -> None:
    p = _policy()
    val = p["AutofillAddressEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_autofill_credit_card_disabled() -> None:
    p = _policy()
    val = p["AutofillCreditCardEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_printing_disabled() -> None:
    p = _policy()
    val = p["PrintingEnabled"]
    assert val is False
    assert isinstance(val, bool)


def test_downloads_blocked() -> None:
    p = _policy()
    val = p["DownloadRestrictions"]
    assert val == 3
    assert type(val) is int


def test_url_blocklist_denies_all() -> None:
    p = _policy()
    assert "URLBlocklist" in p
    bl = p["URLBlocklist"]
    assert isinstance(bl, list)
    assert "*" in bl


def test_url_allowlist_is_minimal() -> None:
    al = _policy()["URLAllowlist"]
    assert isinstance(al, list)
    assert len(al) == 2, f"Expected exactly 2 entries, got {len(al)}: {al}"
    assert set(al) == {
        "https://sushida.net/*",
        "file:///usr/share/sushida-os/offline.html",
    }


def test_no_no_sandbox_in_build_config() -> None:
    matches = _has_search_term("--no-sandbox")
    assert len(matches) == 0, f"--no-sandbox found in: {matches}"


def test_no_disable_gpu_in_build_config() -> None:
    matches = _has_search_term("--disable-gpu")
    assert len(matches) == 0, f"--disable-gpu found in: {matches}"
