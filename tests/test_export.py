"""``mkdeck export``: the deck it prints, and the browser it prints with."""

import re

import pytest

from mkdeck.check import browser_page
from mkdeck.errors import DeckError
from mkdeck.export import PRINT_READY_JS, _print_document, export_deck


@pytest.fixture
def deck(tmp_path):
    folder = tmp_path / "un deck"
    folder.mkdir()
    (folder / "deck.md").write_text("---\ntitle: T\n---\n\nOne.\n\n---\n\nTwo.\n\n---\n\nThree.\n")
    return folder


def test_the_deck_is_printed_from_one_file_at_the_page_size(deck, tmp_path) -> None:
    document = _print_document(deck, tmp_path / "work", size=(1280, 720))
    html = document.read_text()
    assert document.name == "deck.html"
    assert '"width": 1280' in html
    assert '"height": 720' in html


def test_a_built_page_is_printed_as_it_is(tmp_path) -> None:
    built = tmp_path / "index.html"
    built.write_text("<html></html>")
    assert _print_document(built, tmp_path / "work", size=(1280, 720)) == built


def test_a_path_that_holds_no_deck_is_a_deck_error(tmp_path) -> None:
    with pytest.raises(DeckError):
        _print_document(tmp_path / "nothing", tmp_path / "work", size=(1280, 720))


def test_a_deck_is_printed_one_page_per_slide(chromium, deck, tmp_path) -> None:
    pdf = export_deck(deck, tmp_path / "out" / "talk.pdf", size=(1280, 720))
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(re.findall(rb"/Type\s*/Page(?![s\w])", data)) == 4  # the title slide, then the three


PRINTED_JS = """
() => {
  const pictures = Array.from(document.querySelectorAll('deck-rollout img')).map((picture) => {
    const canvas = document.createElement('canvas');
    canvas.width = picture.naturalWidth;
    canvas.height = picture.naturalHeight;
    const context = canvas.getContext('2d');
    context.drawImage(picture, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const colors = new Set();
    for (let i = 0; i < pixels.length; i += 4 * 97) colors.add(pixels.slice(i, i + 3).join());
    return colors.size;
  });
  return {
    states: Array.from(document.querySelectorAll('deck-rollout')).map((host) => host.dataset.mkdState),
    contexts: document.querySelectorAll('deck-rollout canvas').length,
    frames: Array.from(document.querySelectorAll('deck-embed')).map((host) => !!host.querySelector('iframe')),
    colors: pictures,
    below: Array.from(document.querySelectorAll('.pdf-page')).map(
      (page) => page.querySelector('section').getBoundingClientRect().bottom - page.getBoundingClientRect().bottom),
  };
}
"""


def test_a_printed_deck_draws_every_rollout_as_a_picture_and_loads_every_figure(chromium, rollout_deck, tmp_path):
    """A rollout or a page far from the first slide used to print as an empty area."""
    (rollout_deck / "assets" / "page.html").write_text("<html><body style='background:teal'>page</body></html>")
    with (rollout_deck / "deck.md").open("a") as handle:
        for number in range(4):
            handle.write(f"\n---\n\nRun {number}.\n\n![run](assets/run.rollout)\n\n![page](assets/page.html)\n")
    document = _print_document(rollout_deck, tmp_path / "work", size=(1280, 720))
    with browser_page((1280, 720)) as page:
        page.goto(f"{document.resolve().as_uri()}?print-pdf")
        page.wait_for_function(PRINT_READY_JS, timeout=60_000)
        printed = page.evaluate(PRINTED_JS)
    assert printed["states"] == ["printed"] * 5
    assert printed["contexts"] == 0  # every WebGL context was given back
    assert printed["frames"] == [True] * 4
    assert all(below <= 1 for below in printed["below"])  # no slide runs past its page, where Chromium drops it
    assert all(colors > 1 for colors in printed["colors"])  # a drawn scene, not one flat colour
    assert export_deck(rollout_deck, tmp_path / "talk.pdf", size=(1280, 720)).is_file()
