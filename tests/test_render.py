"""The HTML contract: what render.py emits for each kind of slide."""

import pytest

from mkdeck import Deck, DeckError, Embed, Slide, Table, parse_markdown, render_deck
from mkdeck.config import DeckConfig
from mkdeck.render import highlight_numbers, render_slide, render_text

STATEMENT = (
    '<section class="mkd-slide" data-layout="statement" data-id="g8b-recommendation">'
    '<div class="mkd-body">'
    '<p class="mkd-sentence">Raising the cap changes how the wall is crossed, not whether it is crossed.</p>'
    '<ul class="mkd-bullets"><li>five seeds cross</li><li>the peak stays under '
    '<span class="mkd-num">22 N m</span></li></ul>'
    "</div></section>"
)

FIGURES = (
    '<section class="mkd-slide" data-layout="figures" data-id="g3-paired">'
    '<div class="mkd-body">'
    '<p class="mkd-sentence">Body load falls from <span class="mkd-num">134</span> to '
    '<span class="mkd-num">86</span> N s.</p>'
    '<div class="mkd-figures" data-count="2">'
    '<figure class="mkd-figure"><figcaption class="mkd-label">18 N m</figcaption>'
    '<deck-embed src="assets/g3_18.html"></deck-embed></figure>'
    '<figure class="mkd-figure"><figcaption class="mkd-label">22 N m</figcaption>'
    '<deck-embed src="assets/g3_22.html"></deck-embed></figure>'
    "</div></div></section>"
)

TITLE = (
    '<section class="mkd-slide" data-layout="title" data-date="2026-09-18">'
    '<div class="mkd-body"><h1 class="mkd-title">Quadruped Vault Runs</h1>'
    '<p class="mkd-date">2026-09-18</p></div></section>'
)


def test_a_bare_number_is_highlighted() -> None:
    assert str(highlight_numbers("five of 5 runs")) == 'five of <span class="mkd-num">5</span> runs'


def test_a_number_glued_to_letters_stays_grey() -> None:
    assert str(highlight_numbers("the Go2 crosses")) == "the Go2 crosses"


def test_a_number_takes_its_unit_with_it() -> None:
    assert str(highlight_numbers("under 22 N m")) == 'under <span class="mkd-num">22 N m</span>'


def test_the_longest_unit_wins() -> None:
    assert str(highlight_numbers("a gap of 5 mm")) == 'a gap of <span class="mkd-num">5 mm</span>'


def test_signs_and_decimals_are_part_of_the_number() -> None:
    assert str(highlight_numbers("-0.65 m")) == '<span class="mkd-num">-0.65 m</span>'


def test_the_unit_list_is_configurable() -> None:
    assert str(highlight_numbers("7 apples", units=["apples"])) == '<span class="mkd-num">7 apples</span>'
    assert str(highlight_numbers("7 apples", units=[])) == '<span class="mkd-num">7</span> apples'


def test_text_is_escaped_around_the_numbers() -> None:
    assert str(highlight_numbers("<b> & 3")) == '&lt;b&gt; &amp; <span class="mkd-num">3</span>'


def test_inline_math_becomes_a_placeholder() -> None:
    rendered = str(render_text("spread $5\\times10^{-7}$ rad"))
    assert '<span class="mkd-math" data-tex="5\\times10^{-7}"></span>' in rendered
    assert rendered.startswith("spread ")


def test_an_odd_number_of_dollar_signs_is_plain_text() -> None:
    assert str(render_text("costs $5 today")) == 'costs $<span class="mkd-num">5</span> today'


def test_a_statement_slide_matches_the_contract() -> None:
    slide = Slide(
        id="g8b-recommendation",
        sentence="Raising the cap changes how the wall is crossed, not whether it is crossed.",
        bullets=["five seeds cross", "the peak stays under 22 N m"],
    )
    assert str(render_slide(slide)) == STATEMENT


def test_a_figure_slide_matches_the_contract() -> None:
    slide = Slide(
        id="g3-paired",
        sentence="Body load falls from 134 to 86 N s.",
        embeds=[Embed("assets/g3_18.html", label="18 N m"), Embed("assets/g3_22.html", label="22 N m")],
    )
    assert str(render_slide(slide)) == FIGURES


def test_a_label_keeps_one_weight() -> None:
    rendered = str(render_slide(Slide(embeds=[Embed("a.html", label="18 N m")])))
    assert '<figcaption class="mkd-label">18 N m</figcaption>' in rendered


def test_an_image_embed_uses_an_img_in_the_same_wrapper() -> None:
    rendered = str(render_slide(Slide(embeds=[Embed("assets/clip.gif", label="climb")])))
    assert '<figure class="mkd-figure"><figcaption class="mkd-label">climb</figcaption>' in rendered
    assert '<img class="mkd-image" src="assets/clip.gif" alt="climb">' in rendered
    assert 'data-count="1"' in rendered


def test_a_table_highlights_the_body_cells_only() -> None:
    table = Table(columns=["Run", "18 N m"], rows=[["baseline", "2"]])
    rendered = str(render_slide(Slide(table=table)))
    assert '<div class="mkd-table-wrap"><table class="mkd-table">' in rendered
    assert "<thead><tr><th>Run</th><th>18 N m</th></tr></thead>" in rendered
    assert '<tbody><tr><td>baseline</td><td><span class="mkd-num">2</span></td></tr></tbody>' in rendered


