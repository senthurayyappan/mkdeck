"""Building a deck folder into a site."""

import gzip
import json
import os
import re
import struct
import sys
import warnings
from pathlib import Path

import pytest

from mkdeck import Deck, DeckError, DeckWarning, Embed, Slide, load_source
from mkdeck import build as build_module
from mkdeck._messages import install_warning_formatter
from mkdeck.build import MANIFEST_NAME, ROLLOUT_ASSETS, build_deck
from mkdeck.inline import VIEWER_MODULES
from mkdeck.paths import ASSET_ROOT

DECK = """---
title: Quadruped Vault Runs
date: 2026-09-18
---

<!--
id: g3-paired
-->

Body load falls from 134 to 86 N s.

![18 N m](assets/g3_18.html)
"""


@pytest.fixture
def deck_folder(tmp_path):
    folder = tmp_path / "deck"
    (folder / "assets").mkdir(parents=True)
    (folder / "assets" / "g3_18.html").write_text(
        "<!doctype html><title>g3</title>"
    )
    (folder / "deck.md").write_text(DECK)
    return folder


def test_a_build_writes_the_page_the_assets_and_the_vendored_tree(
    deck_folder, tmp_path
):
    index = load_source(deck_folder).build(tmp_path / "site")
    assert index == tmp_path / "site" / "index.html"
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()
    assert (tmp_path / "site" / "mkdeck-assets" / "mkdeck.js").is_file()
    assert (
        tmp_path / "site" / "mkdeck-assets" / "reveal.js" / "dist" / "reveal.js"
    ).is_file()
    assert 'src="assets/g3_18.html"' in index.read_text(encoding="utf-8")


def test_a_single_file_build_leaves_only_the_deck_assets_outside(
    deck_folder, tmp_path
):
    index = load_source(deck_folder).build(
        tmp_path / "one" / "deck.html", single_file=True
    )
    html = index.read_text(encoding="utf-8")
    assert index.name == "deck.html"
    assert not (tmp_path / "one" / "mkdeck-assets").exists()
    assert (tmp_path / "one" / "assets" / "g3_18.html").is_file()
    assert 'rel="stylesheet"' not in html
    assert "<script src=" not in html
    assert "<style>" in html
    assert "data:font/woff2;base64," in html


def test_a_large_embed_is_called_out(deck_folder, tmp_path):
    (deck_folder / "assets" / "g3_18.html").write_bytes(b"x" * 2_500_000)
    with pytest.warns(DeckWarning, match="2.5 MB"):
        load_source(deck_folder).build(tmp_path / "site")


def test_an_embed_shown_twice_is_called_out_once(deck_folder, tmp_path):
    (deck_folder / "assets" / "g3_18.html").write_bytes(b"x" * 2_500_000)
    (deck_folder / "deck.md").write_text(
        f"{DECK}\n---\n\nThe same run, seen again.\n\n![18 N "
        f"m](assets/g3_18.html)\n"
    )
    with pytest.warns(DeckWarning) as caught:
        load_source(deck_folder).build(tmp_path / "site")
    assert sum("2.5 MB" in str(warning.message) for warning in caught) == 1


def test_building_over_the_source_is_refused(deck_folder):
    with pytest.raises(DeckError, match="source folder"):
        load_source(deck_folder).build(deck_folder)


def test_a_python_deck_builds_through_its_own_method(tmp_path):
    deck = Deck(title="Runs", date="2026-09-18")
    deck.slides.append(
        Slide(
            sentence="Five seeds cross.",
            embeds=[Embed("assets/g1.html", label="18 N m")],
        )
    )
    with pytest.warns(DeckWarning, match="assets/g1.html"):
        index = deck.build(tmp_path / "site")
    assert index.is_file()
    assert '<deck-embed src="assets/g1.html">' in index.read_text(
        encoding="utf-8"
    )


