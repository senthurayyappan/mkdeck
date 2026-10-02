from pathlib import Path

import pytest

from mkdeck.errors import DeckError
from mkdeck.markdown import parse_markdown, split_frontmatter
from mkdeck.model import Slide, resolve_layout

SOURCE = Path("slides/deck.md")

# The barkour deck, written in the mkdeck Markdown format: the two-figure
# crate slide, the model table, a section title that restamps the date, the
# diagnostics slide with bullets and a display formula, and a paired-figure
# slide.
DECK = r"""---
title: "Barkour vault: model mismatch, lean formulation, open problems"
date: 2026-09-16
units: [N m, kg, m, percent]
---

# Barkour vault

---
<!--
id: a1-crate
-->

The Go2 finishes standing on the 0.60 m crate with its torso at 0.83 m.
The Barkour CAD model stops against the near face with its torso at 0.59 m.

![Unitree Go2](assets/a1_go2_crate.html)
![Barkour CAD](assets/a1_cad_crate.html)

---
<!-- id: c1-model-table -->

Model differences that matter for the vault, as of 16 September.

| Property | Unitree Go2 | Barkour CAD |
| --- | --- | --- |
| Total mass | 15.21 kg | 11.31 kg |
| Motor torque cap | No | 18 N m, all twelve motors |
| Passive joint damping | 0.65 N m s/rad | 0.65 copied, now 0.024 (hardware) |

---
<!--
id: d0-title
date: 2026-09-17
-->

# Barkour CAD: retuned gains, same reward ladder

---
<!-- id: e0-status -->

Status on 2026-09-17, after the GPU replay.
The median spread is $5\times10^{-7}$ rad.

$$W_{\text{net}}=\sum_{\text{substeps}}\ \sum_{j=1}^{12}\tau_j\,\Delta q_j$$

- Source: one DIAL-MPC rollout, 250 controls of 20 ms, four 5 ms substeps each.
- Replay: MJX on the GPU reproduces every saved state bit for bit.

<!-- notes: the 42 J difference is the 5 ms integrator, not a loss -->

---
<!--
id: g3-paired
classes: [wide]
-->

Body load on the wall falls from 134 to 86 N s.

::: figures
![18 N m](assets/g3_18.html)
![22 N m](assets/g3_22.html)
:::

::: notes
Say that the cap changes how the wall is crossed, not whether it is crossed.
:::

---
<!-- id: f4-twitch -->

![Twitch and flip](assets/f4_twitch.gif)
"""


def parse(text: str = DECK) -> list[Slide]:
    return parse_markdown(text, source=SOURCE).slides


def by_id(slide_id: str) -> Slide:
    return next(slide for slide in parse() if slide.id == slide_id)


def test_the_frontmatter_becomes_the_deck_settings() -> None:
    deck = parse_markdown(DECK, source=SOURCE)
    assert (
        deck.title
        == "Barkour vault: model mismatch, lean formulation, open problems"
    )
    assert deck.date == "2026-09-16"
    assert deck.theme == "minimal"
    assert deck.title_slide is True
    assert len(deck.slides) == 7


def test_a_file_without_frontmatter_is_all_body() -> None:
    text = "# Barkour vault\n"
    assert split_frontmatter(text, source=SOURCE) == ({}, text)


def test_an_unclosed_frontmatter_block_is_an_error() -> None:
    with pytest.raises(DeckError, match="never closed"):
        split_frontmatter(
            "---\ntitle: Barkour vault\n\n# Barkour vault\n", source=SOURCE
        )


def test_frontmatter_that_is_not_settings_is_an_error() -> None:
    with pytest.raises(DeckError, match="does not hold deck settings"):
        split_frontmatter("---\n- Barkour vault\n---\n", source=SOURCE)


def test_a_lone_heading_is_a_title_slide() -> None:
    first = parse()[0]
    assert first.layout == "title"
    assert first.title == "Barkour vault"
    assert first.sentence is None
    assert resolve_layout(first) == "title"


def test_a_section_title_carries_its_date() -> None:
    slide = by_id("d0-title")
    assert slide.layout == "title"
    assert slide.title == "Barkour CAD: retuned gains, same reward ladder"
    assert slide.date == "2026-09-17"


