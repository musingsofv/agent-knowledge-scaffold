"""Validate signal operation inputs and compare explicitly supplied capture context."""

from collections.abc import Mapping
from dataclasses import dataclass

from .catalog import Catalog
from .configuration import read_config_path
from .models import SignalOrigin
from .schema import parse_query
from .validation import ValidationError, read_identifier, read_mapping, read_string


@dataclass(frozen=True, slots=True)
class SignalRecordQuery:
    """Keep a literal input path for the application to resolve against its config."""

    file: str


@dataclass(frozen=True, slots=True)
class SignalListQuery:
    """Select workspace signals and optionally shared signals with bounded paging."""

    include_shared: bool = False
    limit: int = 10
    continuation: str | None = None
    session_id: str | None = None


def parse_signal_record_query(value: object) -> SignalRecordQuery:
    """Require one literal local input path without accessing or expanding it."""
    fields = read_mapping(value, "", {"file"})
    return SignalRecordQuery(file=read_config_path(fields["file"], "file"))


def parse_signal_list_query(value: object, catalog: Catalog) -> SignalListQuery:
    """Validate explicit shared selection and reuse the standard page contract."""
    fields = read_mapping(
        value, "", set(), {"include_shared", "limit", "continuation", "session_id"}
    )
    include_shared = fields.get("include_shared", False)
    if not isinstance(include_shared, bool):
        raise ValidationError("invalid-type", "include_shared", "Expected a boolean.")
    page = parse_query(
        {key: fields[key] for key in ("limit", "continuation") if key in fields}, catalog
    )
    session_id = _session_id(fields["session_id"]) if "session_id" in fields else None
    return SignalListQuery(include_shared, page.limit, page.continuation, session_id)


def _session_id(value: object) -> str:
    """Validate one exact opaque provider handle used by signal listing."""
    session_id = read_string(value, "session_id")
    if len(session_id) > 256 or session_id != session_id.strip():
        raise ValidationError(
            "invalid-value", "session_id", "Expected a short opaque session handle."
        )
    if any(character.isspace() or ord(character) < 32 for character in session_id):
        raise ValidationError(
            "invalid-value", "session_id", "Expected a short opaque session handle."
        )
    if any(character in ("/", "\\", "$", "`") for character in session_id):
        raise ValidationError(
            "invalid-value", "session_id", "Expected a short opaque session handle."
        )
    return session_id


def signal_workspace_id(value: object) -> str:
    """Identify a signal's workspace without validating it against a foreign catalog."""
    if not isinstance(value, Mapping):
        raise ValidationError("invalid-type", "", "Expected an object.")
    if "schema_version" not in value:
        raise ValidationError("missing-field", "schema_version", "Required field is missing.")
    if read_string(value["schema_version"], "schema_version") != "knowledge-signal.v1":
        raise ValidationError(
            "unsupported-schema", "schema_version", "Expected knowledge-signal.v1."
        )
    if "origin" not in value:
        raise ValidationError("missing-field", "origin", "Required field is missing.")
    origin = value["origin"]
    if not isinstance(origin, Mapping):
        raise ValidationError("invalid-type", "origin", "Expected an object.")
    if "workspace_id" not in origin:
        raise ValidationError("missing-field", "origin.workspace_id", "Required field is missing.")
    return read_identifier(origin["workspace_id"], "origin.workspace_id")


def validate_signal_origin(
    origin: SignalOrigin,
    *,
    workspace_id: str,
    applicable_scopes: tuple[str, ...],
    source_ids: tuple[str, ...],
    project_path: str | None,
) -> None:
    """Require captured provenance to match loaded context without inferring membership."""
    if origin.workspace_id != workspace_id:
        raise ValidationError(
            "origin-mismatch",
            "origin.workspace_id",
            "The signal workspace ID must equal the configured workspace ID.",
        )
    if origin.project_path != project_path:
        raise ValidationError(
            "origin-mismatch",
            "origin.project_path",
            "The signal project path must equal the selected project path; "
            "shared capture requires an explicit null project path.",
        )
    if set(origin.applicable_scopes) != set(applicable_scopes):
        raise ValidationError(
            "origin-mismatch",
            "origin.applicable_scopes",
            "The signal scope set must equal the configured workspace scope set.",
        )
    if set(origin.source_ids) != set(source_ids):
        raise ValidationError(
            "origin-mismatch",
            "origin.source_ids",
            "The signal source ID set must equal the configured workspace source ID set.",
        )
