"""Physical locations and conservative Markdown interpretation for file navigation."""

from dataclasses import FrozenInstanceError

import pytest

from agent_knowledge.domain.navigation import (
    Heading,
    MarkdownLink,
    TextLine,
    scan_markdown,
    section_for_line,
)


def test_nested_sections_include_subsections_until_an_equal_or_higher_heading() -> None:
    navigation = scan_markdown(
        "Introduction\n# Operations\nPrerequisites\n## Adding an index\nSteps\n"
        "### Verification\nCheck\n## Recovery\nUndo\n# References\nLinks",
        start_line=12,
    )

    assert navigation.headings == (
        Heading(1, "Operations", "operations", 13, 20),
        Heading(2, "Adding an index", "adding-an-index", 15, 18),
        Heading(3, "Verification", "verification", 17, 18),
        Heading(2, "Recovery", "recovery", 19, 20),
        Heading(1, "References", "references", 21, 22),
    )
    assert section_for_line(navigation, 12) is None
    assert section_for_line(navigation, 14) == navigation.headings[0]
    assert section_for_line(navigation, 15) == navigation.headings[1]
    assert section_for_line(navigation, 18) == navigation.headings[2]
    assert section_for_line(navigation, 22) == navigation.headings[-1]
    assert section_for_line(navigation, 23) is None


def test_cross_section_match_uses_its_enclosing_ancestor() -> None:
    navigation = scan_markdown("# Operations\n## Safety\nindex\n## cost\nLater text")

    assert section_for_line(navigation, 3, end_line=4) == navigation.headings[0]
    assert section_for_line(navigation, 3, end_line=3) == navigation.headings[1]


def test_cross_section_match_without_common_ancestor_has_no_section() -> None:
    navigation = scan_markdown("## Safety\nindex\n## cost\nLater text")

    assert section_for_line(navigation, 2, end_line=3) is None
    assert section_for_line(navigation, 1, end_line=10) is None


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("trailing_newline", [True, False])
def test_physical_lines_preserve_newline_variants_and_original_offsets(
    newline: str, trailing_newline: bool
) -> None:
    body = newline.join(["Intro", "", "## Résumé", "内容"])
    if trailing_newline:
        body += newline

    navigation = scan_markdown(body, start_line=7)

    assert navigation.lines == (
        TextLine(7, "Intro"),
        TextLine(8, ""),
        TextLine(9, "Résumé"),
        TextLine(10, "内容"),
    )
    assert navigation.headings == (Heading(2, "Résumé", "résumé", 9, 10),)


def test_only_cr_and_lf_are_physical_line_delimiters() -> None:
    navigation = scan_markdown("word\u2028word\vword\fword")

    assert navigation.lines == (TextLine(1, "word\u2028word\vword\fword"),)


@pytest.mark.parametrize("body,count", [("", 0), ("\n", 1), ("\n\n", 2), ("a\n\n", 2)])
def test_empty_and_blank_body_line_counts(body: str, count: int) -> None:
    assert len(scan_markdown(body).lines) == count


@pytest.mark.parametrize("start_line", [0, -1, True])
def test_body_start_line_must_be_a_positive_integer(start_line: int) -> None:
    with pytest.raises(ValueError, match="start_line"):
        scan_markdown("body", start_line=start_line)


def test_atx_heading_subset_does_not_invent_other_heading_types() -> None:
    navigation = scan_markdown(
        "# One ###\n   ## Two\n####### Seven\n#not-heading\n    # indented\n"
        "\t# tabbed\n> # quoted\nTitle\n=====\n- # list heading\n#\n"
    )

    assert [(heading.level, heading.title) for heading in navigation.headings] == [
        (1, "One"),
        (2, "Two"),
        (1, ""),
    ]


def test_duplicate_anchors_remain_unique_even_when_explicit_suffixes_collide() -> None:
    navigation = scan_markdown("# Index\n# Index\n# Index-1\n# Index\n# INDEX")

    assert [heading.anchor for heading in navigation.headings] == [
        "index",
        "index-1",
        "index-1-1",
        "index-2",
        "index-3",
    ]


def test_heading_title_uses_visible_inline_text_and_unicode_slug() -> None:
    navigation = scan_markdown("## **Crème** [Index](./index.md) & `SQL` — 数据 ###")

    assert navigation.headings == (
        Heading(2, "Crème Index & SQL — 数据", "crème-index--sql--数据", 1, 1),
    )
    assert navigation.links == (MarkdownLink("Index", "./index.md", 1, 1),)


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_fenced_code_is_literal_search_text_without_fake_headings_or_links(fence: str) -> None:
    navigation = scan_markdown(
        f"# Real\n{fence}markdown\n## fake\n[not a link](evil.md)\n"
        f"**literal**\n{fence}\n## Real child\n"
    )

    assert [heading.title for heading in navigation.headings] == ["Real", "Real child"]
    assert navigation.links == ()
    assert navigation.lines[1:6] == (
        TextLine(2, ""),
        TextLine(3, "## fake"),
        TextLine(4, "[not a link](evil.md)"),
        TextLine(5, "**literal**"),
        TextLine(6, ""),
    )


