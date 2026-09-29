import pytest

from mkdeck.errors import DeckError
from mkdeck.model import (
    Deck,
    Embed,
    Slide,
    Table,
    resolve_embed_kind,
    resolve_layout,
    slide_name,
    validate_deck,
    validate_slide,
)
from mkdeck.paths import asset_path_error, is_remote, local_path, relative_url, validate_src

# The two-figure slide "a1-crate" of the barkour deck.
CRATE = Slide(
    id="a1-crate",
    sentence=(
        "The Go2 finishes standing on the 0.60 m crate with its torso at 0.83 m. "
        "The Barkour CAD model stops against the near face with its torso at 0.59 m."
    ),
    embeds=[
        Embed("assets/a1_go2_crate.html", label="Unitree Go2"),
        Embed("assets/a1_cad_crate.html", label="Barkour CAD"),
    ],
)

# The table slide "c1-model-table" of the barkour deck.
MODEL_TABLE = Slide(
    id="c1-model-table",
    sentence="Model differences that matter for the vault, as of 16 September.",
    table=Table(
        columns=["Property", "Unitree Go2", "Barkour CAD"],
        rows=[
            ["Total mass", "15.21 kg", "11.31 kg"],
            ["Motor torque cap", "No", "18 N m, all twelve motors"],
            ["Passive joint damping", "0.65 N m s/rad", "0.65 copied, now 0.024 (hardware)"],
        ],
    ),
)

SECTION_TITLE = Slide(
    id="d0-title",
    layout="title",
    title="Barkour CAD: retuned gains, same reward ladder",
    date="2026-09-17",
)


def test_slide_defaults_are_empty() -> None:
    slide = Slide()
    assert slide.id is None
    assert slide.layout == "auto"
    assert slide.bullets == []
    assert slide.math == []
    assert slide.embeds == []
    assert slide.table is None
    assert slide.classes == []


def test_deck_defaults() -> None:
    deck = Deck(title="Quadruped Vault Runs")
    assert deck.theme == "minimal"
    assert deck.title_slide is True
    assert deck.slides == []
    assert deck.reveal == {}


def test_auto_layout_prefers_embeds_over_a_table() -> None:
    assert resolve_layout(CRATE) == "figures"
    assert resolve_layout(MODEL_TABLE) == "table"
    assert resolve_layout(Slide(sentence="Five seeds cross the wall.")) == "statement"
    assert resolve_layout(SECTION_TITLE) == "title"


def test_auto_layout_leaves_an_explicit_layout_alone() -> None:
    slide = Slide(layout="statement", embeds=[Embed("assets/g3_18.html")])
    assert resolve_layout(slide) == "statement"


@pytest.mark.parametrize(
    ("src", "kind"),
    [
        ("assets/a1_go2_crate.html", "iframe"),
        ("assets/run_035110.htm", "iframe"),
        ("assets/f4_twitch.gif", "image"),
        ("assets/g3_18.png", "image"),
        ("assets/g3_18.html?seed=2", "iframe"),
    ],
)
def test_auto_embed_kind_follows_the_suffix(src: str, kind: str) -> None:
    assert resolve_embed_kind(Embed(src)) == kind


def test_explicit_embed_kind_wins() -> None:
    assert resolve_embed_kind(Embed("assets/g3_18.html", kind="image")) == "image"


def test_slide_name_uses_the_id_then_the_index() -> None:
    assert slide_name(CRATE, 4) == 'slide 5 "a1-crate"'
    assert slide_name(Slide(), 4) == "slide 5"


def test_a_valid_slide_passes() -> None:
    validate_slide(CRATE, index=0)
    validate_slide(MODEL_TABLE, index=1)
    validate_slide(SECTION_TITLE, index=2)


def test_three_embeds_are_rejected_and_the_slide_is_named() -> None:
    slide = Slide(
        id="g3-paired",
        embeds=[Embed("assets/g3_18.html"), Embed("assets/g3_22.html"), Embed("assets/g3_26.html")],
    )
    with pytest.raises(DeckError) as caught:
        validate_slide(slide, index=2, source="deck.md")
    message = str(caught.value)
    assert message.startswith('deck.md: slide 3 "g3-paired": ')
    assert "3 embeds" in message
    assert "at most 2" in message


def test_an_unnamed_slide_is_reported_by_its_index() -> None:
    slide = Slide(embeds=[Embed("assets/a.html"), Embed("assets/b.html"), Embed("assets/c.html")])
    with pytest.raises(DeckError, match=r"^slide 7: "):
        validate_slide(slide, index=6)