def test_two_images_become_two_iframe_embeds() -> None:
    slide = by_id("a1-crate")
    assert resolve_layout(slide) == "figures"
    assert slide.sentence is not None
    assert slide.sentence.startswith(
        "The Go2 finishes standing on the 0.60 m crate"
    )
    assert "\n" in slide.sentence  # the source line break is kept
    assert [(embed.src, embed.label, embed.kind) for embed in slide.embeds] == [
        ("assets/a1_go2_crate.html", "Unitree Go2", "iframe"),
        ("assets/a1_cad_crate.html", "Barkour CAD", "iframe"),
    ]


def test_a_figures_container_groups_its_images() -> None:
    slide = by_id("g3-paired")
    assert [embed.label for embed in slide.embeds] == ["18 N m", "22 N m"]
    assert slide.sentence == "Body load on the wall falls from 134 to 86 N s."
    assert slide.classes == ["wide"]


def test_an_animation_is_an_image_embed() -> None:
    slide = by_id("f4-twitch")
    assert slide.embeds[0].kind == "image"
    assert slide.embeds[0].label == "Twitch and flip"
    assert resolve_layout(slide) == "figures"


def test_a_gfm_table_becomes_a_table() -> None:
    slide = by_id("c1-model-table")
    assert resolve_layout(slide) == "table"
    assert slide.table is not None
    assert slide.table.columns == ["Property", "Unitree Go2", "Barkour CAD"]
    assert slide.table.rows[0] == ["Total mass", "15.21 kg", "11.31 kg"]
    assert slide.table.rows[2][2] == "0.65 copied, now 0.024 (hardware)"


def test_bullets_math_and_inline_math() -> None:
    slide = by_id("e0-status")
    assert slide.sentence is not None
    assert (
        r"$5\times10^{-7}$" in slide.sentence
    )  # inline math reaches the renderer raw
    assert slide.math == [
        r"W_{\text{net}}=\sum_{\text{substeps}}\ \sum_{j=1}^{12}\tau_j\,\Delta "
        r"q_j"
    ]
    assert slide.bullets == [
        "Source: one DIAL-MPC rollout, 250 controls of 20 ms, four 5 ms "
        "substeps each.",
        "Replay: MJX on the GPU reproduces every saved state bit for bit.",
    ]
    assert resolve_layout(slide) == "statement"


def test_notes_come_from_a_comment_and_from_a_container() -> None:
    assert (
        by_id("e0-status").notes
        == "the 42 J difference is the 5 ms integrator, not a loss"
    )
    wall = (
        "Say that the cap changes how the wall is crossed, not whether it "
        "is crossed."
    )
    assert by_id("g3-paired").notes == wall


def test_an_ordered_list_also_becomes_bullets() -> None:
    slides = parse("1. Raise the cap to 22 N m.\n2. Keep the wall at 0.65 m.\n")
    assert slides[0].bullets == [
        "Raise the cap to 22 N m.",
        "Keep the wall at 0.65 m.",
    ]


def test_a_definition_list_becomes_bullets() -> None:
    slides = parse("Replay\n: MJX on the GPU is bit-exact.\n")
    assert slides[0].bullets == ["Replay: MJX on the GPU is bit-exact."]


def test_a_mermaid_fence_becomes_a_deck_mermaid_element() -> None:
    slides = parse("```mermaid\ngraph TD; A-->B;\n```\n")
    assert slides[0].html == "<deck-mermaid>graph TD; A--&gt;B;</deck-mermaid>"


def test_another_fence_becomes_a_code_block() -> None:
    slides = parse("```python\nprint(1 < 2)\n```\n")
    assert (
        slides[0].html
        == '<pre><code class="language-python">print(1 &lt; 2)</code></pre>'
    )


def test_a_raw_html_block_is_carried_through() -> None:
    slides = parse('<div class="mkd-custom">anything</div>\n')
    assert slides[0].html == '<div class="mkd-custom">anything</div>'


def test_a_separator_inside_a_fence_does_not_cut_the_slide() -> None:
    slides = parse(
        "The deck file looks like this.\n\n```markdown\n---\nid: "
        "a1-crate\n---\n```\n"
    )
    assert len(slides) == 1
    assert slides[0].sentence == "The deck file looks like this."


def test_empty_pieces_are_not_slides_and_do_not_shift_the_numbering() -> None:
    slides = parse("\n---\n\n# Barkour vault\n\n---\n\n")
    assert len(slides) == 1
    assert slides[0].title == "Barkour vault"


def test_options_may_carry_the_whole_slide() -> None:
    slides = parse(
        "<!--\nid: f0-title\nlayout: title\ntitle: Refining the motion\ndate: "
        "2026-09-17\n-->\n"
    )
    assert slides[0] == Slide(
        id="f0-title",
        layout="title",
        title="Refining the motion",
        date="2026-09-17",
    )


