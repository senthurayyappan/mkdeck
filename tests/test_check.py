"""``mkdeck check``: the pure parts, and the browser itself when there is
one.
"""

import json
from pathlib import Path

import pytest

from mkdeck import check as check_module
from mkdeck.browser import browser_page, file_path
from mkdeck.check import (
    EMBED_BLOCK_BYTES,
    _format_row,
    _prepare,
    _route,
    blocks_embed,
    check_deck,
    probe_script,
    report_text,
    slide_flags,
)
from mkdeck.errors import DeckError

# --------------------------------------------------------------------------- #
# The findings
# --------------------------------------------------------------------------- #


def test_a_clean_slide_has_no_flags() -> None:
    assert slide_flags({"n": 1, "overflow_top": 0, "overflow_bottom": 0}) == []
    assert slide_flags({}) == []


def test_every_kind_of_finding_becomes_a_flag() -> None:
    flags = slide_flags(
        {
            "overflow_top": 3,
            "overflow_bottom": 12,
            "into_chrome": True,
            "scrollers": [
                {
                    "tag": "div",
                    "cls": "box",
                    "sw": 900,
                    "cw": 800,
                    "sh": 50,
                    "ch": 40,
                }
            ],
            "overlaps": [{"i": 0, "j": 1, "ox": 30, "oy": 9}],
            "katex_errors": 2,
            "mermaid_errors": 1,
            "math_unrendered": 1,
            "rollout_errors": [
                {
                    "src": "assets/run.rollout",
                    "state": "error",
                    "message": "no meshes",
                }
            ],
        }
    )
    assert flags == [
        "OVERFLOW top 3px bottom 12px",
        "INTO-CHROME",
        "SCROLLBAR div.box 900>800w 50>40h",
        'OVERLAP [{"i": 0, "j": 1, "ox": 30, "oy": 9}]',
        "KATEX-ERROR x2",
        "MERMAID-ERROR x1",
        "MATH-UNRENDERED x1",
        "ROLLOUT-ERROR assets/run.rollout: no meshes",
    ]


def test_a_rollout_that_never_finished_loading_is_still_a_flag() -> None:
    flags = slide_flags(
        {
            "rollout_errors": [
                {"src": "a.rollout", "state": "loading", "message": ""}
            ]
        }
    )
    assert flags == ["ROLLOUT-ERROR a.rollout: still loading"]


def test_a_row_says_what_the_slide_holds() -> None:
    row = _format_row(
        {
            "n": 4,
            "id": "numbers",
            "layout": "figures",
            "sentence_chars": 42,
            "bullets": 2,
            "bullet_chars": [10, 20],
            "figures": 1,
            "table": {"rows": 3, "cols": 2, "width": 640},
            "formula_blocks": 1,
            "top": 100,
            "bottom": 900,
        }
    )
    assert row.startswith("  4 numbers")
    for part in (
        "figures",
        "sent   42",
        "bul 2/10+20",
        "fig 1 table 3x2 640px",
        "fb 1",
        "h 100-900",
        "ok",
    ):
        assert part in row


def test_a_row_carries_its_flags_and_a_probe_error_replaces_it() -> None:
    assert _format_row({"n": 1, "into_chrome": True}).endswith("INTO-CHROME")
    assert _format_row(
        {"n": 2, "id": "x", "error": "no visible slide"}
    ).endswith("no visible slide")


def test_the_report_text_has_a_header_and_a_row_per_slide() -> None:
    text = report_text([{"n": 1}, {"n": 2}], size=(800, 600), path="talk")
    lines = text.splitlines()
    assert lines[0] == "viewport 800x600, deck talk"
    assert len(lines) == 3
    assert text.endswith("\n")


def test_the_probe_ships_beside_the_module_and_reports_rollouts() -> None:
    assert Path(check_module.__file__).with_name("probe.js").is_file()
    assert "rollout_errors" in probe_script()


# --------------------------------------------------------------------------- #
# Which requests get a stub
# --------------------------------------------------------------------------- #


