import re
from pathlib import Path

PACKAGE_LIST = Path(
    "live-build/config/package-lists/kiosk.list.chroot"
)

# Valid Debian package name: lowercase alphanumeric and [+-.]
PKG_RE = re.compile(r"^[a-z0-9][a-z0-9+\-.]+$")


def _packages() -> list[str]:
    """Return parsed package names, ignoring comments and blank lines.

    Each content line must contain exactly one valid Debian package token.
    """
    pkgs: list[str] = []
    for lineno, line in enumerate(PACKAGE_LIST.read_text().splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        assert len(tokens) == 1, (
            f"Line {lineno}: expected 1 package, got {len(tokens)}: {line}"
        )
        pkg = tokens[0]
        assert PKG_RE.match(pkg), (
            f"Line {lineno}: invalid package name: {pkg}"
        )
        pkgs.append(pkg)
    return pkgs


def _package_set() -> set[str]:
    return set(_packages())


# ── basic structure ─────────────────────────────────────────────────────────


def test_package_list_not_empty() -> None:
    assert len(_packages()) > 0


def test_no_todo() -> None:
    assert "TODO" not in PACKAGE_LIST.read_text()


def test_no_duplicates() -> None:
    pkgs = _packages()
    assert len(pkgs) == len(set(pkgs)), "Duplicate package names found"


def test_no_extra_tokens() -> None:
    """Parser already validates single-token lines; this confirms the file
    can be fully parsed without assertion errors."""
    _packages()


# ── required categories: exact package names ────────────────────────────────


def test_base_live_system() -> None:
    s = _package_set()
    for pkg in ("linux-image-amd64", "live-boot", "live-config", "systemd-sysv"):
        assert pkg in s, f"Missing required package: {pkg}"


def test_kiosk_components() -> None:
    s = _package_set()
    assert "cage" in s
    assert "chromium" in s


def test_network() -> None:
    s = _package_set()
    for pkg in ("network-manager", "wpasupplicant", "wireless-regdb"):
        assert pkg in s, f"Missing network package: {pkg}"


def test_audio() -> None:
    s = _package_set()
    for pkg in ("pipewire", "pipewire-pulse", "wireplumber"):
        assert pkg in s, f"Missing audio package: {pkg}"


def test_graphics() -> None:
    s = _package_set()
    for pkg in (
        "libgl1-mesa-dri",
        "mesa-va-drivers",
        "libegl1",
        "libgles2",
        "libgbm1",
        "libdrm2",
    ):
        assert pkg in s, f"Missing graphics package: {pkg}"


def test_wayland_runtime() -> None:
    s = _package_set()
    for pkg in ("libwayland-client0", "libwayland-server0"):
        assert pkg in s, f"Missing Wayland package: {pkg}"


def test_keyboard() -> None:
    s = _package_set()
    for pkg in ("keyboard-configuration", "console-setup", "xkb-data"):
        assert pkg in s, f"Missing keyboard package: {pkg}"


def test_font() -> None:
    assert "fonts-noto-cjk" in _package_set()


def test_firmware() -> None:
    s = _package_set()
    for pkg in (
        "firmware-intel-graphics",
        "firmware-iwlwifi",
        "firmware-realtek",
        "firmware-amd-graphics",
        "intel-microcode",
        "amd64-microcode",
    ):
        assert pkg in s, f"Missing firmware package: {pkg}"


def test_ca_certificates() -> None:
    assert "ca-certificates" in _package_set()


# ── superseded metapackage not present ───────────────────────────────────────


def test_firmware_linux_nonfree_absent() -> None:
    assert "firmware-linux-nonfree" not in _package_set()


# ── prohibited packages: remote shell ───────────────────────────────────────


def test_no_openssh_server() -> None:
    assert "openssh-server" not in _package_set()


def test_no_dropbear() -> None:
    assert "dropbear" not in _package_set()


def test_no_telnetd() -> None:
    for pkg in ("telnetd", "inetutils-telnetd"):
        assert pkg not in _package_set(), f"Prohibited: {pkg}"


# ── prohibited packages: privilege escalation ───────────────────────────────


def test_no_sudo() -> None:
    assert "sudo" not in _package_set()


# ── prohibited packages: remote desktop ─────────────────────────────────────


def test_no_remote_desktop() -> None:
    prohibited = {
        "xrdp", "x11vnc", "tigervnc-standalone-server", "tightvncserver",
    }
    found = _package_set() & prohibited
    assert not found, f"Remote desktop package(s) found: {found}"


# ── prohibited packages: display managers ───────────────────────────────────


def test_no_display_manager() -> None:
    prohibited = {"gdm3", "sddm", "lightdm", "xdm", "slim", "lxdm"}
    found = _package_set() & prohibited
    assert not found, f"Display manager(s) found: {found}"


# ── prohibited packages: terminal emulators ─────────────────────────────────


def test_no_terminal_emulator() -> None:
    prohibited = {
        "xterm", "gnome-terminal", "konsole", "xfce4-terminal",
        "lxterminal", "rxvt-unicode", "terminator", "kgx",
    }
    found = _package_set() & prohibited
    assert not found, f"Terminal emulator(s) found: {found}"


# ── prohibited packages: file managers ──────────────────────────────────────


def test_no_file_manager() -> None:
    prohibited = {
        "nautilus", "dolphin", "thunar", "pcmanfm",
        "caja", "nemo", "krusader",
    }
    found = _package_set() & prohibited
    assert not found, f"File manager(s) found: {found}"


# ── prohibited packages: desktop environments ───────────────────────────────


def test_no_desktop_environment() -> None:
    prohibited = {
        "gnome", "gnome-shell", "kde-plasma-desktop", "plasma-desktop",
        "xfce4", "lxde", "mate-desktop", "cinnamon", "budgie-desktop",
    }
    found = _package_set() & prohibited
    assert not found, f"Desktop environment package(s) found: {found}"


# ── prohibited packages: NVIDIA proprietary driver ──────────────────────────


def test_no_nvidia_driver() -> None:
    prohibited = {
        "nvidia-driver", "nvidia-kernel-dkms", "nvidia-settings",
        "nvidia-xconfig", "nvidia-cuda-toolkit",
    }
    found = _package_set() & prohibited
    assert not found, f"NVIDIA package(s) found: {found}"
