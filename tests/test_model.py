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
    validate_src,
)

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
        ("/home/holycow/barkour-dmpc/slides/assets/a1.html", "absolute"),
        ("C:/decks/a1.html", "absolute"),
        ("../../barkour-dmpc/slides/assets/a1.html", "leaves the deck folder"),
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
    ["assets/a1_go2_crate.html", "./assets/a1.html", "sub/../assets/a1.html", "https://example.org/a1.html"],
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
    assert str(caught.value).startswith('deck.md: slide 3 "a1-crate": repeats the id of slide 1')


def test_validate_deck_checks_every_slide() -> None:
    deck = Deck(title="Quadruped Vault Runs", slides=[CRATE, Slide(table=Table(columns=[], rows=[]))])
    with pytest.raises(DeckError, match="slide 2"):
        validate_deck(deck)


def test_deck_error_without_a_source_or_slide_is_the_bare_message() -> None:
    assert str(DeckError("nothing to render.")) == "nothing to render."
