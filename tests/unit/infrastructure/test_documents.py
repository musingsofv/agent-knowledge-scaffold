"""Shared authored-document and request codec boundaries, entirely in memory."""

import hashlib

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.documents import dump_document, load_mapping, parse_document


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"{}", {}),
        (b"name: example\nvalues: [one, two]\n", {"name": "example", "values": ["one", "two"]}),
        (
            b'{"limit": 10, "enabled": true, "other": null}',
            {"limit": 10, "enabled": True, "other": None},
        ),
        (b"created_at: 2026-09-09T12:30:00Z", {"created_at": "2026-09-09T12:30:00Z"}),
        (b'{"ratio": 1e3, "small": 1e-3}', {"ratio": 1000.0, "small": 0.001}),
        (b'{"title": "\\ud83d\\ude80"}', {"title": "🚀"}),
        (b"decimal: 012\noctal: 0o12\nhex: 0x12", {"decimal": 12, "octal": 10, "hex": 18}),
        (
            b"enabled: TRUE\ndisabled: False\nname: on\nother: yes",
            {"enabled": True, "disabled": False, "name": "on", "other": "yes"},
        ),
        ("title: Café 🚀\n".encode(), {"title": "Café 🚀"}),
        (
            b"description: >\n  Useful knowledge\n  for engineers.\n",
            {"description": "Useful knowledge for engineers.\n"},
        ),
        (
            b"base: &value [one, two]\ncopy: *value",
            {"base": ["one", "two"], "copy": ["one", "two"]},
        ),
    ],
)
def test_mapping_decodes_supported_values(content: bytes, expected: dict[str, object]) -> None:
    assert load_mapping(content) == expected


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "invalid-yaml-root"),
        (b"# comment only", "invalid-yaml-root"),
        (b"null", "invalid-yaml-root"),
        (b"[]", "invalid-yaml-root"),
        (b"just text", "invalid-yaml-root"),
        (b"a: [", "invalid-yaml"),
        (b"a: first\na: second", "duplicate-yaml-key"),
        (b"outer: {a: first, a: second}", "duplicate-yaml-key"),
        (b"1: value", "invalid-yaml-key"),
        (b"true: value", "invalid-yaml-key"),
        (b"? [a, b]\n: value", "invalid-yaml-key"),
        (b"base: &base {a: value}\nmerged: {<<: *base}", "unsupported-yaml-merge"),
        (b"a: !!python/object/apply:os.system ['echo unsafe']", "unsupported-yaml-tag"),
        (b"a: !custom unsafe", "unsupported-yaml-tag"),
        (b"a: !!set {item: null}", "unsupported-yaml-tag"),
        (b"a: !!timestamp 2026-09-09", "unsupported-yaml-tag"),
        (b"a: &cycle [*cycle]", "yaml-alias-cycle"),
        (b"a: &cycle {b: *cycle}", "yaml-alias-cycle"),
        (b"a: 1\n---\nb: 2", "multiple-yaml-documents"),
        (b"a: \xff", "invalid-utf8"),
        (b"a: \x00", "invalid-yaml"),
        (b"a: .inf", "invalid-yaml-scalar"),
        (b"a: .nan", "invalid-yaml-scalar"),
        (b"a: .Inf", "invalid-yaml-scalar"),
        (b"a: -.INF", "invalid-yaml-scalar"),
        (b"a: .NaN", "invalid-yaml-scalar"),
        (b"a: 1e10000", "invalid-yaml-scalar"),
        (b"a: !!float not-a-number", "invalid-yaml-scalar"),
        (b"a: !!int 2.5", "invalid-yaml-scalar"),
        (b"a: !!bool yes", "invalid-yaml-scalar"),
        (b'a: "\\ud800"', "invalid-yaml-scalar"),
    ],
)
def test_invalid_mapping_reports_sanitized_structured_error(content: bytes, code: str) -> None:
    with pytest.raises(ValidationError) as error:
        load_mapping(content, path="catalog.yaml")
    assert error.value.code == code
    assert error.value.path == "catalog.yaml"
    assert "unsafe" not in error.value.message
    assert "echo" not in error.value.message


