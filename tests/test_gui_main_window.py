from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from exportgeneanet.gui.main_window import default_state_path  # noqa: E402


def test_default_state_path_matches_cli_naming_convention():
    # Must match cli.py's `Path.cwd() / f"crawl-state-{username}-{scope}.json"`
    # exactly, so a checkpoint started in one can be resumed in the other.
    assert default_state_path("yann64", "all") == Path.cwd() / "crawl-state-yann64-all.json"
    assert default_state_path("yann64", "ascendants") == Path.cwd() / "crawl-state-yann64-ascendants.json"
