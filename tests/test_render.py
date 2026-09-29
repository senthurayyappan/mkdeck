"""The HTML contract: what render.py emits for each kind of slide."""

import re
import warnings
from pathlib import Path

import pytest

from mkdeck import Deck, DeckError, DeckWarning, Embed, Slide, Table
from mkdeck.inline import PAYLOAD_MARKER, SLIDES_CLOSE, SLIDES_OPEN, VIEWER_MODULES
from mkdeck.markdown import parse_markdown
from mkdeck.paths import ASSET_BASE, ASSET_ROOT
from mkdeck.render import (
    RELOAD_PATH,
    highlight_numbers,
    render_deck,
    render_slide,
    render_text,
)

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


def test_an_element_in_the_sentence_is_kept_as_written() -> None:
    rendered = str(render_text('Departure speed reaches <deck-mark type="circle">2.10 m/s</deck-mark> at 22 N m.'))
    assert '<deck-mark type="circle">2.10 m/s</deck-mark>' in rendered
    assert '<span class="mkd-num">22 N m</span>' in rendered
    assert "&lt;" not in rendered


def test_an_unclosed_tag_is_escaped() -> None:
    assert str(render_text("<b> & 3")) == '&lt;b&gt; &amp; <span class="mkd-num">3</span>'


def test_a_less_than_sign_is_escaped() -> None:
    assert "&lt;" in str(render_text("2 < 3"))


def test_markdown_keeps_an_inline_element(tmp_path) -> None:
    deck = parse_markdown(
        '---\ntitle: T\n---\n\nDeparture speed reaches <deck-mark type="circle">2.10 m/s</deck-mark> at 22 N m.\n',
        source=tmp_path / "deck.md",
    )
    html = str(render_slide(deck.slides[0]))
    assert '<deck-mark type="circle">2.10 m/s</deck-mark>' in html


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
    html = render_deck(Deck(title="Runs", slides=[Slide(sentence="Hi.")]))
    assert html.rindex("</section>") < html.index(SLIDES_CLOSE) < html.index('class="mkd-chrome mkd-chrome-left"')
    assert html.index('class="mkd-chrome mkd-chrome-left"') < html.index('class="mkd-chrome mkd-chrome-right"')


def test_reveal_scaling_is_off() -> None:
    html = render_deck(Deck(title="Runs"))
    for line in ('width: "100%"', 'height: "100%"', "margin: 0", "minScale: 1", "maxScale: 1"):
        assert line in html


def test_the_reveal_options_of_the_deck_are_merged_over_the_defaults() -> None:
    html = render_deck(Deck(title="Runs", reveal={"transition": "fade", "note": "</script>"}))
    assert 'var overrides = {"note": "\\u003c/script\\u003e", "transition": "fade"};' in html


def test_the_deck_supplies_the_unit_list() -> None:
    deck = Deck(title="Runs", title_slide=False, units=["apples"], slides=[Slide(sentence="7 apples")])
    html = render_deck(deck)
    assert '<span class="mkd-num">7 apples</span>' in html


def test_an_empty_unit_list_drops_the_unit_spellings() -> None:
    deck = Deck(title="Runs", title_slide=False, units=[], slides=[Slide(sentence="under 22 N m")])
    html = render_deck(deck)
    assert '<span class="mkd-num">22</span> N m' in html
    assert '<span class="mkd-num">22 N m</span>' not in html


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


def test_inline_markdown_is_rendered_in_text() -> None:
    rendered = str(render_text("**bold**, *em*, `code 5` and [a link](https://example.org/a?b=1&c=2)."))
    assert "<strong>bold</strong>" in rendered
    assert "<em>em</em>" in rendered
    assert "<code>code 5</code>" in rendered  # no number highlighting inside code
    assert '<a href="https://example.org/a?b=1&amp;c=2">a link</a>' in rendered


def test_numbers_are_highlighted_inside_emphasis_but_not_labels() -> None:
    assert '<strong><span class="mkd-num">22 N m</span></strong>' in str(render_text("**22 N m**"))
    assert str(render_text("**22 N m**", numbers=False)) == "<strong>22 N m</strong>"


def test_a_script_link_cannot_be_written_in_markdown() -> None:
    assert "href" not in str(render_text("[x](javascript:alert(1))"))