def test_the_stylesheets_and_scripts_a_deck_adds_are_copied(
    deck_folder, tmp_path
):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text(
        ":root { --mkd-accent: #b4532a; }"
    )
    (deck_folder / "theme" / "marks.js").write_text('console.log("marks");')
    (deck_folder / "deck.yml").write_text(
        "extra_css: [theme/mine.css]\nextra_js: [theme/marks.js]\n"
    )

    index = load_source(deck_folder).build(tmp_path / "site")

    assert 'href="theme/mine.css"' in index.read_text(encoding="utf-8")
    assert (tmp_path / "site" / "theme" / "mine.css").is_file()
    assert (tmp_path / "site" / "theme" / "marks.js").is_file()


def test_a_stylesheet_that_is_not_there_is_called_out(deck_folder, tmp_path):
    (deck_folder / "deck.yml").write_text("extra_css: [theme/nope.css]\n")
    with pytest.warns(DeckWarning, match="theme/nope.css"):
        load_source(deck_folder).build(tmp_path / "site")


def test_a_stylesheet_outside_the_deck_is_refused(deck_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-TOKEN")
    (deck_folder / "deck.yml").write_text("extra_css: ['../secret.txt']\n")
    with pytest.raises(DeckError, match="inside the deck folder") as caught:
        load_source(deck_folder).build(tmp_path / "out")
    assert "deck.yml" in str(caught.value)
    assert secret.read_text(encoding="utf-8") == "SECRET-TOKEN"
    assert not (tmp_path / "out").exists()


def test_a_symlinked_stylesheet_is_not_followed_outside(deck_folder, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-TOKEN")
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").symlink_to(secret)
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\n")
    with pytest.raises(DeckError, match="leaves the deck folder"):
        load_source(deck_folder).build(tmp_path / "site")
    built = (
        list((tmp_path / "site").rglob("*"))
        if (tmp_path / "site").exists()
        else []
    )
    assert all(
        "SECRET-TOKEN" not in path.read_text(errors="ignore")
        for path in built
        if path.is_file()
    )


def test_a_python_deck_refuses_a_stylesheet_outside_the_folder(tmp_path):
    deck = Deck(title="Runs", extra_css=["../secret.txt"])
    with pytest.raises(
        DeckError, match=r'The path "\.\./secret\.txt" under "extra_css"'
    ):
        deck.build(tmp_path / "site")


def test_the_package_ships_its_type_marker_and_the_font_license():
    import mkdeck
    import mkdeck.render as render

    root = Path(mkdeck.__file__).resolve().parent
    assert (root / "py.typed").is_file()
    license_text = (
        render.ASSET_ROOT / "katex" / "dist" / "fonts" / "OFL.txt"
    ).read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in license_text


def test_a_python_deck_cannot_repeat_a_slide_id(tmp_path):
    deck = Deck(
        title="Runs",
        slides=[
            Slide(id="g3", sentence="One."),
            Slide(id="g3", sentence="Two."),
        ],
    )
    with pytest.raises(DeckError, match="repeats the id"):
        deck.build(tmp_path / "site")


# --------------------------------------------------------------------------- #
# Rebuilding, and the files a build carries
# --------------------------------------------------------------------------- #


def test_editing_an_embed_reaches_a_rebuild_into_the_same_folder(
    deck_folder, tmp_path
):
    load_source(deck_folder).build(tmp_path / "site")
    (deck_folder / "assets" / "g3_18.html").write_text("edited page")
    load_source(deck_folder).build(tmp_path / "site")
    assert (tmp_path / "site" / "assets" / "g3_18.html").read_text(
        encoding="utf-8"
    ) == "edited page"


def test_editing_an_extra_stylesheet_reaches_a_rebuild(deck_folder, tmp_path):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text("body { color: red; }")
    (deck_folder / "deck.yml").write_text("extra_css: [theme/mine.css]\n")
    load_source(deck_folder).build(tmp_path / "site")
    (deck_folder / "theme" / "mine.css").write_text("body { color: blue; }")
    load_source(deck_folder).build(tmp_path / "site")
    assert (tmp_path / "site" / "theme" / "mine.css").read_text(
        encoding="utf-8"
    ) == "body { color: blue; }"


def test_an_embed_outside_the_assets_folder_is_refreshed_too(
    deck_folder, tmp_path
):
    (deck_folder / "figs").mkdir()
    (deck_folder / "figs" / "plot.html").write_text("one")
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![p](figs/plot.html)\n"
    )
    load_source(deck_folder).build(tmp_path / "site")
    (deck_folder / "figs" / "plot.html").write_text("two")
    load_source(deck_folder).build(tmp_path / "site")
    assert (tmp_path / "site" / "figs" / "plot.html").read_text(
        encoding="utf-8"
    ) == "two"


def test_a_rebuild_removes_what_the_last_build_wrote_and_this_one_does_not_need(
    deck_folder, tmp_path
):
    (deck_folder / "assets" / "sub").mkdir()
    (deck_folder / "assets" / "sub" / "old.png").write_bytes(b"png")
    site = tmp_path / "site"
    load_source(deck_folder).build(site)
    (site / "mine.txt").write_text("not from mkdeck")
    assert (site / "assets" / "sub" / "old.png").is_file()

    (deck_folder / "assets" / "sub" / "old.png").unlink()
    (deck_folder / "assets" / "sub").rmdir()
    load_source(deck_folder).build(site)

    assert not (site / "assets" / "sub").exists()
    assert (site / "assets" / "g3_18.html").is_file()
    assert (site / "mine.txt").read_text(encoding="utf-8") == "not from mkdeck"
    assert (
        "assets/g3_18.html"
        in json.loads((site / MANIFEST_NAME).read_text(encoding="utf-8"))[
            "files"
        ]
    )


def test_switching_to_a_deck_without_a_rollout_sweeps_the_viewer(
    rollout_deck_folder, tmp_path
):
    site = tmp_path / "site"
    load_source(rollout_deck_folder).build(site)
    assert (site / "mkdeck-assets" / "three" / "three.module.js").is_file()
    (rollout_deck_folder / "deck.md").write_text("---\ntitle: T\n---\n\nHi.\n")
    load_source(rollout_deck_folder).build(site)
    assert not (site / "mkdeck-assets" / "three").exists()
    assert not (site / "mkdeck-assets" / "viewer").exists()


def test_a_damaged_manifest_is_ignored(deck_folder, tmp_path):
    site = tmp_path / "site"
    load_source(deck_folder).build(site)
    (site / MANIFEST_NAME).write_text("{not json")
    load_source(deck_folder).build(site)
    assert json.loads((site / MANIFEST_NAME).read_text(encoding="utf-8"))[
        "files"
    ]


def test_a_manifest_cannot_make_a_build_delete_outside_the_folder(
    deck_folder, tmp_path
):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    site = tmp_path / "site"
    site.mkdir()
    (site / MANIFEST_NAME).write_text(json.dumps({"files": ["../victim.txt"]}))
    load_source(deck_folder).build(site)
    assert victim.read_text(encoding="utf-8") == "keep me"


def test_an_embed_with_a_query_is_copied_and_linked_whole(
    deck_folder, tmp_path
):
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![p](assets/g3_18.html?seed=2#top)\n"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        index = load_source(deck_folder).build(tmp_path / "site")
    assert 'src="assets/g3_18.html?seed=2#top"' in index.read_text(
        encoding="utf-8"
    )
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()


def test_an_embed_with_a_space_in_its_name_is_found_by_its_encoded_src(
    deck_folder, tmp_path
):
    (deck_folder / "assets" / "big plot.html").write_text("big")
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![p](assets/big%20plot.html)\n"
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        load_source(deck_folder).build(tmp_path / "site")
    assert (tmp_path / "site" / "assets" / "big plot.html").read_text(
        encoding="utf-8"
    ) == "big"


def test_an_embed_that_is_not_there_is_a_warning_naming_it(
    deck_folder, tmp_path
):
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![p](figs/gone.html)\n"
    )
    with pytest.warns(DeckWarning, match="figs/gone.html"):
        load_source(deck_folder).build(tmp_path / "site")


def test_a_single_file_build_does_not_copy_what_it_inlined(
    deck_folder, tmp_path
):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text("body { color: red; }")
    (deck_folder / "theme" / "marks.js").write_text('console.log("marks");')
    (deck_folder / "deck.yml").write_text(
        "extra_css: [theme/mine.css]\nextra_js: [theme/marks.js]\n"
    )
    index = load_source(deck_folder).build(
        tmp_path / "one" / "deck.html", single_file=True
    )
    assert "body { color: red; }" in index.read_text(encoding="utf-8")
    assert 'console.log("marks");' in index.read_text(encoding="utf-8")
    assert not (tmp_path / "one" / "theme").exists()
    assert (tmp_path / "one" / "assets" / "g3_18.html").is_file()
    assert not (tmp_path / "one" / MANIFEST_NAME).exists()


def test_only_the_files_a_deck_runs_are_copied(deck_folder, tmp_path):
    (deck_folder / "assets" / ".gitkeep").write_text("")
    (deck_folder / "assets" / ".DS_Store").write_text("")
    site = tmp_path / "site"
    load_source(deck_folder).build(site)
    built = {
        path.relative_to(site).as_posix()
        for path in site.rglob("*")
        if path.is_file()
    }
    assert not {
        name
        for name in built
        if name.endswith(("package.json", "VENDOR.md", ".gitkeep", ".DS_Store"))
    }
    assert "mkdeck-assets/themes/minimal.css" in built
    assert "mkdeck-assets/themes/dark.css" not in built
    assert "mkdeck-assets/templates/deck.html.jinja" not in built
    for library in ("reveal.js", "katex", "roboto"):
        assert f"mkdeck-assets/{library}/LICENSE" in built
    assert "mkdeck-assets/katex/dist/fonts/OFL.txt" in built


def test_the_rollout_viewer_files_are_named_once():
    assert {
        path.split("/", 1)[0] for _, path in VIEWER_MODULES
    } <= ROLLOUT_ASSETS
    for name in ROLLOUT_ASSETS:
        assert (ASSET_ROOT / name).exists(), name


def test_a_python_deck_finds_its_assets_in_the_current_directory(
    deck_folder, tmp_path, monkeypatch
):
    monkeypatch.chdir(deck_folder)
    deck = Deck(
        title="Runs",
        slides=[Slide(sentence="Hi.", embeds=[Embed("assets/g3_18.html")])],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        deck.build(tmp_path / "site")
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()


def test_source_and_out_may_be_plain_strings(deck_folder, tmp_path):
    deck = Deck(
        title="Runs",
        slides=[Slide(sentence="Hi.", embeds=[Embed("assets/g3_18.html")])],
    )
    index = deck.build(str(tmp_path / "site"), source=str(deck_folder))
    assert (tmp_path / "site" / "assets" / "g3_18.html").is_file()
    assert index == tmp_path / "site" / "index.html"


def test_a_python_deck_built_into_its_own_folder_is_left_alone(
    deck_folder, monkeypatch
):
    monkeypatch.chdir(deck_folder)
    deck = Deck(
        title="Runs",
        slides=[Slide(sentence="Hi.", embeds=[Embed("assets/g3_18.html")])],
    )
    deck.build(".")
    assert (deck_folder / "assets" / "g3_18.html").read_text(
        encoding="utf-8"
    ) == "<!doctype html><title>g3</title>"
    assert (deck_folder / "index.html").is_file()


def test_a_folder_link_and_a_link_out_of_the_folder_are_not_copied(
    deck_folder, tmp_path
):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET-TOKEN")
    (deck_folder / "assets" / "linked").symlink_to(
        outside, target_is_directory=True
    )
    (deck_folder / "assets" / "leak.txt").symlink_to(outside / "secret.txt")
    with pytest.warns(DeckWarning) as caught:
        load_source(deck_folder).build(tmp_path / "site")
    messages = " ".join(str(warning.message) for warning in caught)
    assert "assets/linked" in messages
    assert "assets/leak.txt" in messages
    assert not (tmp_path / "site" / "assets" / "linked").exists()
    assert not (tmp_path / "site" / "assets" / "leak.txt").exists()


def test_a_symlinked_embed_is_not_followed_out_of_the_folder(
    deck_folder, tmp_path
):
    secret = tmp_path / "secret.html"
    secret.write_text("SECRET-TOKEN")
    (deck_folder / "figs").mkdir()
    (deck_folder / "figs" / "leak.html").symlink_to(secret)
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![p](figs/leak.html)\n"
    )
    with pytest.raises(DeckError, match="leaves the deck folder"):
        load_source(deck_folder).build(tmp_path / "site")


def test_a_link_left_in_the_output_is_not_written_through(
    deck_folder, tmp_path
):
    keep = tmp_path / "keep.txt"
    keep.write_text("mine")
    site = tmp_path / "site"
    (site / "assets").mkdir(parents=True)
    (site / "assets" / "g3_18.html").symlink_to(keep)
    load_source(deck_folder).build(site)
    assert keep.read_text(encoding="utf-8") == "mine"
    assert (site / "assets" / "g3_18.html").read_text(
        encoding="utf-8"
    ) == "<!doctype html><title>g3</title>"


def test_the_output_folder_may_not_sit_on_the_source_by_any_spelling(
    deck_folder,
):
    with pytest.raises(DeckError, match="source folder"):
        load_source(deck_folder).build(deck_folder / "sub" / "..")


def test_a_deck_warning_is_formatted_for_the_command_line(monkeypatch):
    monkeypatch.setattr(
        warnings, "formatwarning", warnings.formatwarning
    )  # restored after the test
    install_warning_formatter()
    install_warning_formatter()
    text = warnings.formatwarning(
        "the embed is gone", DeckWarning, "x.py", 1, None
    )
    assert text == "mkdeck: warning: the embed is gone\n"
    assert "UserWarning" in warnings.formatwarning(
        "other", UserWarning, "x.py", 1, None
    )


# --------------------------------------------------------------------------- #
# A rollout is data, and may not name a file outside the deck
# --------------------------------------------------------------------------- #


def write_rollout(path: Path, *, meshes: object) -> None:
    """A rollout whose header points at `meshes`; the body is not read by the
    build.
    """
    header = json.dumps(
        {"version": 1, "meshes": {"bytes": 0, "file": meshes}}
    ).encode()
    header += b" " * (-(len(header) + 12) % 8)
    path.write_bytes(
        b"RSPL" + struct.pack("<Q", len(header)) + header + gzip.compress(b"")
    )


@pytest.fixture
def rollout_deck_folder(deck_folder):
    write_rollout(deck_folder / "assets" / "run.rollout", meshes="abc.meshes")
    (deck_folder / "assets" / "abc.meshes").write_bytes(b"meshes")
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![run](assets/run.rollout)\n"
    )
    return deck_folder