@pytest.mark.parametrize(
    ("src", "reason"),
    [
        ("/srv/decks/vault/assets/a1.html", "absolute"),
        ("C:/decks/a1.html", "absolute"),
        ("../../other-project/assets/a1.html", "leaves the deck folder"),
        ("", "empty src"),
        ("file:///tmp/a1.html", "is not supported"),
    ],
)
def test_bad_embed_sources_are_rejected(src: str, reason: str) -> None:
    assert reason in (validate_src(src) or "")
    with pytest.raises(DeckError, match=reason):
        validate_slide(Slide(id="b1", embeds=[Embed(src)]), index=0)


@pytest.mark.parametrize(
    "src",
    [
        "assets/a1_go2_crate.html",
        "./assets/a1.html",
        "sub/../assets/a1.html",
        "https://example.org/a1.html",
        "HTTPS://example.org/a1.html",
        "figs/g3_18.html?seed=2#top",
        "run:3.html",
        "run:3/plot.html",
    ],
)
def test_good_embed_sources_pass(src: str) -> None:
    assert validate_src(src) is None


def test_a_table_needs_columns() -> None:
    slide = Slide(id="c1-model-table", table=Table(columns=[], rows=[["Total mass", "15.21 kg"]]))
    with pytest.raises(DeckError, match="no columns"):
        validate_slide(slide, index=0)


def test_every_row_matches_the_columns() -> None:
    slide = Slide(
        id="c1-model-table",
        table=Table(
            columns=["Property", "Unitree Go2", "Barkour CAD"],
            rows=[["Total mass", "15.21 kg", "11.31 kg"], ["Motor torque cap", "No"]],
        ),
    )
    with pytest.raises(DeckError) as caught:
        validate_slide(slide, index=0)
    assert "row 2 holds 2 cells" in str(caught.value)


def test_an_unknown_layout_lists_the_layouts() -> None:
    slide = Slide(id="b1-position", layout="figure")  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError) as caught:
        validate_slide(slide, index=0)
    assert "figures" in str(caught.value)
    assert "statement" in str(caught.value)


def test_duplicate_ids_are_rejected() -> None:
    deck = Deck(title="Quadruped Vault Runs", slides=[CRATE, MODEL_TABLE, CRATE])
    with pytest.raises(DeckError) as caught:
        validate_deck(deck, source="deck.md")
    assert str(caught.value).startswith('deck.md: slide 3 "a1-crate": This slide repeats the id of slide 1')


def test_validate_deck_checks_every_slide() -> None:
    deck = Deck(title="Quadruped Vault Runs", slides=[CRATE, Slide(table=Table(columns=[], rows=[]))])
    with pytest.raises(DeckError, match="slide 2"):
        validate_deck(deck)


def test_deck_error_without_a_source_or_slide_is_the_bare_message() -> None:
    assert str(DeckError("nothing to render.")) == "nothing to render."


@pytest.mark.parametrize(
    "src",
    [
        "%2e%2e/secret.html",
        "..%2fsecret.html",
        "%2Fetc/passwd",
        "javascript:alert(1)",
        "data:text/html,x",
        "ftp://host/a.html",
    ],
)
def test_encoded_and_scripted_sources_are_rejected(src: str) -> None:
    assert validate_src(src) is not None


def test_a_query_or_fragment_is_not_part_of_the_file_name() -> None:
    assert local_path("figs/g3_18.html?seed=2#top") == "figs/g3_18.html"
    assert local_path("figs/g3.html#a?b") == "figs/g3.html"
    assert local_path("assets/big%20plot.html") == "assets/big plot.html"
    assert resolve_embed_kind(Embed("figs/g3_18.png?seed=2")) == "image"
    assert resolve_embed_kind(Embed("runs/a.rollout?v=2")) == "rollout"


def test_remote_is_decided_once_and_in_any_case() -> None:
    for src in ("http://x/a.html", "HTTPS://x/a.html", "//cdn.example.org/a.css", "DATA:image/png;base64,AA"):
        assert is_remote(src)
    for src in ("assets/a.html", "run:3.html", "./http://x"):
        assert not is_remote(src)


def test_a_file_name_with_a_colon_is_written_as_a_path() -> None:
    assert relative_url("run:3.html") == "./run:3.html"
    assert relative_url("assets/run:3.html") == "assets/run:3.html"  # a colon after a slash is already a path
    assert relative_url("assets/a.html") == "assets/a.html"
    assert relative_url("https://x/a:b.html") == "https://x/a:b.html"


def test_a_stylesheet_path_follows_the_embed_rule() -> None:
    assert asset_path_error("theme/mine.css", key="extra_css") is None
    assert asset_path_error("HTTPS://cdn.example.org/a.css", key="extra_css") is None
    message = asset_path_error("../a.css", key="extra_css")
    assert message is not None
    assert message.startswith('The path "../a.css" under "extra_css" has to stay inside the deck folder')