def sized(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_a_file_url_becomes_the_path_it_names(tmp_path) -> None:
    target = tmp_path / "my deck" / "naïve 1.html"
    assert file_path(target.as_uri()) == target
    assert "%20" in target.as_uri()


def test_a_heavy_page_in_a_frame_is_stubbed(tmp_path) -> None:
    page = sized(tmp_path / "plot.html", EMBED_BLOCK_BYTES + 1)
    assert blocks_embed(page.as_uri(), subframe=True)


def test_the_deck_itself_is_never_stubbed_however_large(tmp_path) -> None:
    deck = sized(tmp_path / "deck.html", EMBED_BLOCK_BYTES * 2)
    assert not blocks_embed(deck.as_uri(), subframe=False)


def test_a_light_page_in_a_frame_loads(tmp_path) -> None:
    page = sized(tmp_path / "plot.html", 1000)
    assert not blocks_embed(page.as_uri(), subframe=True)


def test_a_path_with_spaces_and_accents_is_measured_too(tmp_path) -> None:
    page = sized(
        tmp_path / "mes figures" / "tracé 1.html", EMBED_BLOCK_BYTES + 1
    )
    assert blocks_embed(page.as_uri(), subframe=True)


def test_only_html_files_and_only_file_urls_are_stubbed(tmp_path) -> None:
    data = sized(tmp_path / "data.json", EMBED_BLOCK_BYTES + 1)
    assert not blocks_embed(data.as_uri(), subframe=True)
    assert not blocks_embed("https://example.com/plot.html", subframe=True)
    assert not blocks_embed((tmp_path / "gone.html").as_uri(), subframe=True)


# --------------------------------------------------------------------------- #
# Getting a document to open
# --------------------------------------------------------------------------- #


def test_a_deck_is_built_as_one_file_so_a_rollout_can_be_read(
    rollout_deck, tmp_path
) -> None:
    document = _prepare(rollout_deck, tmp_path / "work")
    html = document.read_text(encoding="utf-8")
    assert document.name == "deck.html"
    assert 'data-mkd-rollout="assets/run.rollout"' in html


def test_a_built_page_is_opened_as_it_is(tmp_path) -> None:
    built = tmp_path / "site" / "index.html"
    built.parent.mkdir()
    built.write_text("<html></html>")
    assert _prepare(built, tmp_path / "work") == built


def test_a_path_that_holds_no_deck_is_a_deck_error(tmp_path) -> None:
    with pytest.raises(DeckError):
        _prepare(tmp_path / "nothing", tmp_path / "work")


# --------------------------------------------------------------------------- #
# The browser
# --------------------------------------------------------------------------- #


def test_a_check_reads_every_slide_and_a_rollout_on_one(
    chromium, rollout_deck, tmp_path
) -> None:
    out = tmp_path / "report"
    records = check_deck(rollout_deck, out=out, size=(1280, 720))
    assert [record["n"] for record in records] == [1, 2, 3, 4]
    assert all(record["flags"] == [] for record in records), [
        record["flags"] for record in records
    ]
    assert records[2]["figures"] == 1
    assert sorted(path.name for path in out.glob("slide_*.png")) == [
        f"slide_0{n}.png" for n in (1, 2, 3, 4)
    ]
    written = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert [row["flags"] for row in written] == [[]] * 4
    assert (
        (out / "report.txt")
        .read_text(encoding="utf-8")
        .startswith("viewport 1280x720, deck ")
    )


def test_a_deck_larger_than_the_embed_limit_is_still_checked(
    chromium, rollout_deck, tmp_path
) -> None:
    built = _prepare(rollout_deck, tmp_path / "work")
    with built.open("a", encoding="utf-8") as handle:
        handle.write("<!--" + "x" * (EMBED_BLOCK_BYTES + 1) + "-->")
    records = check_deck(
        built, out=tmp_path / "report", size=(1280, 720), shots=False
    )
    assert len(records) == 4
    assert records[2]["flags"] == []


def test_a_rollout_a_folder_build_cannot_read_is_flagged_with_the_reason(
    chromium, rollout_deck, tmp_path
) -> None:
    from mkdeck import load_source

    index = load_source(rollout_deck).build(tmp_path / "site")
    records = check_deck(
        index, out=tmp_path / "report", size=(1280, 720), shots=False
    )
    (flag,) = records[2]["flags"]
    assert flag.startswith("ROLLOUT-ERROR assets/run.rollout:")
    assert "--single-file" in flag


@pytest.mark.filterwarnings("ignore::mkdeck.errors.DeckWarning")
def test_a_heavy_iframe_is_stubbed_but_the_deck_around_it_is_not(
    chromium, tmp_path
) -> None:
    folder = tmp_path / "un dossier"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "tracé lourd.html").write_text(
        "<html><body>REAL" + "x" * (EMBED_BLOCK_BYTES + 1) + "</body></html>"
    )
    (folder / "assets" / "light.html").write_text(
        "<html><body>LIGHTREAL</body></html>"
    )
    (folder / "deck.md").write_text(
        "---\ntitle: E\n---\n\nSay it.\n\n![a](<assets/tracé "
        "lourd.html>)\n![b](assets/light.html)\n"
    )
    document = _prepare(folder, tmp_path / "work")
    with browser_page((1280, 720)) as page:
        page.route("**/*", _route)
        page.goto(document.as_uri())
        page.wait_for_function("window.Reveal && Reveal.isReady()")
        page.wait_for_function(
            "document.querySelectorAll('iframe[src]').length > 0"
        )
        page.wait_for_timeout(500)
        texts = [frame.content() for frame in page.frames[1:]]
    assert any("blocked in the checker" in text for text in texts)
    assert any("LIGHTREAL" in text for text in texts)
    assert not any("REAL" in text.replace("LIGHTREAL", "") for text in texts)


def test_a_browser_timeout_is_a_deck_error(chromium) -> None:
    with (
        pytest.raises(DeckError, match="timed out"),
        browser_page((200, 200)) as page,
    ):
        page.wait_for_function("false", timeout=50)