@pytest.mark.parametrize("single_file", [True, False])
def test_a_rollout_cannot_pull_a_file_from_outside_the_deck_by_naming_it(
    deck_folder, tmp_path, single_file
):
    (tmp_path / "secret.txt").write_text("SECRET-TOKEN")
    write_rollout(
        deck_folder / "assets" / "run.rollout", meshes="../../secret.txt"
    )
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![run](assets/run.rollout)\n"
    )
    out = tmp_path / "one" / "deck.html" if single_file else tmp_path / "site"
    with pytest.raises(DeckError):
        load_source(deck_folder).build(out, single_file=single_file)
    built = [
        path
        for path in tmp_path.rglob("*")
        if path.is_file() and path.parent != tmp_path
    ]
    assert all(
        "SECRET-TOKEN" not in path.read_text(errors="ignore")
        for path in built
        if deck_folder not in path.parents
    )


@pytest.mark.parametrize(
    "name",
    ["../secret.txt", "sub/abc.meshes", "..", "", "a\\b.meshes", "/etc/passwd"],
)
def test_a_mesh_name_that_is_a_path_is_refused_in_both_kinds_of_build(
    deck_folder, tmp_path, name
):
    write_rollout(deck_folder / "assets" / "run.rollout", meshes=name)
    (deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![run](assets/run.rollout)\n"
    )
    with pytest.raises(DeckError, match="plain file name"):
        load_source(deck_folder).build(
            tmp_path / "one" / "deck.html", single_file=True
        )
    with pytest.raises(DeckError, match="plain file name"):
        load_source(deck_folder).build(tmp_path / "site")