def test_a_plain_comment_is_not_read_as_options() -> None:
    slides = parse(
        "<!-- the playback page is regenerated by build_compare_plots.py "
        "-->\n\nFive seeds cross.\n"
    )
    assert slides[0].sentence == "Five seeds cross."
    assert slides[0].html is None


def test_an_unknown_option_names_the_slide_and_suggests_the_key() -> None:
    with pytest.raises(DeckError) as caught:
        parse("<!--\nid: a1-crate\nlayot: figures\n-->\n\nFive seeds cross.\n")
    message = str(caught.value)
    assert message.startswith(
        f'{Path("slides/deck.md")}: slide 1 "a1-crate": This slide has the '
        f'unknown option "layot".'
    )
    assert 'Did you mean "layout"?' in message


def test_an_unknown_layout_names_the_layouts() -> None:
    with pytest.raises(DeckError, match="has the unknown layout"):
        parse("<!--\nlayout: figure\n-->\n\nFive seeds cross.\n")


def test_a_body_field_cannot_be_set_in_the_options() -> None:
    with pytest.raises(DeckError, match="written in the Markdown body"):
        parse("<!--\nembeds: [assets/g3_18.html]\n-->\n")


def test_an_option_that_repeats_the_body_is_an_error() -> None:
    with pytest.raises(DeckError, match="keep one of the two"):
        parse(
            "<!--\nsentence: Five seeds cross the wall.\n-->\n\nSix seeds "
            "cross the wall.\n"
        )


def test_an_option_that_agrees_with_the_body_is_accepted() -> None:
    slides = parse(
        "<!--\nsentence: Five seeds cross the wall.\n-->\n\nFive seeds cross "
        "the wall.\n"
    )
    assert slides[0].sentence == "Five seeds cross the wall."


def test_three_embeds_are_rejected_with_the_slide_named() -> None:
    text = (
        "<!-- id: g3-paired -->\n\n"
        "![18 N m](assets/g3_18.html)\n![22 N m](assets/g3_22.html)\n![26 N "
        "m](assets/g3_26.html)\n"
    )
    with pytest.raises(DeckError) as caught:
        parse(text)
    assert 'slide 1 "g3-paired": This slide has 3 embeds' in str(caught.value)


def test_an_escaping_embed_source_is_rejected() -> None:
    with pytest.raises(DeckError, match="leaves the deck folder"):
        parse("![Go2](../../other-project/assets/a1.html)\n")


def test_two_headings_on_one_slide_are_an_error() -> None:
    with pytest.raises(DeckError, match="two headings"):
        parse("# Barkour vault\n\n# Refining the motion\n")


def test_a_construct_with_no_home_on_a_slide_is_an_error() -> None:
    with pytest.raises(DeckError, match="a blockquote"):
        parse("> The cap changes how the wall is crossed.\n")


def test_unreadable_options_name_the_slide() -> None:
    with pytest.raises(DeckError) as caught:
        parse("# One\n\n---\n<!--\nid: [unclosed\n-->\n\nFive seeds cross.\n")
    assert str(caught.value).startswith(
        f"{Path('slides/deck.md')}: slide 2: The options comment is not valid."
    )


def test_duplicate_slide_ids_are_rejected() -> None:
    with pytest.raises(DeckError, match="repeats the id of slide 1"):
        parse(
            "<!-- id: a1-crate -->\n\nOne.\n\n---\n<!-- id: a1-crate "
            "-->\n\nTwo.\n"
        )


def test_a_deck_with_windows_line_endings_splits_and_reads_like_any_other() -> (
    None
):
    text = DECK.replace("\n", "\r\n")
    deck = parse_markdown(text, source=SOURCE)
    assert len(deck.slides) == 7
    assert deck.title.startswith("Barkour vault")
    assert all("\r" not in (slide.sentence or "") for slide in deck.slides)
    assert [slide.id for slide in deck.slides][1:3] == [
        "a1-crate",
        "c1-model-table",
    ]


def test_a_separator_directly_under_a_paragraph_still_cuts_the_slide() -> None:
    slides = parse("First sentence.\n---\nSecond sentence.\n")
    assert [slide.sentence for slide in slides] == [
        "First sentence.",
        "Second sentence.",
    ]