def test_markdown_spans_can_wrap_math() -> None:
    assert '<strong>a <span class="mkd-math" data-tex="x^2"></span></strong>' in str(render_text("**a $x^2$**"))


def test_dollar_amounts_are_text_and_an_escaped_dollar_is_a_dollar() -> None:
    assert "mkd-math" not in str(render_text("costs $5 and $10 today"))
    assert "mkd-math" not in str(render_text("costs $ 5 and 6 $ today"))
    rendered = str(render_text(r"it costs \$5 and $y$ is math"))
    assert rendered.count("mkd-math") == 1
    assert 'data-tex="y"' in rendered
    assert "\\" not in rendered


def test_math_is_not_read_inside_inline_code() -> None:
    assert "mkd-math" not in str(render_text("write `$a$ and $b$` in TeX"))


def test_a_greater_than_sign_inside_an_attribute_does_not_end_the_tag() -> None:
    rendered = str(render_text('<img src="a>b.png"> and 5'))
    assert '<img src="a>b.png">' in rendered
    assert '<span class="mkd-num">5</span>' in rendered


def test_elements_of_the_same_name_nest() -> None:
    rendered = str(render_text("<span>a<span>b</span>c 2.5</span> then 7"))
    assert rendered.startswith("<span>a<span>b</span>c 2.5</span> then ")
    assert '<span class="mkd-num">7</span>' in rendered


def test_a_tag_inside_inline_code_is_shown_not_run() -> None:
    assert "<code>&lt;b&gt;x&lt;/b&gt;</code>" in str(render_text("`<b>x</b>`"))


def test_an_open_tag_and_a_stray_close_tag_are_text() -> None:
    assert str(render_text("a </i> b")) == "a &lt;/i&gt; b"
    assert str(render_text("<i>only opened")) == "&lt;i&gt;only opened"


def test_an_html_comment_in_text_is_kept() -> None:
    assert str(render_text("a <!-- c --> b")) == "a <!-- c --> b"


def test_units_may_be_listed_in_any_order() -> None:
    for units in (["m", "N m", "N m s/rad"], ["N m s/rad", "N m", "m"]):
        assert str(highlight_numbers("0.65 N m s/rad", units=units)) == '<span class="mkd-num">0.65 N m s/rad</span>'
        assert str(highlight_numbers("under 22 N m", units=units)) == 'under <span class="mkd-num">22 N m</span>'


def test_quotes_are_escaped_in_the_label_the_src_and_the_id() -> None:
    slide = Slide(id='a"b', embeds=[Embed('x".html', label='say "hi"'), Embed("i'm.png", label="it's")])
    rendered = str(render_slide(slide))
    assert 'data-id="a&#34;b"' in rendered
    assert '<deck-embed src="x&#34;.html">' in rendered
    assert '<img class="mkd-image" src="i&#39;m.png" alt="it&#39;s">' in rendered
    assert "say &#34;hi&#34;" in rendered
    assert '"hi"' not in rendered


def test_a_class_name_cannot_break_out_of_the_attribute() -> None:
    rendered = str(render_slide(Slide(sentence="Hi.", classes=['x" onclick="alert(1)'])))
    assert 'onclick="' not in rendered


def test_a_heading_with_a_body_is_drawn_above_the_body() -> None:
    slide = parse_markdown("# Big Title\n\nSome sentence.\n", source=Path("deck.md")).slides[0]
    rendered = str(render_slide(slide))
    assert '<h1 class="mkd-title">Big Title</h1>' in rendered
    assert rendered.index("mkd-title") < rendered.index("mkd-sentence")
    assert 'data-layout="statement"' in rendered


def test_a_heading_is_drawn_above_figures_and_a_table_too() -> None:
    figures = str(render_slide(Slide(title="Heading", embeds=[Embed("a.html")])))
    table = str(render_slide(Slide(title="Heading", table=Table(columns=["a"], rows=[["1"]]))))
    assert figures.index("mkd-title") < figures.index("mkd-figures")
    assert table.index("mkd-title") < table.index("mkd-table")


def test_the_heading_takes_inline_math_and_markdown() -> None:
    rendered = str(render_slide(Slide(title="Gain $k_p$ is *tuned*", sentence="Hi.")))
    assert 'data-tex="k_p"' in rendered
    assert "<em>tuned</em>" in rendered