def test_mapping_size_is_measured_in_bytes() -> None:
    content = "a: é".encode()
    assert load_mapping(content, max_bytes=len(content)) == {"a": "é"}
    with pytest.raises(ValidationError, match="byte limit") as error:
        load_mapping(content, max_bytes=len(content) - 1)
    assert error.value.code == "input-too-large"


def test_deep_yaml_is_rejected_before_composition_recurses() -> None:
    with pytest.raises(ValidationError) as error:
        load_mapping(b"a: " + b"[" * 2000 + b"x" + b"]" * 2000)
    assert error.value.code == "yaml-complexity-limit"


def test_too_many_yaml_nodes_are_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        load_mapping(("a: [" + ",".join("x" for _ in range(20001)) + "]").encode())
    assert error.value.code == "yaml-complexity-limit"


def test_alias_expansion_is_bounded() -> None:
    content = "a: &a [x, x, x, x, x, x, x, x, x, x]\n"
    for letter, previous in zip("bcdefg", "abcdef", strict=True):
        content += f"{letter}: &{letter} [" + ", ".join([f"*{previous}"] * 10) + "]\n"
    with pytest.raises(ValidationError) as error:
        load_mapping(content.encode())
    assert error.value.code == "yaml-complexity-limit"


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_document_preserves_exact_body_physical_ranges_and_fingerprint(
    newline: str, final_newline: bool
) -> None:
    body = newline + "# Café 🚀" + newline + "Procedure\u2028on the same physical line."
    if final_newline:
        body += newline
    content = (newline.join(["---", "title: Example", "---", ""]) + body).encode()
    parsed = parse_document(content)
    assert parsed.metadata == {"title": "Example"}
    assert parsed.body == body
    assert parsed.frontmatter_range == (1, 3)
    assert parsed.body_range == (4, 6)
    assert parsed.line_count == 6
    assert parsed.byte_count == len(content)
    assert parsed.fingerprint == "sha256:" + hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_document_can_have_no_body(ending: bytes) -> None:
    parsed = parse_document(b"---\n{}\n---" + ending)
    assert parsed.body == ""
    assert parsed.body_range is None
    assert parsed.line_count == 3


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"title: Example\n",
        b"\n---\ntitle: Example\n---\n",
        b" ---\ntitle: Example\n---\n",
        b"--- \ntitle: Example\n---\n",
        b"\xef\xbb\xbf---\ntitle: Example\n---\n",
        b"---\ntitle: Example\n",
        b"---\ntitle: Example\n...\nbody",
    ],
)
def test_document_requires_exact_first_line_and_closing_delimiters(content: bytes) -> None:
    with pytest.raises(ValidationError) as error:
        parse_document(content, path="runbooks/example.md")
    assert error.value.code == "invalid-frontmatter"
    assert error.value.path == "runbooks/example.md"


def test_document_uses_same_strict_yaml_loader() -> None:
    with pytest.raises(ValidationError) as error:
        parse_document(b"---\ntitle: one\ntitle: two\n---\n# body")
    assert error.value.code == "duplicate-yaml-key"


def test_document_body_is_not_reinterpreted_as_yaml_or_frontmatter() -> None:
    body = "---\nnot: [valid yaml\n...\n\n```yaml\n---\n```"
    assert parse_document(("---\n{}\n---\n" + body).encode()).body == body


def test_document_size_bounds_include_the_body() -> None:
    content = b"---\n{}\n---\nbody"
    assert parse_document(content, max_bytes=len(content)).body == "body"
    with pytest.raises(ValidationError) as error:
        parse_document(content, max_bytes=len(content) - 1)
    assert error.value.code == "input-too-large"


@pytest.mark.parametrize("body", ["", "# Claim", "\r\n# Café 🚀\r\n\r\n", "\n---\n", "\u2028"])
def test_serializer_round_trips_metadata_and_exact_body(body: str) -> None:
    metadata = {
        "schema_version": "knowledge-signal.v1",
        "created_at": "2026-09-09T12:30:00Z",
        "description": "Several lines\nending with a newline.\n",
        "origin": {"name": "on", "scopes": ["org:example"]},
        "enabled": True,
        "count": 3,
        "ratio": 0.5,
        "nothing": None,
    }
    parsed = parse_document(dump_document(metadata, body))
    assert parsed.metadata == metadata
    assert parsed.body == body


