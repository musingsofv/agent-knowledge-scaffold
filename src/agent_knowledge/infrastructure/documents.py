"""Strict UTF-8 YAML and Markdown envelopes without filesystem access.

Frontmatter starts on physical line one and uses exact ``---`` delimiters.
LF, CRLF and CR are physical newlines; Unicode separators are ordinary text.
The body is returned unchanged. Ranges are one-based, inclusive and include
frontmatter delimiters; a terminal newline does not create a phantom line.

YAML permits only mappings with string keys, sequences and scalar primitives.
Only true/false resolve as booleans; yes/no/on/off and timestamps stay strings.
Numbers use decimal, 0o octal or 0x hexadecimal integers and finite decimal
floats, including exponent notation. Quoted values always remain strings.
No YAML constructors run: PyYAML provides syntax nodes, converted explicitly
below. Acyclic aliases are accepted with bounded expansion; merges are not.
"""

import hashlib
import math
import re
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    ScalarEvent,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from agent_knowledge.domain.validation import ValidationError

MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 20_000
DEFAULT_MAPPING_BYTES = 1_048_576
DEFAULT_DOCUMENT_BYTES = 8_388_608
_TAG = "tag:yaml.org,2002:"
_INTEGER = re.compile(r"[-+]?(?:[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)\Z")
_FLOAT = re.compile(
    r"[-+]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?"
    r"|[0-9]+[eE][-+]?[0-9]+|\.(?:inf|Inf|INF|nan|NaN|NAN))\Z"
)


class _SyntaxLoader(yaml.SafeLoader):
    """Compose nodes with local resolvers, never construct Python YAML objects."""


_SyntaxLoader.yaml_implicit_resolvers = {}
for _name, _pattern, _first_characters in (
    ("bool", re.compile(r"(?:true|false)\Z", re.I), tuple("tTfF")),
    ("null", re.compile(r"(?:~|null|Null|NULL|)\Z"), ("~", "n", "N", "")),
    ("int", _INTEGER, tuple("-+0123456789")),
    ("float", _FLOAT, tuple("-+.0123456789")),
    ("merge", re.compile(r"<<\Z"), ("<",)),
):
    for _character in _first_characters:
        _SyntaxLoader.yaml_implicit_resolvers.setdefault(_character, []).append(
            (_TAG + _name, _pattern)
        )


class _DocumentDumper(yaml.SafeDumper):
    """Quote string scalars according to the exact rules used when reading them."""