FAKE_MERMAID = (
    "window.mermaid = { initialize() {}, render: async () => ({ "
    "svg: '<svg></svg>' }) };"
)


@pytest.mark.parametrize(
    ("script", "flags"),
    [("mermaid.min.js", []), ("gone.js", ["MERMAID-ERROR x1"])],
)
def test_a_diagram_that_did_not_draw_is_flagged(
    chromium, tmp_path, script, flags
) -> None:
    folder = tmp_path / "diagrams"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "mermaid.min.js").write_text(FAKE_MERMAID)
    (folder / "deck.md").write_text(
        "---\ntitle: D\ntitle_slide: false\n---\n\n"
        f'<deck-mermaid data-src="assets/{script}">flowchart LR\n  A --> '
        f"B</deck-mermaid>\n"
    )
    (record,) = check_deck(
        folder, out=tmp_path / "report", size=(1280, 720), shots=False
    )
    assert record["flags"] == flags


def hostile_deck(tmp_path: Path) -> tuple[Path, Path]:
    """A deck whose raw HTML frames a file outside it, as well as one of its
    own.
    """
    secret = tmp_path / "secret.html"
    secret.write_text("<html><body>SECRETTEXT</body></html>")
    folder = tmp_path / "deck"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "own.html").write_text(
        "<html><body>OWNTEXT</body></html>"
    )
    (folder / "deck.md").write_text(
        f"---\ntitle: T\ntitle_slide: false\n---\n\n<iframe "
        f'src="{secret.as_uri()}"></iframe>\n\n'
        '<iframe src="assets/own.html"></iframe>\n'
    )
    return folder, secret


def test_a_page_in_the_browser_cannot_read_a_local_file_outside_its_deck(
    chromium, tmp_path
) -> None:
    """Raw HTML such as an iframe of `file:///etc/hosts` was drawn into check
    screenshots and the PDF.
    """
    folder, _ = hostile_deck(tmp_path)
    document = _prepare(folder, tmp_path / "work")
    with browser_page((1280, 720), folder=document.parent) as page:
        page.goto(document.as_uri())
        page.wait_for_function("window.Reveal && Reveal.isReady()")
        page.wait_for_function(
            "Array.from(document.querySelectorAll('iframe')).length === 2"
        )
        page.wait_for_timeout(500)
        texts = [frame.content() for frame in page.frames[1:]]
    assert any("OWNTEXT" in text for text in texts)
    assert not any("SECRETTEXT" in text for text in texts)


def test_check_and_export_both_keep_the_page_to_the_folder_of_its_deck(
    chromium, tmp_path, monkeypatch
) -> None:
    from mkdeck import export as export_module

    folder, _ = hostile_deck(tmp_path)
    folders: list[Path | None] = []

    def spy(size, *, folder=None):
        folders.append(folder)
        return browser_page(size, folder=folder)

    monkeypatch.setattr(check_module, "browser_page", spy)
    monkeypatch.setattr(export_module, "browser_page", spy)
    check_deck(folder, out=tmp_path / "report", size=(640, 360), shots=False)
    export_module.export_deck(folder, tmp_path / "deck.pdf", size=(640, 360))
    assert len(folders) == 2
    assert all(isinstance(path, Path) for path in folders)


def test_a_check_clears_the_screenshots_of_an_earlier_longer_run(
    chromium, rollout_deck, tmp_path
) -> None:
    out = tmp_path / "report"
    out.mkdir()
    for number in (5, 6, 7):
        (out / f"slide_{number:02d}.png").write_bytes(b"old")
    (out / "notes.txt").write_text("mine")
    check_deck(rollout_deck, out=out, size=(640, 360))
    assert sorted(path.name for path in out.glob("slide_*.png")) == [
        f"slide_0{n}.png" for n in (1, 2, 3, 4)
    ]
    assert (out / "notes.txt").read_text() == "mine"
    check_deck(rollout_deck, out=out, size=(640, 360), shots=False)
    assert not list(out.glob("slide_*.png"))


def test_strict_check_exits_with_an_error_on_a_deck_that_overflows(
    chromium, tmp_path
) -> None:
    from typer.testing import CliRunner

    from mkdeck.cli import app

    deck = tmp_path / "deck.md"
    deck.write_text(
        "---\ntitle: T\ntitle_slide: false\n---\n\nToo much.\n\n"
        + "\n".join(f"- point {n}" for n in range(60))
    )
    runner = CliRunner()
    args = [
        "check",
        str(deck),
        "--size",
        "640x360",
        "--no-shots",
        "--out",
        str(tmp_path / "report"),
    ]
    lenient = runner.invoke(app, args)
    assert lenient.exit_code == 0, lenient.output
    assert "OVERFLOW" in lenient.output
    strict = runner.invoke(app, [*args, "--strict"])
    assert strict.exit_code == 1
    assert "1 of 1 slides are flagged" in strict.output
