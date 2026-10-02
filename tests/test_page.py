"""The deck page in headless Chromium: what `mkdeck.js` and the rollout
element do with a deck.
"""

import sys
from pathlib import Path

import pytest

from mkdeck import Deck, Embed, Slide, load_source
from mkdeck.browser import browser_page
from mkdeck.check import _prepare

SIZE = (1280, 720)


def write_deck(
    folder: Path, text: str, files: dict[str, str] | None = None
) -> Path:
    """A deck folder holding `text` as its Markdown, and the other `files` by
    relative path.
    """
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    for name, content in (files or {}).items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(content, encoding="utf-8")
    (folder / "deck.md").write_text(text, encoding="utf-8")
    return folder


def open_single_file(folder: Path, tmp_path: Path) -> Path:
    """The document `mkdeck check` opens for a deck folder."""
    return _prepare(folder, tmp_path / "work")


def open_folder_build(folder: Path, tmp_path: Path) -> Path:
    return load_source(folder).build(tmp_path / "site")


BUILDS = pytest.mark.parametrize(
    "build",
    [open_single_file, open_folder_build],
    ids=["single-file", "folder"],
)


def ready(page, document: Path) -> None:
    page.goto(document.resolve().as_uri())
    page.wait_for_function(
        "window.Reveal && Reveal.isReady() && "
        "document.querySelector('.mkd-chrome-right').textContent"
    )


def test_a_classes_dense_the_author_set_is_kept(chromium, tmp_path) -> None:
    """The dense pass used to toggle the class, which took a hand-set one off
    a slide with nothing crowded.
    """
    folder = write_deck(
        tmp_path / "deck",
        "---\ntitle: T\ntitle_slide: false\n---\n\n<!--\nclasses: "
        "[dense]\n-->\n\nA bare sentence.\n\n---\n\n"
        "A sentence.\n\n- and a bullet\n\n---\n\nPlain.\n",
    )
    with browser_page(SIZE) as page:
        ready(page, open_folder_build(folder, tmp_path))
        classes = page.evaluate(
            "Array.from(document.querySelectorAll('.slides > section')).map(s "
            "=> s.classList.contains('dense'))"
        )
    assert classes == [True, True, False]


def test_a_display_formula_is_drawn_in_display_mode(chromium, tmp_path) -> None:
    """`displayMode` was always false, so `\\sum` showed its limits beside
    it, as in a line of text.
    """
    folder = write_deck(
        tmp_path / "deck",
        "---\ntitle: T\ntitle_slide: false\n---\n\n$$\\sum_{i=1}^n i$$\n\nThe "
        "sum $\\sum_{i=1}^n i$ of it.\n",
    )
    with browser_page(SIZE) as page:
        ready(page, open_folder_build(folder, tmp_path))
        found = page.evaluate(
            """() => ({
              block: document.querySelectorAll(
                '.mkd-math-block .katex-display').length,
              inline: document.querySelectorAll(
                '.mkd-sentence .katex-display').length,
              blockLimits: document.querySelectorAll(
                '.mkd-math-block .mop.op-limits').length,
              inlineLimits: document.querySelectorAll(
                '.mkd-sentence .mop.op-limits').length,
            })"""
        )
    assert found == {
        "block": 1,
        "inline": 0,
        "blockLimits": 1,
        "inlineLimits": 0,
    }


MODULE = "export const mark = (node) => { node.dataset.marked = 'yes'; };"
EXTRA_JS = (
    "(async () => {\n"
    f'  const {{ mark }} = await import("data:text/javascript,{MODULE}");\n'
    '  customElements.define("deck-mark", class extends HTMLElement { '
    "connectedCallback() { mark(this); } });\n"
    "})();\n"
)