def test_embeds_and_a_table_cannot_share_a_slide() -> None:
    slide = Slide(id="both", embeds=[Embed("a.html")], table=Table(columns=["a"], rows=[["1"]]))
    with pytest.raises(DeckError, match='slide 1 "both": This slide holds both figures and a table'):
        validate_slide(slide, index=0)


def test_a_slide_without_a_position_is_named_without_a_number() -> None:
    assert slide_name(Slide()) == "slide"
    assert slide_name(Slide(id="a1")) == 'slide "a1"'
    with pytest.raises(DeckError, match=r'^slide "b": '):
        validate_slide(Slide(id="b", layout="nope"))  # ty: ignore[invalid-argument-type]


@pytest.mark.parametrize(
    ("slide", "field"),
    [
        (Slide(sentence=5), "sentence"),  # ty: ignore[invalid-argument-type]
        (Slide(id=3), "id"),  # ty: ignore[invalid-argument-type]
        (Slide(bullets="one"), "bullets"),  # ty: ignore[invalid-argument-type]
        (Slide(bullets=["a", 2]), "bullets"),  # ty: ignore[invalid-argument-type]
        (Slide(classes="wide"), "classes"),  # ty: ignore[invalid-argument-type]
        (Slide(embeds=["a.html"]), "embeds"),  # ty: ignore[invalid-argument-type]
        (Slide(embeds=[Embed(3)]), "src"),  # ty: ignore[invalid-argument-type]
        (Slide(embeds=[Embed("a.html", label=3)]), "label"),  # ty: ignore[invalid-argument-type]
    ],
)
def test_a_field_of_the_wrong_type_is_a_deck_error_naming_it(slide: Slide, field: str) -> None:
    with pytest.raises(DeckError, match=f'The field "{field}" has to') as caught:
        validate_slide(slide, index=1)
    assert str(caught.value).startswith("slide 2")


def test_a_table_that_is_not_a_table_is_a_deck_error() -> None:
    with pytest.raises(DeckError, match="not a Table"):
        validate_slide(Slide(table=[["a"]]))  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError, match="holds no list of cells"):
        validate_slide(Slide(table=Table(columns=["a"], rows=["x"])))  # ty: ignore[invalid-argument-type]


def test_a_deck_with_the_wrong_types_is_a_deck_error() -> None:
    with pytest.raises(DeckError, match='The field "title" has to be text'):
        validate_deck(Deck(title=None))  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError, match='"reveal" has to be a mapping'):
        validate_deck(Deck(title="T", reveal=[]))  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError, match='"title_slide" has to be true or false'):
        validate_deck(Deck(title="T", title_slide="yes"))  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError, match="list of Slide objects"):
        validate_deck(Deck(title="T", slides=["one"]))  # ty: ignore[invalid-argument-type]
    with pytest.raises(DeckError, match='The field "extra_css" has to be a list'):
        validate_deck(Deck(title="T", extra_css="a.css"))  # ty: ignore[invalid-argument-type]


def test_a_deck_with_an_unknown_theme_is_a_deck_error() -> None:
    with pytest.raises(DeckError, match='The theme "nope" does not exist'):
        validate_deck(Deck(title="T", theme="nope"))
    with pytest.raises(DeckError, match='Did you mean "dark"'):
        validate_deck(Deck(title="T", theme="drak"))
    with pytest.raises(DeckError, match="does not exist"):
        validate_deck(Deck(title="T", theme="../../x"))
    validate_deck(Deck(title="T", theme="dark"))


def test_a_deck_stylesheet_outside_the_folder_is_a_deck_error() -> None:
    with pytest.raises(DeckError, match='under "extra_js"'):
        validate_deck(Deck(title="T", extra_js=["../x.js"]))


def test_the_layouts_and_kinds_are_the_literals() -> None:
    from mkdeck.model import EMBED_KINDS, LAYOUTS

    assert LAYOUTS == ("auto", "title", "statement", "figures", "table")
    assert EMBED_KINDS == ("auto", "iframe", "image", "rollout")


def test_three_embeds_are_refused_by_name() -> None:
    slide = Slide(id="too-many", embeds=[Embed("a.html"), Embed("b.html"), Embed("c.html")])
    with pytest.raises(DeckError, match='slide 4 "too-many"'):
        validate_slide(slide, index=3)


def test_figures_and_a_table_are_refused_by_name() -> None:
    slide = Slide(id="both", embeds=[Embed("a.html")], table=Table(columns=["a"], rows=[["1"]]))
    with pytest.raises(DeckError, match='slide 5 "both"'):
        validate_slide(slide, index=4)


def test_an_error_without_an_index_does_not_claim_to_be_slide_one() -> None:
    with pytest.raises(DeckError) as caught:
        validate_slide(Slide(embeds=[Embed("a.html"), Embed("b.html"), Embed("c.html")]))
    assert not str(caught.value).startswith("slide 1")