def test_a_separator_inside_a_comment_or_a_display_formula_does_not_cut_the_slide() -> (  # noqa: E501
    None
):
    text = (
        "Five seeds cross.\n\n<!--\nold notes\n---\nmore\n-->\n\n$$\na = "
        "b\n---\nc = d\n$$\n"
    )
    slides = parse(text)
    assert len(slides) == 1
    assert slides[0].sentence == "Five seeds cross."
    assert slides[0].math == ["a = b\n---\nc = d"]


def test_a_rule_nested_in_a_container_is_not_a_separator() -> None:
    slides = parse("::: notes\nSay this.\n\n---\n\nThen this.\n:::\n")
    assert len(slides) == 1
    assert slides[0].notes is not None
    assert "Then this." in slides[0].notes


def test_a_file_that_opens_with_a_separator_gets_a_specific_error() -> None:
    with pytest.raises(DeckError, match='opens with "---"') as caught:
        parse(
            "---\n\n# Barkour vault\n\nFive seeds cross.\n\n---\n\nSecond "
            "slide.\n"
        )
    assert "slide separator" in str(caught.value)
    with pytest.raises(DeckError, match="does not hold deck settings"):
        parse("---\n# Barkour vault\n---\n\nFive seeds cross.\n")


def test_a_frontmatter_block_that_is_empty_is_allowed() -> None:
    assert len(parse("---\n---\n\nFive seeds cross.\n")) == 1


def test_a_todo_comment_is_an_ordinary_comment() -> None:
    slides = parse("<!-- TODO: fix this slide -->\n\nFive seeds cross.\n")
    assert slides[0].sentence == "Five seeds cross."
    assert slides[0].id is None
    assert (
        parse("<!-- see the paper: section 3 -->\n\nFive seeds cross.\n")[
            0
        ].sentence
        == "Five seeds cross."
    )


def test_a_slide_that_holds_only_a_plain_comment_is_not_a_slide() -> None:
    slides = parse(
        "Five seeds cross.\n\n---\n<!-- TODO: write this one -->\n\n---\n\nSix "
        "seeds cross.\n"
    )
    assert [slide.sentence for slide in slides] == [
        "Five seeds cross.",
        "Six seeds cross.",
    ]


def test_a_comment_that_nearly_names_an_option_is_checked_like_options() -> (
    None
):
    with pytest.raises(DeckError, match='unknown option "note"'):
        parse("<!-- note: say this slowly -->\n\nFive seeds cross.\n")


def test_options_mixed_with_an_unknown_key_are_an_error() -> None:
    with pytest.raises(DeckError, match='unknown option "TODO"'):
        parse("<!--\nid: a1\nTODO: fix\n-->\n\nFive seeds cross.\n")


def test_a_heading_with_a_body_keeps_both() -> None:
    slide = parse("# Big Title\n\nSome sentence.\n")[0]
    assert slide.title == "Big Title"
    assert slide.sentence == "Some sentence."
    assert slide.layout == "auto"


def test_two_tables_on_one_slide_are_an_error() -> None:
    table = "| a | b |\n| - | - |\n| 1 | 2 |\n"
    with pytest.raises(DeckError, match="two tables"):
        parse(f"{table}\n{table}")


def test_figures_and_a_table_on_one_slide_are_an_error() -> None:
    with pytest.raises(DeckError, match="both figures and a table"):
        parse("![a](a.html)\n\n| a | b |\n| - | - |\n| 1 | 2 |\n")


def test_a_nested_list_is_an_error_not_a_flattened_bullet() -> None:
    with pytest.raises(DeckError, match="nested list") as caught:
        parse("<!-- id: deep -->\n\n- a\n  - b\n  - c\n")
    assert 'slide 1 "deep"' in str(caught.value)


def test_a_bullet_that_holds_a_code_block_is_an_error() -> None:
    with pytest.raises(DeckError, match="a code block inside a bullet"):
        parse("- a\n\n  ```\n  code\n  ```\n")
    with pytest.raises(DeckError, match="raw HTML inside a bullet"):
        parse("- a\n\n  <div>x</div>\n")


def test_a_paragraph_around_an_image_keeps_its_formatting_and_math() -> None:
    slide = parse(
        r"Speed is **fast** at $v^2$, cost \$5.  ![18 N m](a.html)" + "\n"
    )[0]
    assert slide.sentence == r"Speed is **fast** at $v^2$, cost \$5."
    assert [embed.src for embed in slide.embeds] == ["a.html"]


def test_text_before_and_after_images_stays_one_sentence_in_order() -> None:
    slide = parse("Before *it*.\n![a](a.html)\nAfter it.\n![b](b.html)\n")[0]
    assert slide.sentence == "Before *it*.\nAfter it."
    assert [embed.src for embed in slide.embeds] == ["a.html", "b.html"]


