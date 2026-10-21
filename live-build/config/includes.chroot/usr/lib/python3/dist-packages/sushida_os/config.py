"""The single parser and validator for /etc/sushida-os/config.env.

Every consumer (launcher, network watcher, input watcher) reads the file
through this module, so syntax rules, the accepted key set, and value
ranges live in exactly one place.

The file is parsed verbatim and never evaluated: lines are split on the
first ``=``, only a trailing CR is stripped, and quotes or leading
whitespace are NOT removed.  Blank lines and lines starting with ``#`` are
ignored.  A line without ``=``, an unknown key, or a duplicate key makes
the whole file invalid.  Values are validated only for the keys a caller
asks for, so a component never refuses to run over a setting it does not
use.

Shell callers run ``python3 -m sushida_os.config --file PATH KEY`` and get
the validated value on stdout (an empty line for an unset optional
setting); on any problem the process prints ``ERROR: ...`` to stderr and
exits 1.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = Path("/etc/sushida-os/config.env")

# The only origin SUSHIDA_URL may name: the bare origin, its root, or any
# path below it.  Userinfo, ports, other hosts and schemes all fail the
# prefix match.
SUSHIDA_ORIGIN = "https://sushida.net"


class ConfigError(ValueError):
    """config.env is missing, malformed, or holds an out-of-range value."""


@dataclass(frozen=True)
class Setting:
    """One accepted key.

    Integer settings are bounded by ``minimum``/``maximum``.  When the key is
    absent the ``default`` applies; an ``optional`` setting that is absent
    or empty is unset (``None``), meaning "leave the system default".
    """

    key: str
    minimum: int = 0
    maximum: int = 0
    default: int | None = None
    optional: bool = False
    url: bool = False


SETTINGS: dict[str, Setting] = {
    setting.key: setting
    for setting in (
        Setting("SUSHIDA_URL", url=True),
        Setting("NETWORK_CHECK_INTERVAL_SECONDS", minimum=30, maximum=3600, default=30),
        Setting("NETWORK_SETUP_GRACE_SECONDS", minimum=0, maximum=60, default=15),
        Setting("AUDIO_VOLUME_PERCENT", minimum=0, maximum=100, optional=True),
        # The floor keeps a bad value from ever blacking out the panel.
        Setting("SCREEN_BRIGHTNESS_PERCENT", minimum=5, maximum=100, default=80),
        Setting("SCREEN_ZOOM_PERCENT", minimum=50, maximum=300, optional=True),
    )
}


def parse(text: str) -> dict[str, str]:
    """Return the raw ``KEY -> value`` map, enforcing syntax only."""
    raw: dict[str, str] = {}
    for number, line in enumerate(text.split("\n"), start=1):
        if line.endswith("\r"):
            line = line[:-1]
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid config line (missing '=') at line {number}")
        key, value = line.split("=", 1)
        if key not in SETTINGS:
            raise ConfigError(f"Unknown config key at line {number}")
        if key in raw:
            raise ConfigError(f"Duplicate {key}")
        raw[key] = value
    return raw


def url_allowed(url: str) -> bool:
    return url in (SUSHIDA_ORIGIN, SUSHIDA_ORIGIN + "/") or \
        url.startswith(SUSHIDA_ORIGIN + "/")


def value(raw: dict[str, str], key: str) -> str | int | None:
    """Validate and return one setting from a parsed map."""
    setting = SETTINGS[key]
    if setting.url:
        url = raw.get(key, "")
        if not url:
            raise ConfigError(f"{key} not set")
        if not url_allowed(url):
            raise ConfigError(f"Invalid or disallowed URL: {url}")
        return url
    if key not in raw:
        return setting.default
    text = raw[key]
    if not text and setting.optional:
        return None
    if not (text.isascii() and text.isdigit()):
        raise ConfigError(f"{key} must be an integer")
    number = int(text)
    if not setting.minimum <= number <= setting.maximum:
        raise ConfigError(
            f"{key} must be between {setting.minimum} and {setting.maximum}")
    return number


def read(path: Path = CONFIG_FILE) -> dict[str, str]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except OSError:
        raise ConfigError(f"Config file unreadable: {path}") from None
    # surrogateescape keeps arbitrary bytes intact for the round trip back
    # to a shell caller instead of silently rewriting them.
    return parse(data.decode("utf-8", "surrogateescape"))


def load(key: str, path: Path = CONFIG_FILE) -> str | int | None:
    """Read the file and return one validated setting."""
    return value(read(path), key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m sushida_os.config")
    parser.add_argument("--file", type=Path, default=CONFIG_FILE)
    parser.add_argument("key", choices=sorted(SETTINGS))
    args = parser.parse_args(argv)
    try:
        result = load(args.key, args.file)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    text = "" if result is None else str(result)
    sys.stdout.buffer.write(text.encode("utf-8", "surrogateescape") + b"\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
