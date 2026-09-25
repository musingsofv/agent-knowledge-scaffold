"""Describe the public schemas without loading configuration or knowledge."""

from typing import TypedDict

from agent_knowledge.domain.models import CatalogDimension, KnowledgeKind
from agent_knowledge.domain.validation import ValidationError, read_mapping, read_string
from agent_knowledge.resources import guide_path, template_paths


class FieldSpec(TypedDict):
    """Describe one authoring or request field."""

    type: str
    required: bool
    description: str


class ResourceLocations(TypedDict):
    """Report only resources actually delivered by the current slice."""

    status: str
    guide: str | None
    templates: list[str]


class Description(TypedDict, total=False):
    """Return either the compact overview or selected schema fields."""

    commands: dict[str, str]
    planned_commands: list[str]
    schemas: list[str]
    kinds: list[str]
    semantics: list[str]
    resources: ResourceLocations
    limits: dict[str, int]
    invocation: dict[str, str]
    schema: str
    fields: dict[str, FieldSpec]


def _field(type_name: str, description: str, required: bool = False) -> FieldSpec:
    """Construct one schema description with explicit requiredness."""
    return FieldSpec(type=type_name, required=required, description=description)


def _schemas() -> dict[str, dict[str, FieldSpec]]:
    """Keep schema documentation in one discoverable owner."""
    technology = (
        "Registered technology IDs or family:<id>; [any] alone means unrestricted. "
        "Required on guidance documents. Queries explicitly include every alternative."
    )
    applicability = "Registered IDs or [any] alone; required on guidance documents."
    knowledge = {
        "schema_version": _field("string", "Exactly knowledge.v1.", True),
        "kind": _field("string", "One of the eight listed knowledge kinds.", True),
        "title": _field("string", "Nonblank document title.", True),
        "description": _field(
            "string", "When this document is useful; at most 600 characters.", True
        ),
        "scope": _field("string[]", "Nonempty unique registered applicability scopes.", True),
        "topics": _field(
            "string[]", "Registered business or engineering subjects addressed.", True
        ),
        "entities": _field("string[]", "Registered named entities discussed by this document."),
        "languages": _field("string[]", applicability),
        "technologies": _field("string[]", technology),
        "environments": _field("string[]", applicability),
        "aliases": _field("string[]", "Alternative discovery phrases, not filter identifiers."),
        "terms": _field("string[]", "Additional literal discovery phrases."),
    }
    text = _field(
        "object", "any/all nonempty phrase lists; OR within any, AND within all and across groups."
    )
    limit = _field("integer", "Page size, default 10, minimum 1, maximum 100.")
    continuation = _field(
        "string", "Opaque snapshot cursor; repeat the original request to continue."
    )
    query = {
        key: _field("string[]", "Explicit OR alternatives; supplied fields combine with AND.")
        for key in (
            "kind",
            "scope",
            "topics",
            "entities",
            "languages",
            "technologies",
            "environments",
            "sources",
        )
    }
    query.update(text=text, limit=limit, continuation=continuation)
    return {
        "knowledge.v1": knowledge,
        "knowledge-signal.v1": {
            "schema_version": _field("string", "Exactly knowledge-signal.v1.", True),
            "id": _field("string", "Stable signal identifier.", True),
            "created_at": _field(
                "string", "Timezone-qualified ISO timestamp, not a local time.", True
            ),
            "kind_hint": _field(
                "string", "Advisory knowledge kind; compounding decides ownership.", True
            ),
            "origin": _field(
                "object",
                "workspace_id, project_path (nullable), applicable_scopes, source_ids; "
                "provenance is not canonical applicability. Optional harness (codex, claude "
                "or copilot) requires session_id: copy the exact opaque provider session "
                "handle from the hook. Manual/non-harness signals may omit both. "
                "automation_id is independently optional and cannot replace session_id.",
                True,
            ),
            "entities": _field("string[]", "Optional registered entity hints."),
            "technologies": _field("string[]", "Optional registered applicability hints."),
            "evidence": _field(
                "object[]",
                "Nonempty {type, reference} pointers; claim belongs in the nonblank Markdown body.",
                True,
            ),
        },
        "knowledge-catalog.v1": {
            "schema_version": _field("string", "Exactly knowledge-catalog.v1.", True),
            **{
                dimension.value: _field(
                    "object",
                    "ID-to-record registry; may be empty. Records contain label/description "
                    "and optional aliases.",
                    True,
                )
                for dimension in CatalogDimension
            },
        },
        "knowledge-profiles.v1": {
            "schema_version": _field("string", "Exactly knowledge-profiles.v1.", True),
            "default_profile": _field(
                "string", "Optional exact existing profile name; no implicit first profile."
            ),
            "profiles": _field(
                "object",
                (
                    "Lowercase slugs mapped to {config, overrides?, environment?}. Config, "
                    "override and environment.file paths resolve from the registry. "
                    "Environment variables map lowercase labels to required "
                    "{from_env, expose_as, description}; values remain in the external "
                    "dotenv file and never enter configuration or receipts. Overrides: "
                    "applicable_scopes, sources, signal_storage, receipts, setup. Lists "
                    "replace; maps merge. Identity cannot change."
                ),
                True,
            ),
        },
        "profiles list": {},
        "knowledge-workspace.v1": {
            "schema_version": _field("string", "Exactly knowledge-workspace.v1.", True),
            "workspace_id": _field("string", "Stable explicit workspace identity.", True),
            "applicable_scopes": _field(
                "string[]", "Explicit registered scope IDs; no automatic ancestor expansion.", True
            ),
            "sources": _field(
                "object[]",
                "Unique id, root, catalog; optional publication "
                "{repository, base_branch, branch_prefix}. Paths resolve relative to config.",
                True,
            ),
            "signal_storage": _field(
                "object",
                "scaffold_root and code_root; inbox is scaffold_root/ai/signals, "
                "separate from canonical roots.",
            ),
            "receipts": _field(
                "object",
                "enabled (default true), directory (default ./ai/usage), "
                "retention_days (default 30). Relative to config; outside "
                "knowledge and inbox roots. Disabling diagnostics retains "
                "mandatory compound archives.",
            ),
            "setup": _field(
                "object",
                "Optional non-secret venv, harness and native automation preferences; "
                "credential values remain in provider state or an external profile env file; "
                "task IDs remain harness state.",
            ),
        },
        "search": query,
        "inspect": {
            "document": _field(
                "object", "Configured {source, path}; path is source-relative.", True
            ),
            "view": _field(
                "string", "navigation (default) or incoming authored Markdown references."
            ),
            "sources": _field(
                "string[]",
                "Incoming only: configured referencing sources to scan; "
                "default all. Catalog documents references are separate "
                "coverage.",
            ),
            "expected_fingerprint": _field(
                "string", "Optional sha256:<64 lowercase hex digits> from a preview."
            ),
            "limit": limit,
            "continuation": continuation,
        },
        "validate": {
            "sources": _field(
                "string[]",
                "Validate every Markdown document in the selected configured sources.",
            ),
            "documents": _field(
                "object[]",
                "Validate explicit {source, path} document references without linked-body reads.",
            ),
            "signal_files": _field(
                "string[]",
                "Validate authored Markdown signal paths relative to the workspace config.",
            ),
        },
        "compound": {
            "action": _field(
                "string",
                "One of status, start, finish or drain; coordinates activity and "
                "guarded signal removal.",
                True,
            ),
            "workspace_id": _field("string", "Required for start; must match --config."),
            "selected": _field(
                "object[]",
                "Signal id/path/sha256 snapshot selected by signal list; complete bytes are "
                "rechecked unchanged before drain.",
            ),
            "harness": _field("string", "Optional safe harness provenance."),
            "session_id": _field("string", "Optional opaque originating-session handle."),
            "automation_id": _field("string", "Optional opaque native automation handle."),
            "run_id": _field(
                "string",
                "Required for drain and finish; must identify this workspace's recorded run.",
            ),
            "outcome": _field(
                "string",
                "Required for finish; agent-reported outcome, not proof of "
                "drainage or publication.",
            ),
            "dispositions": _field(
                "object[]",
                "signal_id/decision/rationale plus owners [{source,path} or "
                "{repository,path,package?}] or owner_unavailable_reason. "
                "Required for drain. Write decisions with unresolved owners "
                "remain pending.",
            ),
            "publication": _field(
                "object",
                "Agent-reported status and repository/PR/commit evidence; "
                "optional checkout/before_revision/after_revision for tool- "
                "captured bounded Git patch, or unavailable_reason.",
            ),
            "publication_verified": _field(
                "boolean",
                "Explicit caller assertion for write decisions; never "
                "inferred from a commit, receipt, or finish outcome.",
            ),
        },
        "usage export": {
            "since": _field("string", "UTC ISO timestamp, inclusive start.", True),
            "until": _field("string", "UTC ISO timestamp, exclusive end; must follow since.", True),
            "destination": _field(
                "string",
                "Fresh local directory for this workspace's "
                "events/artifacts, checksums and coverage diagnostics; never "
                "upload or overwrite.",
                True,
            ),
        },
        "signal record": {
            "file": _field(
                "string",
                "Authored Markdown signal path, relative to the workspace configuration. "
                "Validate and capture a unique inbox file; retain the authored input.",
                True,
            ),
        },
        "signal list": {
            "include_shared": _field(
                "boolean",
                "Default false. Include the non-project inbox for this configured workspace; "
                "shared names storage, not a canonical applicability scope.",
            ),
            "session_id": _field(
                "string",
                "Optional exact opaque provider session handle; matching is literal "
                "and case-sensitive.",
            ),
            "limit": limit,
            "continuation": continuation,
        },
        "catalog": {
            "dimension": _field(
                "string", "One registered catalog dimension, e.g. entities or technologies.", True
            ),
            "ids": _field("string[]", "Exact registered IDs in that dimension; OR alternatives."),
            "sources": _field(
                "string[]", "Configured sources declaring the records; OR alternatives."
            ),
            "text": text,
            "limit": limit,
            "continuation": continuation,
        },
        "doctor": {
            "mode": _field(
                "string",
                "read (default) or write; write probes only existing validated signal storage.",
            ),
            "expected_workspace_id": _field(
                "string", "Assert selected workspace identity; not a catalog filter."
            ),
        },
        "context": {},
        "describe": {
            "schema": _field("string", "Select one of the schemas listed by describe."),
            "field": _field("string", "Select a top-level schema field; requires schema."),
        },
    }