_DocumentDumper.yaml_implicit_resolvers = _SyntaxLoader.yaml_implicit_resolvers


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Decoded envelope plus navigation facts for the exact supplied bytes."""

    metadata: dict[str, object]
    body: str
    byte_count: int
    line_count: int
    frontmatter_range: tuple[int, int]
    body_range: tuple[int, int] | None
    fingerprint: str
    field_ranges: dict[str, tuple[int, int]]


def _decode(data: bytes, path: str, max_bytes: int) -> str:
    if len(data) > max_bytes:
        raise ValidationError("input-too-large", path, "Input exceeds the configured byte limit.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValidationError("invalid-utf8", path, "Input must contain valid UTF-8.") from None


def _complexity_error(path: str) -> ValidationError:
    return ValidationError(
        "yaml-complexity-limit", path, "YAML exceeds the supported depth or node limit."
    )


def _check_events(text: str, path: str) -> list[tuple[int, int]]:
    """Bound composition and retain authored top-level key/value character spans.

    Alias events locate the actual reference; composed nodes instead reuse the
    anchor's location. Block collection end marks can point at the next field,
    so only child syntax and explicit flow delimiters extend the authored span.
    """
    depth = 0
    count = 0
    documents = 0
    flow_collections: list[bool] = []
    spans: list[tuple[int, int]] = []
    for event in yaml.parse(text, Loader=_SyntaxLoader):
        if isinstance(event, DocumentStartEvent):
            documents += 1
            if documents > 1:
                raise ValidationError(
                    "multiple-yaml-documents", path, "Expected exactly one YAML document."
                )
        if isinstance(event, CollectionStartEvent | AliasEvent | ScalarEvent):
            if depth == 1:
                spans.append((event.start_mark.index, event.end_mark.index))
            elif depth > 1:
                spans[-1] = (spans[-1][0], event.end_mark.index)
            count += 1
        if isinstance(event, CollectionStartEvent):
            flow_collections.append(bool(event.flow_style))
            depth += 1
        elif isinstance(event, CollectionEndEvent):
            if flow_collections.pop() and depth > 1:
                spans[-1] = (spans[-1][0], event.end_mark.index)
            depth -= 1
        if depth > MAX_YAML_DEPTH or count > MAX_YAML_NODES:
            raise _complexity_error(path)
    return spans


def _scalar(node: ScalarNode, path: str) -> object:
    value = node.value
    if node.tag == _TAG + "str":
        if re.search(r"[\ud800-\udfff]", value):
            try:
                # JSON escapes may represent one Unicode scalar as a surrogate pair.
                return value.encode("utf-16", "surrogatepass").decode("utf-16")
            except UnicodeDecodeError:
                raise ValidationError(
                    "invalid-yaml-scalar", path, "Text contains an invalid Unicode scalar."
                ) from None
        return value
    if node.tag == _TAG + "null" and value.lower() in {"", "~", "null"}:
        return None
    if node.tag == _TAG + "bool" and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if node.tag == _TAG + "int" and _INTEGER.fullmatch(value):
        base = 0 if value.lstrip("+-").startswith(("0o", "0x")) else 10
        try:
            return int(value, base)
        except ValueError:
            raise _complexity_error(path) from None
    if node.tag == _TAG + "float" and _FLOAT.fullmatch(value):
        result = float(value.lower().replace(".inf", "inf").replace(".nan", "nan"))
        if math.isfinite(result):
            return result
    if node.tag in {_TAG + name for name in ("str", "null", "bool", "int", "float")}:
        raise ValidationError("invalid-yaml-scalar", path, "YAML scalar has an unsupported value.")
    raise ValidationError("unsupported-yaml-tag", path, "YAML tag is not supported.")


def _from_node(
    node: Node, path: str, active: set[int], remaining: list[int], depth: int = 1
) -> object:
    remaining[0] -= 1
    if remaining[0] < 0 or depth > MAX_YAML_DEPTH + 1:
        raise _complexity_error(path)
    identity = id(node)
    if identity in active:
        raise ValidationError("yaml-alias-cycle", path, "Cyclic YAML aliases are not supported.")
    active.add(identity)
    try:
        if isinstance(node, ScalarNode):
            return _scalar(node, path)
        if isinstance(node, SequenceNode) and node.tag == _TAG + "seq":
            return [_from_node(item, path, active, remaining, depth + 1) for item in node.value]
        if isinstance(node, MappingNode) and node.tag == _TAG + "map":
            result: dict[str, object] = {}
            for key_node, value_node in node.value:
                if key_node.tag == _TAG + "merge":
                    raise ValidationError(
                        "unsupported-yaml-merge", path, "YAML merges are not supported."
                    )
                key = _from_node(key_node, path, active, remaining, depth + 1)
                if not isinstance(key, str):
                    raise ValidationError(
                        "invalid-yaml-key", path, "YAML mapping keys must be strings."
                    )
                if key in result:
                    raise ValidationError(
                        "duplicate-yaml-key", path, "YAML mapping keys must be unique."
                    )
                result[key] = _from_node(value_node, path, active, remaining, depth + 1)
            return result
        raise ValidationError("unsupported-yaml-tag", path, "YAML tag is not supported.")
    finally:
        active.remove(identity)


def load_mapping(
    data: bytes, *, path: str = "<input>", max_bytes: int = DEFAULT_MAPPING_BYTES
) -> dict[str, object]:
    """Parse one bounded safe YAML/JSON mapping; malformed input never means empty."""
    text = _decode(data, path, max_bytes)
    return _load_mapping(text, path)[0]


def _load_mapping(text: str, path: str) -> tuple[dict[str, object], list[tuple[int, int]]]:
    """Share the same strict event/composition pass with source-location consumers."""
    try:
        spans = _check_events(text, path)
        node = yaml.compose(text, Loader=_SyntaxLoader)
        if node is None:
            raise ValidationError("invalid-yaml-root", path, "Expected one YAML mapping.")
        value = _from_node(node, path, set(), [MAX_YAML_NODES])
    except yaml.YAMLError:
        raise ValidationError("invalid-yaml", path, "Input is not valid supported YAML.") from None
    except RecursionError:
        raise _complexity_error(path) from None
    if not isinstance(value, dict):
        raise ValidationError("invalid-yaml-root", path, "Expected one YAML mapping.")
    return value, spans


def _field_ranges(
    metadata: Mapping[str, object], spans: list[tuple[int, int]], text: str
) -> dict[str, tuple[int, int]]:
    """Bind validated mapping keys to authored physical lines after the opening delimiter."""
    starts = [0, *(match.end() for match in re.finditer(r"\r\n|[\r\n]", text))]
    return {
        key: (
            bisect_right(starts, key_span[0]) + 1,
            bisect_right(starts, max(key_span[0], value_span[1] - 1)) + 1,
        )
        for key, key_span, value_span in zip(metadata, spans[::2], spans[1::2], strict=True)
    }


def parse_document(
    data: bytes, *, path: str = "<document>", max_bytes: int = DEFAULT_DOCUMENT_BYTES
) -> ParsedDocument:
    """Parse a Markdown frontmatter envelope without interpreting its body."""
    text = _decode(data, path, max_bytes)
    lines = re.findall(r"[^\r\n]*(?:\r\n|[\r\n]|$)", text)[:-1]
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValidationError(
            "invalid-frontmatter", path, "Expected --- on the first physical line."
        )
    closing = next(
        (index for index in range(1, len(lines)) if lines[index].rstrip("\r\n") == "---"), None
    )
    if closing is None:
        raise ValidationError(
            "invalid-frontmatter", path, "Frontmatter requires a closing --- line."
        )
    metadata_text = "".join(lines[1:closing])
    metadata, spans = _load_mapping(metadata_text, path)
    body = "".join(lines[closing + 1 :])
    return ParsedDocument(
        metadata=metadata,
        body=body,
        byte_count=len(data),
        line_count=len(lines),
        frontmatter_range=(1, closing + 1),
        body_range=(closing + 2, len(lines)) if body else None,
        fingerprint="sha256:" + hashlib.sha256(data).hexdigest(),
        field_ranges=_field_ranges(metadata, spans, metadata_text),
    )


def _serializable(value: object, active: set[int], remaining: list[int], depth: int = 1) -> object:
    """Copy only bounded primitive containers; never stringify unknown objects."""
    path = "<document>"
    remaining[0] -= 1
    if remaining[0] < 0 or depth > MAX_YAML_DEPTH + 1:
        raise _complexity_error(path)
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    identity = id(value)
    if identity in active:
        raise ValidationError("yaml-alias-cycle", path, "Cyclic YAML aliases are not supported.")
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            result: dict[str, object] = {}
            for key, item in value.items():
                if type(key) is not str:
                    raise ValidationError(
                        "invalid-yaml-key", path, "YAML mapping keys must be strings."
                    )
                remaining[0] -= 1
                result[key] = _serializable(item, active, remaining, depth + 1)
            return result
        if isinstance(value, list):
            return [_serializable(item, active, remaining, depth + 1) for item in value]
        raise ValidationError(
            "invalid-yaml-value", path, "Expected supported YAML primitive values."
        )
    finally:
        active.remove(identity)


def dump_document(metadata: Mapping[str, object], body: str) -> bytes:
    """Write canonical LF frontmatter and retain the body's exact Unicode text."""
    value = _serializable(metadata, set(), [MAX_YAML_NODES])
    try:
        frontmatter = yaml.dump(value, Dumper=_DocumentDumper, allow_unicode=True, sort_keys=False)
        data = ("---\n" + frontmatter + "---\n" + body).encode("utf-8")
    except (yaml.YAMLError, UnicodeEncodeError, ValueError):
        raise ValidationError(
            "invalid-yaml-value",
            "<document>",
            "Document contains unsupported text or scalar values.",
        ) from None
    parse_document(data)
    return data
