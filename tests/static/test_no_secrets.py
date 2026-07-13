from pathlib import Path


def test_placeholder() -> None:
    assert Path("AGENTS.md").is_file()
