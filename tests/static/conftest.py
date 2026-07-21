"""Shared test environment for the static suite (Stage G-04).

Loading the production ``sushida_os`` package from the image tree and
refusing to scatter ``.pyc`` files next to files that live-build stages
into the ISO used to be a per-file boilerplate block; pytest imports this
conftest before any test module, so both apply suite-wide exactly once.

``tests/static/test_wifi_setup_backend.py`` (characterization) keeps its
own copy untouched by design; the duplication there is harmless.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

DIST_PACKAGES = (
    Path(__file__).resolve().parent.parent.parent
    / "live-build/config/includes.chroot/usr/lib/python3/dist-packages"
)
if str(DIST_PACKAGES) not in sys.path:
    sys.path.insert(0, str(DIST_PACKAGES))