def test_a_slide_of_the_wrong_type_is_a_deck_error_not_an_attribute_error() -> None:
    with pytest.raises(DeckError, match='The field "sentence" has to be text'):
        render_deck(Deck(title="Runs", slides=[Slide(sentence=5)]))  # ty: ignore[invalid-argument-type]


def test_an_unknown_theme_is_refused_before_it_is_linked() -> None:
    with pytest.raises(DeckError, match=r'The theme "\.\./\.\./x" does not exist'):
        render_deck(Deck(title="Runs", theme="../../x"))
    assert 'themes/dark.css"' in render_deck(Deck(title="Runs", theme="dark"))


def test_a_stylesheet_outside_the_folder_is_refused_by_the_renderer() -> None:
    with pytest.raises(DeckError, match='under "extra_css"'):
        render_deck(Deck(title="Runs", extra_css=["../a.css"]))


def test_the_units_of_a_deck_have_to_be_text() -> None:
    with pytest.raises(DeckError, match='"units"'):
        render_deck(Deck(title="Runs", units=[3]))  # ty: ignore[invalid-argument-type]


def test_a_file_name_with_a_colon_is_written_so_a_browser_reads_it_as_a_path() -> None:
    rendered = str(render_slide(Slide(embeds=[Embed("run:3.html")])))
    assert '<deck-embed src="./run:3.html">' in rendered


def test_a_query_stays_in_the_document() -> None:
    rendered = str(render_slide(Slide(embeds=[Embed("figs/g3_18.html?seed=2")])))
    assert '<deck-embed src="figs/g3_18.html?seed=2">' in rendered


def test_the_live_reload_client_is_only_there_when_asked_for() -> None:
    plain = render_deck(Deck(title="Runs"))
    live = render_deck(Deck(title="Runs"), live_reload=True)
    assert "EventSource" not in plain
    assert RELOAD_PATH not in plain
    assert live.count("EventSource") == 1
    assert f'new EventSource("{RELOAD_PATH}")' in live
    assert live.rindex("EventSource") < live.rindex("</body>")


def test_the_template_carries_the_markers_the_single_file_build_looks_for() -> None:
    html = render_deck(Deck(title="Runs", slides=[Slide(sentence="Hi.")]))
    assert html.count(PAYLOAD_MARKER) == 1
    assert html.index(SLIDES_OPEN) < html.index("<section") < html.index(SLIDES_CLOSE)


def test_every_asset_the_document_names_is_on_disk() -> None:
    deck = Deck(title="Runs", slides=[Slide(embeds=[Embed("a.rollout")])])
    html = render_deck(deck)
    urls = re.findall(rf'(?:href|src)="({ASSET_BASE}/[^"]+)"', html)
    assert len(urls) > 10
    for url in urls:
        assert (ASSET_ROOT / url.removeprefix(f"{ASSET_BASE}/")).is_file(), url


def test_the_viewer_modules_are_on_disk_and_match_the_ones_the_browser_loads() -> None:
    for _, path in VIEWER_MODULES:
        assert (ASSET_ROOT / path).is_file(), path
    script = (ASSET_ROOT / "mkdeck-rollout.js").read_text(encoding="utf-8")
    block = script[script.index("var MODULES = [") :].split("];", 1)[0]
    assert re.findall(r'\["([^"]+)", "([^"]+)"\]', block) == list(VIEWER_MODULES)


def test_an_image_inside_a_bullet_or_a_cell_is_called_out_when_it_is_a_local_file() -> None:
    with pytest.warns(DeckWarning, match=r'"assets/icon.png".*on a line of its own'):
        html = str(render_slide(Slide(bullets=["a ![icon](assets/icon.png) bullet"])))
    assert '<img src="assets/icon.png" alt="icon" />' in html  # the text is still drawn as written
    with pytest.warns(DeckWarning, match="assets/cell.png"):
        render_slide(Slide(table=Table(columns=["Run"], rows=[["![](assets/cell.png)"]])))


def test_a_remote_image_inside_a_bullet_needs_no_copy_and_is_not_called_out() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeckWarning)
        render_slide(Slide(bullets=["![logo](https://example.org/logo.png)"]))