def test_fence_closing_requires_matching_character_and_sufficient_length() -> None:
    navigation = scan_markdown(
        "````\n```\n# Still code\n~~~~\n## Still code\n````` text\n### Still code\n`````\n# Visible"
    )

    assert [heading.title for heading in navigation.headings] == ["Visible"]


def test_unclosed_fence_keeps_remainder_literal() -> None:
    navigation = scan_markdown("~~~\n# fake\n[link](hidden.md)")

    assert navigation.headings == ()
    assert navigation.links == ()
    assert navigation.lines[-1] == TextLine(3, "[link](hidden.md)")


def test_indented_code_does_not_yield_links_or_formatted_text() -> None:
    navigation = scan_markdown("    [code](x.md) **literal**\n\t[more](y.md)")

    assert navigation.links == ()
    assert navigation.lines[0].text == "    [code](x.md) **literal**"


@pytest.mark.parametrize("indentation", [" \t", "  \t", "   \t"])
def test_tab_stops_after_leading_spaces_still_protect_indented_code(indentation: str) -> None:
    body = indentation + "[code](fake.md) **literal**"

    assert scan_markdown(body).links == ()
    assert scan_markdown(body).lines == (TextLine(1, body),)


def test_empty_heading_with_optional_closing_hashes_has_no_visible_title() -> None:
    assert scan_markdown("# ###\nbody").headings == (Heading(1, "", "", 1, 2),)


def test_inline_syntax_keeps_visible_text_and_discards_link_targets() -> None:
    navigation = scan_markdown(
        "Use **concurrent index** and _verification_, then `DROP INDEX`. "
        'Read [the **runbook**](../runbooks/index.md#adding-index "Procedure").'
    )

    assert navigation.lines == (
        TextLine(1, "Use concurrent index and verification, then DROP INDEX. Read the runbook."),
    )
    assert navigation.links == (
        MarkdownLink("the runbook", "../runbooks/index.md#adding-index", 1, 1),
    )


def test_emphasis_preserves_unpaired_markers_intraword_underscores_and_escapes() -> None:
    navigation = scan_markdown(r"snake_case_column \*literal\* and **bold** *unclosed")

    assert navigation.lines[0].text == "snake_case_column *literal* and bold *unclosed"


def test_code_spans_ignore_fake_links_and_preserve_literal_markers() -> None:
    navigation = scan_markdown(
        "`[fake](no.md) **literal**` then ``some `backticks` [fake](no.md)`` and [real](yes.md)"
    )

    assert navigation.links == (MarkdownLink("real", "yes.md", 1, 1),)
    assert navigation.lines[0].text == (
        "[fake](no.md) **literal** then some `backticks` [fake](no.md) and real"
    )


def test_multiline_code_span_retains_physical_lines_and_ignores_its_links() -> None:
    navigation = scan_markdown("Before `code\n[not link](no.md)` after", start_line=20)

    assert navigation.lines == (
        TextLine(20, "Before code"),
        TextLine(21, "[not link](no.md) after"),
    )
    assert navigation.links == ()


def test_multiline_link_label_and_title_keep_full_original_location() -> None:
    navigation = scan_markdown(
        'See [adding\na secondary **index**](../index.md#add\n "Long title") now.',
        start_line=30,
    )

    assert navigation.links == (
        MarkdownLink("adding a secondary index", "../index.md#add", 30, 32),
    )
    assert navigation.lines == (
        TextLine(30, "See adding"),
        TextLine(31, "a secondary index"),
        TextLine(32, " now."),
    )


@pytest.mark.parametrize(
    "markdown,target",
    [
        ("[label](runbook(index).md)", "runbook(index).md"),
        (r"[label](runbook\(index\).md)", "runbook(index).md"),
        ("[label](<runbook index.md>)", "runbook index.md"),
        ("[label](#local-anchor)", "#local-anchor"),
        ("[label]()", ""),
        ("[label](../x.md 'A title')", "../x.md"),
        ("[label](../x.md (A title))", "../x.md"),
    ],
)
def test_inline_destinations_preserve_path_anchor_and_supported_title_syntax(
    markdown: str, target: str
) -> None:
    assert scan_markdown(markdown).links == (MarkdownLink("label", target, 1, 1),)


def test_reference_links_resolve_forward_case_and_whitespace_normalized_definitions() -> None:
    navigation = scan_markdown(
        "Read [the rule][Index Cost], [Index Cost][] and [INDEX COST].\n\n"
        '[index   cost]: ../rules/cost.md#tradeoffs "Title"\n'
    )

    assert navigation.links == (
        MarkdownLink("the rule", "../rules/cost.md#tradeoffs", 1, 1),
        MarkdownLink("Index Cost", "../rules/cost.md#tradeoffs", 1, 1),
        MarkdownLink("INDEX COST", "../rules/cost.md#tradeoffs", 1, 1),
    )
    assert navigation.lines[0].text == "Read the rule, Index Cost and INDEX COST."
    assert navigation.lines[-1].text == ""