def describe(value: object) -> Description:
    """Return a bounded contract overview or requested schema/field documentation."""
    request = read_mapping(value, "", set(), {"schema", "field"})
    schemas = _schemas()
    if "field" in request and "schema" not in request:
        raise ValidationError("missing-field", "schema", "A field selector requires schema.")
    if "schema" in request:
        schema = read_string(request["schema"], "schema")
        if schema not in schemas:
            raise ValidationError(
                "invalid-value", "schema", "Unknown schema; use describe to list schemas."
            )
        fields = schemas[schema]
        if "field" in request:
            field = read_string(request["field"], "field")
            if field not in fields:
                raise ValidationError(
                    "unknown-field", "field", "Unknown field for the selected schema."
                )
            fields = {field: fields[field]}
        return Description(schema=schema, fields=fields)
    guide = guide_path()
    templates = [str(path) for path in template_paths()]
    return Description(
        commands={
            "describe": "Discover schemas; optional schema/field. Configuration is not required.",
            "doctor": "Check setup; optional mode/expected_workspace_id.",
            "context": (
                "Read effective configuration, selection, origins and safe selected-profile "
                "environment metadata; no request fields."
            ),
            "profiles list": (
                "List registry names/default/paths without opening workspaces; optional --settings."
            ),
            "catalog": "Discover IDs with dimension/text/ids/sources/limit/continuation.",
            "search": "Return matching file previews, with bounded, pageable match locations.",
            "inspect": (
                "Return navigation or explicitly requested incoming references; no body prose."
            ),
            "validate": "Validate selected sources, documents or signal files before publication.",
            "signal record": "Validate Markdown and durable origin; capture without overwrite.",
            "signal list": "List originating workspace signals with metadata and body locations.",
            "compound": (
                "Archive selected inputs, record a run and safely drain unchanged handled signals."
            ),
            "usage export": (
                "Export a UTC interval of workspace usage and supporting artifacts locally."
            ),
        },
        invocation={
            "--config": "Direct workspace path; mutually exclusive with --profile/--settings.",
            "--profile": (
                "Exact knowledge profile name. Credential activation is fixed when a harness "
                "session starts; selecting another name does not mutate that environment."
            ),
            "--settings": (
                "Registry path; otherwise ~/.config/agent-knowledge/config.yaml. "
                "Unqualified operations use its default_profile."
            ),
            "--harness": "Optional caller-supplied codex/claude/copilot; before command.",
            "--session-id": "Exact hook session handle; omit when unknown.",
            "--compound-run-id": (
                "Recorded workspace run; supplies consistent harness/session "
                "defaults and correlates retrieval/validate evidence."
            ),
        },
        planned_commands=[],
        schemas=list(schemas),
        kinds=[kind.value for kind in KnowledgeKind],
        semantics=[
            "Same-field OR; different supplied filters use AND. Missing metadata is not any.",
            "Scopes, any and family:<id> must be explicitly requested; no filter expansion.",
            "Literal Unicode/case-normalized phrases and direct aliases; no regex or reranking.",
            "Catalog text and IDs combine with AND; ambiguous aliases retain distinct candidates.",
            "Invalid input is an error; zero matches is a successful result for that request only.",
            "Search returns 20 locations per file; match_continuation pages more via search.",
            "Inspect resolves outgoing file paths; other-file anchors remain unverified.",
            "Validate shares the strict codec/schema and reports broken local references.",
            "Signal origin records capture context; compounding decides canonical applicability.",
            "Signal listing returns previews without claim bodies and does not alter the inbox.",
            "CLI catalog/search/inspect write terminal receipts by default; "
            "body_read remains unknown.",
            "Compound archive and pre-removal intent are mandatory even with "
            "diagnostic receipts disabled.",
        ],
        resources=ResourceLocations(
            status="ready" if guide.is_file() and templates else "unavailable",
            guide=str(guide),
            templates=templates,
        ),
        limits={
            "page_default": 10,
            "page_max": 100,
            "structured_bytes": 1048576,
            "document_bytes": 8388608,
            "yaml_depth": 64,
            "yaml_nodes": 20000,
            "match_locations_per_file": 20,
        },
    )