def test_a_rollout_and_its_meshes_are_inlined_and_copied(
    rollout_deck_folder, tmp_path
):
    one = (
        load_source(rollout_deck_folder)
        .build(tmp_path / "one" / "deck.html", single_file=True)
        .read_text(encoding="utf-8")
    )
    assert 'data-mkd-rollout="assets/run.rollout"' in one
    assert 'data-mkd-rollout="assets/abc.meshes"' in one
    site = tmp_path / "site"
    load_source(rollout_deck_folder).build(site)
    assert (site / "assets" / "abc.meshes").read_bytes() == b"meshes"


def test_a_rollout_src_with_a_query_is_inlined_under_the_name_the_page_asks_for(
    rollout_deck_folder, tmp_path
):
    (rollout_deck_folder / "deck.md").write_text(
        "---\ntitle: T\n---\n\nHi.\n\n![run](assets/run.rollout?v=2)\n"
    )
    html = (
        load_source(rollout_deck_folder)
        .build(tmp_path / "one" / "deck.html", single_file=True)
        .read_text(encoding="utf-8")
    )
    assert 'data-mkd-rollout="assets/run.rollout?v=2"' in html
    assert 'data-mkd-rollout="assets/abc.meshes"' in html


def test_a_damaged_rollout_is_a_deck_error(rollout_deck_folder, tmp_path):
    (rollout_deck_folder / "assets" / "run.rollout").write_bytes(
        b"RSPL" + struct.pack("<Q", 5) + b"{not-"
    )
    with pytest.raises(DeckError, match="damaged"):
        load_source(rollout_deck_folder).build(tmp_path / "site")