def test_serializer_rejects_unsupported_objects_without_their_representation() -> None:
    class Secret:
        def __repr__(self) -> str:
            return "secret-value"

    with pytest.raises(ValidationError) as error:
        dump_document({"a": Secret()}, "Claim")
    assert "secret-value" not in str(error.value)


def test_serializer_rejects_cycles() -> None:
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(ValidationError) as error:
        dump_document({"a": cycle}, "Claim")
    assert error.value.code == "yaml-alias-cycle"


@pytest.mark.parametrize("text", ["1e3", "1.0e3", "0o12", "True", "null", "012", "yes", "on"])
def test_serializer_quotes_using_the_same_scalar_rules_as_the_loader(text: str) -> None:
    metadata = {"title": text, text: "value"}
    assert parse_document(dump_document(metadata, "Claim")).metadata == metadata


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_metadata_field_ranges_use_original_physical_lines(
    newline: str, final_newline: bool
) -> None:
    lines = [
        "---",
        "# introductory comment",
        "title: Example # title comment",
        "description: >-",
        "  Useful indexing guidance",
        "  across two lines.",
        "languages: [any]",
        "technologies:",
        "  - postgresql",
        "  # comment inside this list",
        "  - mysql",
        "# comment before the next field",
        "terms: [",
        "  relational,",
        "  indexing",
        "]",
        "empty: # null value",
        "---",
        "# Body",
    ]
    content = newline.join(lines) + (newline if final_newline else "")
    parsed = parse_document(content.encode())
    assert parsed.field_ranges == {
        "title": (3, 3),
        "description": (4, 6),
        "languages": (7, 7),
        "technologies": (8, 11),
        "terms": (13, 16),
        "empty": (17, 17),
    }
    assert parsed.body_range == (19, 19)


def test_metadata_field_ranges_point_at_alias_use_not_anchor_definition() -> None:
    parsed = parse_document(
        b"---\n"
        b"terms: &names\n  - indexing\n  - relational\n"
        b"aliases: *names\n"
        b"title: &key description\n"
        b"*key : A description using an aliased field name\n"
        b"---"
    )
    assert parsed.field_ranges == {
        "terms": (2, 4),
        "aliases": (5, 5),
        "title": (6, 6),
        "description": (7, 7),
    }
    assert parsed.metadata["aliases"] == parsed.metadata["terms"]


def test_metadata_field_ranges_cover_nested_values_without_following_alias_marks() -> None:
    parsed = parse_document(
        b"---\n"
        b"base: &base {name: example}\n"
        b"origin:\n  workspace: example\n  evidence:\n    - *base\n"
        b"# comment belongs to neither field\n"
        b"empty: {}\n"
        b"---\n"
    )
    assert parsed.field_ranges == {"base": (2, 2), "origin": (3, 6), "empty": (8, 8)}


def test_metadata_field_ranges_for_empty_frontmatter_mapping() -> None:
    assert parse_document(b"---\n{}\n---").field_ranges == {}


def test_multiple_inline_fields_truthfully_share_a_line() -> None:
    parsed = parse_document(b'---\n{"title": "Example", "terms": ["index"]}\n---')
    assert parsed.field_ranges == {"title": (2, 2), "terms": (2, 2)}


def test_unicode_yaml_line_separators_do_not_invent_physical_lines() -> None:
    parsed = parse_document('---\ndescription: "one\u2028two"\ntitle: Example\n---'.encode())
    assert parsed.field_ranges == {"description": (2, 2), "title": (3, 3)}


@pytest.mark.parametrize("style", ["|", "|-", "|+", ">", ">-", ">+"])
def test_block_scalar_range_includes_authored_blank_lines_but_not_next_field(style: str) -> None:
    content = f"---\ndescription: {style}\n  Claim\n\n# external comment\ntitle: Example\n---"
    parsed = parse_document(content.encode())
    assert parsed.field_ranges == {"description": (2, 4), "title": (6, 6)}


def test_null_field_range_does_not_consume_later_comment_or_field() -> None:
    parsed = parse_document(b"---\nempty:\n# comment\nnext: value\n---")
    assert parsed.field_ranges == {"empty": (2, 2), "next": (4, 4)}