@BUILDS
def test_extra_js_loads_a_module_with_a_dynamic_import(
    chromium, build, tmp_path
) -> None:
    """`extra_js` is a classic script, so the documented example imports with
    `import()`, not `import ... from`.
    """
    folder = write_deck(
        tmp_path / "deck",
        "---\ntitle: T\ntitle_slide: false\nextra_js: "
        "[theme/marks.js]\n---\n\nSpeed is <deck-mark>2.10</deck-mark> now.\n",
        {"theme/marks.js": EXTRA_JS},
    )
    with browser_page(SIZE) as page:
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        ready(page, build(folder, tmp_path))
        page.wait_for_function(
            "document.querySelector('deck-mark').dataset.marked === 'yes'"
        )
    assert errors == []


def test_a_static_import_in_extra_js_is_a_syntax_error(
    chromium, tmp_path
) -> None:
    folder = write_deck(
        tmp_path / "deck",
        "---\ntitle: T\ntitle_slide: false\nextra_js: "
        "[theme/marks.js]\n---\n\nHi.\n",
        {
            "theme/marks.js": "import { mark } from "
            '"https://example.org/mark.js";\n'
        },
    )
    with browser_page(SIZE) as page:
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        ready(page, open_single_file(folder, tmp_path))
    assert any("import statement outside a module" in error for error in errors)


ROLLOUT_STATE = """() => Array.from(
  document.querySelectorAll('deck-rollout[data-view]')).map((host) => ({
  state: host.dataset.mkdState,
  playing: host.mkdViewer ? host.mkdViewer.playing : null,
}))"""


def test_a_rollout_written_in_raw_html_loads_the_viewer_and_takes_its_options(
    chromium, rollout_deck, tmp_path
):
    """Only a hand-written element can carry `data-*` options, and it used to
    bring no viewer with it.
    """
    with (rollout_deck / "deck.md").open("a", encoding="utf-8") as handle:
        handle.write(
            '\n---\n\n<deck-rollout data-view="side" data-autoplay="false" '
            'src="assets/run.rollout"></deck-rollout>\n'
        )
    with browser_page(SIZE) as page:
        ready(page, open_single_file(rollout_deck, tmp_path))
        page.evaluate("Reveal.slide(4, 0)")
        page.wait_for_function(
            "document.querySelector('deck-rollout[data-view]')"
            ".dataset.mkdState === 'ready'"
        )
        (host,) = page.evaluate(ROLLOUT_STATE)
    assert host == {
        "state": "ready",
        "playing": False,
    }  # data-autoplay="false" reached the viewer


def test_a_deck_with_only_a_raw_rollout_carries_the_viewer(
    rollout_deck, tmp_path
) -> None:
    (rollout_deck / "deck.md").write_text(
        "---\ntitle: T\n---\n\n<deck-rollout "
        'src="assets/run.rollout"></deck-rollout>\n',
        encoding="utf-8",
    )
    folder = open_folder_build(rollout_deck, tmp_path).read_text(
        encoding="utf-8"
    )
    assert '<script src="mkdeck-assets/mkdeck-rollout.js">' in folder
    assert (tmp_path / "site" / "assets" / "run.rollout").is_file()
    one = open_single_file(rollout_deck, tmp_path).read_text(encoding="utf-8")
    assert 'data-mkd-module="mkdeck-viewer"' in one
    assert 'data-mkd-rollout="assets/run.rollout"' in one


@pytest.mark.skipif(
    sys.platform == "win32", reason='a file name cannot hold a " on Windows'
)
def test_a_rollout_whose_name_holds_a_quote_still_loads(
    chromium, rollout_deck, tmp_path
) -> None:
    """The inline payload was found with a selector built from the name, so a
    `"` threw.
    """
    (rollout_deck / "assets" / "run.rollout").rename(
        rollout_deck / "assets" / 'we"ird.rollout'
    )
    deck = Deck(
        title="T",
        title_slide=False,
        slides=[Slide(embeds=[Embed('assets/we"ird.rollout')])],
    )
    document = deck.build(
        tmp_path / "work" / "deck.html", source=rollout_deck, single_file=True
    )
    with browser_page(SIZE) as page:
        ready(page, document)
        page.wait_for_function(
            "document.querySelector('deck-rollout').dataset.mkdState === "
            "'ready'"
        )
