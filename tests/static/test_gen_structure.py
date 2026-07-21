"""Behavior tests for the structure-index generator (Stage G-03).

The generator lists the post-commit shape of the repository: tracked
files plus untracked non-ignored files.  A freshly created file must
therefore make --check report staleness before it is ever `git add`ed —
the mistake this guards against happened twice in practice.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

GENERATOR = Path("tools/gen-structure.py").resolve()


def _make_fixture_repo(tmp_path: Path) -> Path:
    """A tiny repo whose tools/gen-structure.py is the real generator."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy2(GENERATOR, repo / "tools" / "gen-structure.py")
    (repo / ".gitignore").write_text("ignored-dir/\n*.secret\n")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('x')\n")
    (repo / "src" / ".gitkeep").write_text("")
    (repo / "ignored-dir").mkdir()
    (repo / "ignored-dir" / "junk.bin").write_text("junk\n")
    (repo / "token.secret").write_text("do-not-list\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    return repo


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "tools" / "gen-structure.py"), *args],
        capture_output=True, text=True, timeout=30,
    )


def test_generation_lists_tracked_but_never_ignored_files(tmp_path: Path) -> None:
    repo = _make_fixture_repo(tmp_path)
    assert _run(repo).returncode == 0
    text = (repo / "STRUCTURE.txt").read_text()
    assert "app.py" in text
    assert ".gitkeep" not in text
    assert "junk.bin" not in text and "ignored-dir" not in text
    assert "token.secret" not in text
    assert _run(repo, "--check").returncode == 0


def test_untracked_file_is_stale_before_git_add(tmp_path: Path) -> None:
    repo = _make_fixture_repo(tmp_path)
    assert _run(repo).returncode == 0
    (repo / "src" / "new_module.py").write_text("pass\n")
    result = _run(repo, "--check")
    assert result.returncode == 1, "untracked file must already count as stale"
    assert "stale" in result.stderr
    # Regenerating picks the file up without any git add.
    assert _run(repo).returncode == 0
    assert "new_module.py" in (repo / "STRUCTURE.txt").read_text()
    assert _run(repo, "--check").returncode == 0


def test_ignored_files_never_trigger_staleness(tmp_path: Path) -> None:
    repo = _make_fixture_repo(tmp_path)
    assert _run(repo).returncode == 0
    (repo / "ignored-dir" / "more-junk.tmp").write_text("x\n")
    (repo / "another.secret").write_text("x\n")
    assert _run(repo, "--check").returncode == 0