def test_a_rollout_that_is_not_there_is_a_warning_in_a_single_file_build(
    rollout_deck_folder, tmp_path
):
    (rollout_deck_folder / "assets" / "run.rollout").unlink()
    with pytest.warns(DeckWarning, match="run.rollout"):
        load_source(rollout_deck_folder).build(
            tmp_path / "one" / "deck.html", single_file=True
        )


def test_a_rollout_link_out_of_the_deck_is_refused(
    rollout_deck_folder, tmp_path
):
    secret = tmp_path / "secret.rollout"
    write_rollout(secret, meshes="abc.meshes")
    (rollout_deck_folder / "assets" / "run.rollout").unlink()
    (rollout_deck_folder / "assets" / "run.rollout").symlink_to(secret)
    with pytest.raises(DeckError, match="leaves the deck folder"):
        load_source(rollout_deck_folder).build(
            tmp_path / "one" / "deck.html", single_file=True
        )


def test_building_a_deck_directly_still_defaults_the_flag_to_off(
    rollout_deck_folder, tmp_path
):
    index = build_deck(
        load_source(rollout_deck_folder).deck,
        tmp_path / "site",
        source=rollout_deck_folder,
    )
    assert "EventSource" not in index.read_text(encoding="utf-8")


def test_a_single_file_build_into_the_deck_folder_still_inlines_its_extras(
    deck_folder, monkeypatch
):
    (deck_folder / "theme").mkdir()
    (deck_folder / "theme" / "mine.css").write_text("body { color: teal; }")
    monkeypatch.chdir(deck_folder)
    deck = Deck(
        title="Runs",
        extra_css=["theme/mine.css"],
        slides=[Slide(sentence="Hi.")],
    )
    deck.build("deck.html", single_file=True)
    assert "body { color: teal; }" in (deck_folder / "deck.html").read_text(
        encoding="utf-8"
    )


