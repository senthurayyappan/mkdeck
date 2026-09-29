"""Fixtures shared by the tests that open a deck in a browser."""

import base64
import json
import zlib

import pytest

from mkdeck.check import browser_page
from mkdeck.errors import DeckError
from mkdeck.rollout import convert_brax_html

SCENE = {
    "opt": {"timestep": 0.02},
    "link_names": ["torso"],
    "geoms": {
        "torso": [
            {
                "name": "Box",
                "link_idx": 0,
                "pos": [0, 0, 0],
                "rot": [1, 0, 0, 0],
                "rgba": [1, 1, 1, 1],
                "size": [1, 1, 1],
            }
        ]
    },
    "states": {"x": [{"pos": [[0.0, 0.0, 0.1 * t]], "rot": [[1.0, 0.0, 0.0, 0.0]]} for t in range(10)]},
}


@pytest.fixture
def rollout_deck(tmp_path):
    """A folder deck: the title slide, a sentence, a rollout and a formula."""
    folder = tmp_path / "my deck"
    (folder / "assets").mkdir(parents=True)
    page = tmp_path / "run.html"
    blob = base64.b64encode(zlib.compress(json.dumps(SCENE).encode())).decode()
    page.write_text(f'<html><script>var system = "{blob}";</script></html>')
    convert_brax_html(page, folder / "assets")
    (folder / "deck.md").write_text(
        "---\ntitle: Runs\ndate: 2026-09-18\n---\n\nHello.\n\n---\n\nThe robot.\n\n![run](assets/run.rollout)\n\n"
        "---\n\nA formula $x^2$ here.\n"
    )
    return folder


@pytest.fixture(scope="session")
def chromium() -> None:
    """Skip the test unless Playwright and a Chromium for it are here."""
    try:
        with browser_page((100, 100)):
            pass
    except DeckError as exc:
        pytest.skip(f"no headless Chromium: {exc}")
