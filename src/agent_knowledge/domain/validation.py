"""Narrow already-parsed, untrusted values without parsing files or YAML."""

import re
from collections.abc import Mapping, Set

from agent_knowledge.domain.models import DocumentReference


class ValidationError(ValueError):
    """Report a stable error category and the offending input field."""

    def __init__(self, code: str, path: str, message: str) -> None:
        """Retain structured diagnostics for adapters to render."""
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def field_path(parent: str, field: str) -> str:
    """Join diagnostic fields without a leading dot at the request root."""
    return f"{parent}.{field}" if parent else field


def read_mapping(
    value: object,
    path: str,
    required: Set[str],
    optional: Set[str] = frozenset(),
) -> dict[str, object]:
    """Require a string-keyed mapping with a closed set of fields."""
    if not isinstance(value, Mapping):
        raise ValidationError("invalid-type", path, "Expected an object.")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValidationError("invalid-type", path, "Object keys must be strings.")
        result[key] = item
    for key in sorted(required - result.keys()):
        raise ValidationError("missing-field", field_path(path, key), "Required field is missing.")
    for key in sorted(result.keys() - required - optional):
        raise ValidationError("unknown-field", field_path(path, key), "Field is not supported.")
    return result


def read_string(value: object, path: str) -> str:
    """Require a nonblank string without silently rewriting authored values."""
    if not isinstance(value, str):
        raise ValidationError("invalid-type", path, "Expected a string.")
    if not value.strip() or "\x00" in value:
        raise ValidationError("invalid-value", path, "Expected nonblank text without NUL.")
    return value


def read_strings(value: object, path: str, unique: bool = True) -> tuple[str, ...]:
    """Validate a nonempty list, preserving positions until semantic checks finish."""
    if not isinstance(value, list):
        raise ValidationError("invalid-type", path, "Expected a list of strings.")
    if not value:
        raise ValidationError("invalid-value", path, "An explicit list must not be empty.")
    values = tuple(read_string(item, f"{path}[{index}]") for index, item in enumerate(value))
    distinct = tuple(dict.fromkeys(values))
    if unique and len(distinct) != len(values):
        raise ValidationError("duplicate-value", path, "Authored values must be unique.")
    return values


def read_identifier(value: object, path: str) -> str:
    """Require an exact lowercase slug or colon-qualified identifier."""
    identifier = read_string(value, path)
    if not re.fullmatch(r"[a-z0-9]+(?:[._:-][a-z0-9]+)*", identifier):
        raise ValidationError(
            "invalid-identifier", path, "Expected a lowercase registered-style identifier."
        )
    return identifier


def read_relative_path(value: object, path: str) -> str:
    """Validate a source-relative POSIX path lexically, without filesystem access."""
    relative = read_string(value, path)
    if (
        relative.startswith("/")
        or any(character in relative for character in ("\\", "\x00", "#", "?"))
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", relative)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValidationError(
            "invalid-path", path, "Expected a contained relative POSIX file path."
        )
    return relative


def read_document_reference(value: object, path: str) -> DocumentReference:
    """Validate the shape of a source-qualified document pointer."""
    fields = read_mapping(value, path, {"source", "path"})
    return DocumentReference(
        source=read_identifier(fields["source"], field_path(path, "source")),
        path=read_relative_path(fields["path"], field_path(path, "path")),
    )