def test_a_title_slide_matches_the_contract() -> None:
    slide = Slide(layout="title", title="Quadruped Vault Runs")
    assert str(render_slide(slide, date="2026-09-18")) == TITLE


def test_display_math_comes_before_the_sentence() -> None:
    rendered = str(render_slide(Slide(math=["a = b"], sentence="Why.")))
    assert rendered.index('class="mkd-math mkd-math-block" data-tex="a = b"') < rendered.index("mkd-sentence")


def test_two_paragraphs_become_two_sentences() -> None:
    rendered = str(render_slide(Slide(sentence="First line.\n\nSecond line.")))
    assert rendered.count('<p class="mkd-sentence">') == 2


def test_speaker_notes_use_reveals_own_element() -> None:
    rendered = str(render_slide(Slide(sentence="Hi.", notes="Say this out loud.")))
    assert '<aside class="notes"><p>Say this out loud.</p></aside>' in rendered


def test_extra_classes_and_the_id_reach_the_section() -> None:
    rendered = str(render_slide(Slide(id="a1", classes=["wide"], sentence="Hi.")))
    assert rendered.startswith('<section class="mkd-slide wide" data-layout="statement" data-id="a1">')


def test_raw_html_is_kept_beside_the_rest() -> None:
    rendered = str(render_slide(Slide(sentence="Hi.", html="<deck-mermaid>graph TD</deck-mermaid>")))
    assert "<deck-mermaid>graph TD</deck-mermaid>" in rendered
    assert "Hi." in rendered


def test_three_embeds_are_refused_by_name() -> None:
    slide = Slide(id="too-many", embeds=[Embed("a.html"), Embed("b.html"), Embed("c.html")])
    with pytest.raises(DeckError, match="too-many"):
        render_slide(slide, index=3)


def test_a_deck_opens_with_a_generated_title_slide() -> None:
    html = render_deck(Deck(title="Runs", date="2026-09-18", slides=[Slide(sentence="Hi.")]))
    assert html.count("<section") == 2
    assert '<h1 class="mkd-title">Runs</h1>' in html


def test_a_deck_that_writes_its_own_title_slide_is_not_doubled() -> None:
    deck = Deck(title="Runs", slides=[Slide(layout="title", title="Runs"), Slide(sentence="Hi.")])
    assert render_deck(deck).count("<section") == 2


def test_the_title_slide_can_be_turned_off() -> None:
    deck = Deck(title="Runs", slides=[Slide(sentence="Hi.")], title_slide=False)
    assert render_deck(deck).count("<section") == 1


def test_a_section_title_restamps_the_slides_after_it() -> None:
    deck = Deck(
        title="Runs",
        date="2026-09-18",
        title_slide=False,
        slides=[Slide(layout="title", title="Part two", date="2026-09-19")],
    )
    assert 'data-date="2026-09-19"' in render_deck(deck)


def test_the_document_links_its_assets_in_order() -> None:
    html = render_deck(Deck(title="Runs"))
    order = [
        "roboto/roboto.css",
        "reveal.js/dist/reset.css",
        "reveal.js/dist/reveal.css",
        "katex/dist/katex.min.css",
        "themes/minimal.css",
        "mkdeck.css",
        "reveal.js/dist/reveal.js",
        "reveal.js/dist/plugin/notes.js",
        "reveal.js/dist/plugin/zoom.js",
        "katex/dist/katex.min.js",
        "mkdeck.js",
    ]
    found = [html.index(f"mkdeck-assets/{name}") for name in order]
    assert found == sorted(found)


def test_the_chrome_sits_outside_the_slides() -> None:
    html = render_deck(Deck(title="Runs"))
    assert html.index("</div>") < html.index('class="mkd-chrome mkd-chrome-left"')
    assert 'class="mkd-chrome mkd-chrome-right"' in html


def test_reveal_scaling_is_off() -> None:
    html = render_deck(Deck(title="Runs"))
    assert "minScale" in html and "maxScale" in html


def test_the_config_supplies_the_unit_list() -> None:
    deck = Deck(title="Runs", title_slide=False, slides=[Slide(sentence="7 apples")])
    html = render_deck(deck, config=DeckConfig(units=["apples"]))
    assert '<span class="mkd-num">7 apples</span>' in html


def test_a_python_deck_and_the_same_markdown_render_alike(tmp_path) -> None:
    text = (
        "---\ntitle: Runs\ndate: 2026-09-18\n---\n\n"
        "<!--\nid: one\n-->\n\n"
        "Body load falls from 134 to 86 N s.\n\n"
        "![18 N m](assets/g3_18.html)\n"
        "![22 N m](assets/g3_22.html)\n"
    )
    parsed = parse_markdown(text, source=tmp_path / "deck.md")
    built = Deck(
        title="Runs",
        date="2026-09-18",
        slides=[
            Slide(
                id="one",
                sentence="Body load falls from 134 to 86 N s.",
                embeds=[
                    Embed("assets/g3_18.html", label="18 N m", kind="iframe"),
                    Embed("assets/g3_22.html", label="22 N m", kind="iframe"),
                ],
            )
        ],
    )
    assert render_deck(parsed) == render_deck(built)