def test_unresolved_explicit_references_are_visible_without_inventing_a_target() -> None:
    navigation = scan_markdown("[Evidence][missing] [Unknown][] and ordinary [text].")

    assert navigation.links == (
        MarkdownLink("Evidence", None, 1, 1),
        MarkdownLink("Unknown", None, 1, 1),
    )
    assert navigation.lines[0].text == "Evidence Unknown and ordinary [text]."


def test_first_reference_definition_wins_and_code_definitions_do_not_count() -> None:
    navigation = scan_markdown(
        "[one][x] [two][y]\n\n[x]: first.md\n[x]: second.md\n```\n[y]: fake.md\n```"
    )

    assert navigation.links == (
        MarkdownLink("one", "first.md", 1, 1),
        MarkdownLink("two", None, 1, 1),
    )


def test_unsupported_reference_destination_remains_unresolved() -> None:
    navigation = scan_markdown("[See][x]\n\n[x]: destination with unquoted spaces")

    assert navigation.links == (MarkdownLink("See", None, 1, 1),)
    assert navigation.lines[-1].text == "[x]: destination with unquoted spaces"


def test_escaped_reference_definition_label_resolves_consistently() -> None:
    navigation = scan_markdown("[link][foo\\]]\n\n[foo\\]]: real.md")

    assert navigation.links == (MarkdownLink("link", "real.md", 1, 1),)


def test_standalone_html_comments_do_not_fabricate_links_or_section_boundaries() -> None:
    navigation = scan_markdown("<!--\n# Hidden\n[Hidden](hidden.md)\n-->\n# Real")

    assert navigation.links == ()
    assert navigation.headings == (Heading(1, "Real", "real", 5, 5),)
    assert all(not line.text for line in navigation.lines[:4])


def test_inline_html_comment_is_not_searchable_or_navigable() -> None:
    navigation = scan_markdown("Before <!-- [hidden](hidden.md) --> after [real](real.md)")

    assert navigation.links == (MarkdownLink("real", "real.md", 1, 1),)
    assert navigation.lines[0].text == "Before  after real"


def test_recognizable_html_block_stays_literal_until_a_blank_line() -> None:
    navigation = scan_markdown(
        "<div>\n# Hidden\n[Hidden](hidden.md)\n</div>\n## Still raw\n\n# Real"
    )

    assert navigation.links == ()
    assert navigation.headings == (Heading(1, "Real", "real", 7, 7),)
    assert navigation.lines[2].text == "[Hidden](hidden.md)"


@pytest.mark.parametrize("tag", ["script", "pre", "style", "textarea"])
def test_explicit_html_blocks_remain_literal_across_blank_lines(tag: str) -> None:
    navigation = scan_markdown(f"<{tag}>\n\n# Hidden\n[Hidden](no.md)\n</{tag}>\n# Real")

    assert navigation.links == ()
    assert navigation.headings == (Heading(1, "Real", "real", 6, 6),)


def test_autolinks_and_image_alt_text_keep_navigation_references() -> None:
    navigation = scan_markdown(
        "<https://example.com/runbook#section> ![System **diagram**](./diagram.svg)"
    )

    assert navigation.links == (
        MarkdownLink(
            "https://example.com/runbook#section", "https://example.com/runbook#section", 1, 1
        ),
        MarkdownLink("System diagram", "./diagram.svg", 1, 1),
    )
    assert navigation.lines[0].text == "https://example.com/runbook#section System diagram"


def test_escaped_and_code_delimited_link_syntax_is_not_navigation() -> None:
    navigation = scan_markdown(r"\[escaped](no.md) `[fake](no.md)` [real](yes.md)")

    assert navigation.links == (MarkdownLink("real", "yes.md", 1, 1),)


def test_unclosed_inline_link_is_literal_without_a_fabricated_destination() -> None:
    navigation = scan_markdown("[broken](somewhere and [unterminated")

    assert navigation.links == ()
    assert navigation.lines[0].text == "[broken](somewhere and [unterminated"


def test_links_and_code_cannot_span_blank_lines_or_block_boundaries() -> None:
    navigation = scan_markdown("[broken\n\nlabel](no.md)\n`start\n# Heading\nend`")

    assert navigation.links == ()
    assert navigation.headings[0].title == "Heading"


def test_navigation_records_are_immutable() -> None:
    navigation = scan_markdown("# Title\n[Link](somewhere.md)")

    with pytest.raises(FrozenInstanceError):
        navigation.headings[0].title = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        navigation.links[0].target = "changed"  # type: ignore[misc]


def test_deep_unclosed_brackets_preserve_a_nested_valid_link() -> None:
    navigation = scan_markdown("[" * 3000 + "[valid](yes.md)")

    assert navigation.links == (MarkdownLink("valid", "yes.md", 1, 1),)
    assert navigation.lines[0].text == "[" * 3000 + "valid"


def test_many_distinct_unclosed_code_delimiters_remain_literal() -> None:
    body = " ".join("`" * width for width in range(1, 180))

    assert scan_markdown(body).lines == (TextLine(1, body),)