def test_mermaid_is_fetched_as_an_exact_release_and_checked_against_its_hash():
    script = (ASSET_ROOT / "mkdeck.js").read_text(encoding="utf-8")
    assert re.search(
        r"cdn\.jsdelivr\.net/npm/mermaid@\d+\.\d+\.\d+/dist/mermaid\.min\.js",
        script,
    )
    assert re.search(r'MERMAID_INTEGRITY = "sha384-[A-Za-z0-9+/]{64}"', script)
    assert "script.integrity = MERMAID_INTEGRITY" in script


# --------------------------------------------------------------------------- #
# What the copies look like
# --------------------------------------------------------------------------- #


def test_a_read_only_source_file_can_be_built_again(deck_folder, tmp_path):
    """The copy kept the mode of the original, so the second build could not
    write over the first.
    """
    (deck_folder / "assets" / "g3_18.html").chmod(0o444)
    site = tmp_path / "site"
    load_source(deck_folder).build(site)
    load_source(deck_folder).build(site)
    copy = site / "assets" / "g3_18.html"
    assert (
        copy.read_text(encoding="utf-8") == "<!doctype html><title>g3</title>"
    )
    assert os.access(copy, os.W_OK)


def test_a_read_only_asset_root_can_be_built_from_again(
    deck_folder, tmp_path, monkeypatch
):
    """The shipped front end may sit in a read-only place, such as a Nix
    store.
    """
    root = tmp_path / "store"
    (root / "themes").mkdir(parents=True)
    (root / "mkdeck.js").write_text("// deck")
    (root / "themes" / "minimal.css").write_text(":root {}")
    for path in (root / "mkdeck.js", root / "themes" / "minimal.css"):
        path.chmod(0o444)
    monkeypatch.setattr(build_module, "ASSET_ROOT", root)
    site = tmp_path / "site"
    load_source(deck_folder).build(site)
    load_source(deck_folder).build(site)
    assert (site / "mkdeck-assets" / "mkdeck.js").read_text(
        encoding="utf-8"
    ) == "// deck"
    assert os.access(site / "mkdeck-assets" / "themes" / "minimal.css", os.W_OK)


@pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no permission bits to copy"
)
def test_a_copy_takes_the_umask_not_the_mode_of_the_original(
    deck_folder, tmp_path
):
    """A file only its owner could read must not make a site that another
    user cannot serve.
    """
    (deck_folder / "assets" / "g3_18.html").chmod(0o600)
    before = os.umask(0o022)
    try:
        load_source(deck_folder).build(tmp_path / "site")
    finally:
        os.umask(before)
    assert (
        tmp_path / "site" / "assets" / "g3_18.html"
    ).stat().st_mode & 0o777 == 0o644


def test_a_source_folder_that_is_not_there_is_a_deck_error(tmp_path):
    with pytest.raises(DeckError, match="source folder does not exist"):
        Deck(title="T").build(tmp_path / "site", source=tmp_path / "nope")
    assert not (tmp_path / "site").exists()


def test_building_into_the_assets_folder_is_refused(deck_folder):
    """It used to copy `assets` into itself, again and again."""
    with pytest.raises(DeckError, match="assets folder"):
        load_source(deck_folder).build(deck_folder / "assets")
    with pytest.raises(DeckError, match="assets folder"):
        load_source(deck_folder).build(
            deck_folder / "assets" / "deck.html", single_file=True
        )
    assert sorted(path.name for path in (deck_folder / "assets").iterdir()) == [
        "g3_18.html"
    ]