def test_an_image_label_keeps_its_math() -> None:
    assert parse("![run $k=2$](a.html)\n")[0].embeds[0].label == "run $k=2$"


def test_a_code_block_keeps_the_indentation_of_its_first_line() -> None:
    slide = parse("```python\n    indented()\nx = 1\n```\n")[0]
    assert (
        slide.html == '<pre><code class="language-python">    indented()\nx = '
        "1</code></pre>"
    )


def test_an_embed_source_with_a_query_is_kept_whole() -> None:
    embed = parse("![run](figs/g3_18.html?seed=2)\n")[0].embeds[0]
    assert embed.src == "figs/g3_18.html?seed=2"
    assert embed.kind == "iframe"


def test_a_dollar_amount_is_not_math_to_the_parser() -> None:
    slide = parse("It costs $5 and $10 to run.\n\n$$\nx\n$$\n")[0]
    assert slide.sentence == "It costs $5 and $10 to run."
    assert slide.math == ["x"]


@pytest.mark.parametrize(
    "note",
    [
        "Remember: pause",
        "fix # later",
        "yes",
        "- a",
        "no, really: 1.10 stays as written",
    ],
)
def test_a_comment_that_starts_with_notes_is_raw_text_wherever_it_sits(
    note: str,
) -> None:
    """A notes comment first on a slide used to be read as YAML, so a colon
    or `yes` broke it.
    """
    first = parse(f"<!-- notes: {note} -->\n\nFive seeds cross.\n")[0]
    after = parse(f"Five seeds cross.\n\n<!-- notes: {note} -->\n")[0]
    assert first.notes == after.notes == note
    assert first.sentence == "Five seeds cross."


def test_a_multiline_notes_comment_first_on_a_slide_is_all_notes() -> None:
    slide = parse(
        "<!--\nnotes: Open with the wall.\nThen: the cap.\n-->\n\nFive seeds "
        "cross.\n"
    )[0]
    assert slide.notes == "Open with the wall.\nThen: the cap."


def test_notes_can_still_be_an_option_when_other_options_come_first() -> None:
    slide = parse(
        '<!--\nid: a1\nnotes: "Say: pause"\n-->\n\nFive seeds cross.\n'
    )[0]
    assert (slide.id, slide.notes) == ("a1", "Say: pause")


def test_an_image_takes_its_link_or_emphasis_with_it() -> None:
    """`[![Run](a.png)](url)` and `*![Run](a.png)*` used to leave an empty
    link or a stray `**`.
    """
    for text in (
        "[![Run](assets/a.png)](https://example.org)",
        "*![Run](assets/a.png)*",
        "**![Run](assets/a.png)**",
    ):
        slide = parse(text)[0]
        assert slide.sentence is None, text
        assert [embed.src for embed in slide.embeds] == ["assets/a.png"]


def test_the_words_around_an_image_and_a_link_that_holds_more_than_it_stay() -> (  # noqa: E501
    None
):
    slide = parse(
        "*Run 3* ![Run](assets/a.png) and [see ![Run](assets/b.png) "
        "here](https://example.org)\n"
    )[0]
    assert slide.sentence == "*Run 3*  and [see  here](https://example.org)"
    assert [embed.src for embed in slide.embeds] == [
        "assets/a.png",
        "assets/b.png",
    ]


def test_a_deck_with_no_title_gets_no_generated_title_slide() -> None:
    deck = parse_markdown("# My Talk\n\n---\n\nHello.\n", source=SOURCE)
    assert deck.title_slide is False
    assert (
        deck.title == "My Talk"
    )  # the browser tab is named after the first heading
    assert [slide.title for slide in deck.slides] == ["My Talk", None]
    assert parse_markdown("Hello.\n", source=SOURCE).title == "Slide Deck"


def test_a_deck_with_a_title_keeps_its_generated_title_slide() -> None:
    deck = parse_markdown(
        "---\ntitle: Talk\n---\n\n# My Talk\n\n---\n\nHello.\n", source=SOURCE
    )
    assert deck.title == "Talk"
    assert deck.title_slide is True


def test_a_deck_with_nothing_in_it_is_an_error() -> None:
    for text in ("", "---\n---\n", "<!-- just a comment -->\n"):
        with pytest.raises(DeckError, match="no slides"):
            parse_markdown(text, source=SOURCE)
    assert (
        parse_markdown("---\ntitle: Talk\n---\n", source=SOURCE).slides == []
    )  # the title slide is the deck
