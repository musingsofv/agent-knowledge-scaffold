"""Pure decisions used by the scheduled and on-demand compounding workflow.

The compounding skill owns agent judgement, Git and GitHub commands.  This
module owns only the small deterministic decisions that must remain stable
across harnesses: knowledge-PR eligibility/selection and safe disposition
gates for signal drainage.  It does not read files, inspect Git, or contact a
provider.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .configuration import CompoundTrigger, parse_compound_trigger
from .validation import (
    ValidationError,
    read_identifier,
    read_mapping,
    read_relative_path,
    read_string,
)


class CompoundDecision(StrEnum):
    """Name the explicit outcomes a signal can receive in one run."""

    UPDATE = "update"
    CREATE = "create"
    DELETE_RETIRE = "delete-retire"
    KEEP = "keep"
    SKIP = "skip"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    """Bind a selected signal to its complete bytes before agent work starts."""

    id: str
    path: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class OwnerReference:
    """Identify a declared knowledge or authoritative package/repository owner."""

    path: str
    source: str | None = None
    repository: str | None = None
    package: str | None = None


@dataclass(frozen=True, slots=True)
class PublicationEvidence:
    """Carry agent assertions and optional exact local Git revision boundaries."""

    status: str
    repository: str
    publication_verified: bool
    pull_request: int | None = None
    commit: str | None = None
    checkout: str | None = None
    before_revision: str | None = None
    after_revision: str | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SignalDisposition:
    """Record one explicit compound decision and its durable rationale."""

    signal_id: str
    decision: CompoundDecision
    rationale: str
    owners: tuple[OwnerReference, ...] = ()
    owner_unavailable_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PullRequestCandidate:
    """Carry the GitHub fields needed for knowledge-PR selection."""

    number: int
    author_login: str
    state: str
    head_ref: str
    title: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class PullRequestSelection:
    """Explain the selected PR and the deterministic selection rule used."""

    selected: PullRequestCandidate | None
    reason: str


@dataclass(frozen=True, slots=True)
class CompoundRequest:
    """Validate the narrow coordination helper request at its public boundary."""

    action: str
    workspace_id: str | None = None
    selected: tuple[SignalSnapshot, ...] = ()
    harness: str | None = None
    session_id: str | None = None
    automation_id: str | None = None
    run_id: str | None = None
    outcome: str | None = None
    dispositions: tuple[SignalDisposition, ...] = ()
    publications: tuple[PublicationEvidence, ...] = ()
    automatic: bool = False
    worker_id: str | None = None
    parent_session_id: str | None = None
    recovery_of: str | None = None
    completion: str | None = None
    expected_trigger: CompoundTrigger | None = None


_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


_WRITE_DECISIONS = frozenset(
    {CompoundDecision.UPDATE, CompoundDecision.CREATE, CompoundDecision.DELETE_RETIRE}
)
_NON_WRITE_DECISIONS = frozenset({CompoundDecision.KEEP, CompoundDecision.SKIP})


def eligible_pull_request(
    candidate: PullRequestCandidate, *, operator_login: str, branch_prefix: str
) -> bool:
    """Return whether a candidate is an open PR owned by this operator's prefix."""
    return (
        candidate.state.casefold() == "open"
        and candidate.author_login.casefold() == operator_login.casefold()
        and candidate.head_ref.startswith(branch_prefix)
    )


def select_pull_request(
    candidates: tuple[PullRequestCandidate, ...],
    *,
    operator_login: str,
    branch_prefix: str,
    explicit_number: int | None = None,
) -> PullRequestSelection:
    """Select one eligible current-user PR without inspecting unrelated work.

    An explicit number is honored only after the same eligibility check used by
    automatic selection.  Automatic selection orders ISO timestamps
    lexicographically (the GitHub API returns timezone-qualified instants) and
    uses the PR number as a stable tie-breaker.
    """
    eligible = tuple(
        candidate
        for candidate in candidates
        if eligible_pull_request(
            candidate, operator_login=operator_login, branch_prefix=branch_prefix
        )
    )
    if explicit_number is not None:
        selected = next((item for item in eligible if item.number == explicit_number), None)
        return PullRequestSelection(
            selected,
            "explicit eligible PR" if selected is not None else "explicit PR is not eligible",
        )
    selected = max(eligible, key=lambda item: (item.updated_at, item.number)) if eligible else None
    return PullRequestSelection(
        selected,
        "most recently updated eligible PR" if selected is not None else "no eligible PR",
    )


def can_drain(
    disposition: SignalDisposition,
    *,
    publications: tuple[PublicationEvidence, ...] = (),
    source_repositories: Mapping[str, str] | None = None,
) -> bool:
    """Require agent-verified publication for each authored owner, or a no-write decision.

    Source routes come from effective workspace configuration, never a publication
    entry's claim. Local patch capture and PR presence alone prove no publication.
    """
    if not disposition.rationale.strip():
        return False
    if disposition.decision in _NON_WRITE_DECISIONS:
        return True
    if (
        disposition.decision not in _WRITE_DECISIONS
        or not disposition.owners
        or disposition.owner_unavailable_reason is not None
        or len({item.repository for item in publications}) != len(publications)
    ):
        return False
    verified_repositories = {
        item.repository
        for item in publications
        if item.publication_verified
        and item.status == "published"
        and item.commit is not None
        and _COMMIT.fullmatch(item.commit)
        and item.unavailable_reason is None
    }
    sources = source_repositories or {}
    return all(
        (sources.get(owner.source) if owner.source is not None else owner.repository)
        in verified_repositories
        for owner in disposition.owners
    )


def drainable_snapshots(
    snapshots: tuple[SignalSnapshot, ...],
    dispositions: tuple[SignalDisposition, ...],
    *,
    current_fingerprints: dict[str, str],
    publications: tuple[PublicationEvidence, ...] = (),
    source_repositories: Mapping[str, str] | None = None,
) -> tuple[SignalSnapshot, ...]:
    """Return only selected, handled signals whose complete bytes are unchanged.

    Missing dispositions, deferred decisions, missing current fingerprints and
    changed bytes all retain the signal.  The filesystem adapter performs the
    final containment, identity and unlink checks after this pure selection.
    """
    snapshot_by_id = {snapshot.id: snapshot for snapshot in snapshots}
    if len(snapshot_by_id) != len(snapshots):
        raise ValueError("Signal snapshot IDs must be unique.")
    dispositions_by_id = {item.signal_id: item for item in dispositions}
    if len(dispositions_by_id) != len(dispositions):
        raise ValueError("Signal dispositions must be unique.")
    result: list[SignalSnapshot] = []
    for signal_id, disposition in dispositions_by_id.items():
        snapshot = snapshot_by_id.get(signal_id)
        if snapshot is None or not can_drain(
            disposition, publications=publications, source_repositories=source_repositories
        ):
            continue
        if current_fingerprints.get(signal_id) == snapshot.fingerprint:
            result.append(snapshot)
    return tuple(sorted(result, key=lambda item: (item.path, item.id)))


def parse_compound_request(value: object) -> CompoundRequest:
    """Parse status/start/finish/drain without executing any side effect."""
    fields = read_mapping(
        value,
        "",
        {"action"},
        {
            "automatic",
            "worker_id",
            "parent_session_id",
            "recovery_of",
            "completion",
            "expected_trigger",
            "workspace_id",
            "selected",
            "harness",
            "session_id",
            "automation_id",
            "run_id",
            "outcome",
            "dispositions",
            "publications",
        },
    )
    action = read_string(fields["action"], "action")
    if action not in {
        "status",
        "due",
        "configure-trigger",
        "record-worker",
        "start",
        "finish",
        "drain",
    }:
        raise ValidationError(
            "invalid-value",
            "action",
            "Expected status, due, configure-trigger, record-worker, start, finish or drain.",
        )
    for field, required_action in (
        ("automatic", "start"),
        ("completion", "finish"),
        ("expected_trigger", "configure-trigger"),
        ("recovery_of", "start"),
    ):
        if field in fields and action != required_action:
            raise ValidationError(
                "invalid-field", field, f"Field applies only to {required_action}."
            )
    workspace_id = (
        read_string(fields["workspace_id"], "workspace_id") if "workspace_id" in fields else None
    )
    selected = _request_snapshots(fields.get("selected", []), "selected")
    harness = _optional_request_text(fields.get("harness"), "harness")
    session_id = _optional_handle(fields.get("session_id"), "session_id")
    automation_id = _optional_handle(fields.get("automation_id"), "automation_id")
    run_id = _optional_request_text(fields.get("run_id"), "run_id")
    outcome = _optional_request_text(fields.get("outcome"), "outcome")
    dispositions = _request_dispositions(fields.get("dispositions", []), "dispositions")
    publications = _request_publications(fields.get("publications", []))
    if action == "start":
        if workspace_id is None:
            raise ValidationError("missing-field", "workspace_id", "Start requires workspace_id.")
    elif action == "record-worker":
        if run_id is None or fields.get("worker_id") is None:
            raise ValidationError(
                "missing-field", "run_id/worker_id", "record-worker requires run_id and worker_id."
            )
        if any(
            field in fields
            for field in (
                "selected",
                "outcome",
                "dispositions",
                "publications",
                "automation_id",
            )
        ):
            raise ValidationError(
                "invalid-field",
                "record-worker",
                "Worker attachment accepts identity metadata only.",
            )
    elif action == "finish":
        if run_id is None:
            raise ValidationError("missing-field", "run_id", "Finish requires run_id.")
        if outcome is None:
            raise ValidationError("missing-field", "outcome", "Finish requires outcome.")
    elif action == "drain":
        if run_id is None:
            raise ValidationError("missing-field", "run_id", "Drain requires a recorded run_id.")
        if not selected:
            raise ValidationError("missing-field", "selected", "Drain requires selected snapshots.")
        if not dispositions:
            raise ValidationError("missing-field", "dispositions", "Drain requires dispositions.")
    automatic = fields.get("automatic", False)
    if not isinstance(automatic, bool):
        raise ValidationError("invalid-type", "automatic", "Expected a boolean.")
    completion = _optional_request_text(fields.get("completion"), "completion")
    if completion is not None and completion not in {"completed", "deferred", "failed", "empty"}:
        raise ValidationError("invalid-value", "completion", "Unknown terminal classification.")
    return CompoundRequest(
        automatic=automatic,
        completion=completion,
        worker_id=_optional_worker_handle(fields.get("worker_id"), "worker_id"),
        parent_session_id=_optional_worker_handle(
            fields.get("parent_session_id"), "parent_session_id"
        ),
        recovery_of=_optional_request_text(fields.get("recovery_of"), "recovery_of"),
        expected_trigger=parse_compound_trigger(fields["expected_trigger"], "expected_trigger")
        if "expected_trigger" in fields
        else None,
        action=action,
        workspace_id=workspace_id,
        selected=selected,
        harness=harness,
        session_id=session_id,
        automation_id=automation_id,
        run_id=run_id,
        outcome=outcome,
        dispositions=dispositions,
        publications=publications,
    )


def _request_snapshots(value: object, path: str) -> tuple[SignalSnapshot, ...]:
    if not isinstance(value, list):
        raise ValidationError("invalid-type", path, "Expected a list of snapshots.")
    result: list[SignalSnapshot] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        fields = read_mapping(item, item_path, {"id", "path", "fingerprint"})
        fingerprint = read_string(fields["fingerprint"], f"{item_path}.fingerprint")
        if not _FINGERPRINT.fullmatch(fingerprint):
            raise ValidationError(
                "invalid-value",
                f"{item_path}.fingerprint",
                "Expected sha256:<64 lowercase hex digits>.",
            )
        result.append(
            SignalSnapshot(
                id=read_string(fields["id"], f"{item_path}.id"),
                path=read_string(fields["path"], f"{item_path}.path"),
                fingerprint=fingerprint,
            )
        )
    if len({item.id for item in result}) != len(result):
        raise ValidationError("duplicate-value", path, "Snapshot IDs must be unique.")
    return tuple(result)


def _request_dispositions(value: object, path: str) -> tuple[SignalDisposition, ...]:
    if not isinstance(value, list):
        raise ValidationError("invalid-type", path, "Expected a list of dispositions.")
    result: list[SignalDisposition] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        fields = read_mapping(
            item,
            item_path,
            {"signal_id", "decision", "rationale"},
            {"owners", "owner_unavailable_reason"},
        )
        try:
            decision = CompoundDecision(read_string(fields["decision"], f"{item_path}.decision"))
        except ValueError as error:
            raise ValidationError(
                "invalid-value", f"{item_path}.decision", "Unknown decision."
            ) from error
        owners = _request_owners(fields.get("owners", []), f"{item_path}.owners")
        unavailable = _optional_request_text(
            fields.get("owner_unavailable_reason"), f"{item_path}.owner_unavailable_reason"
        )
        if decision in _WRITE_DECISIONS and not owners and unavailable is None:
            raise ValidationError(
                "missing-field",
                f"{item_path}.owners",
                "Write decisions require owners or an explicit owner_unavailable_reason.",
            )
        result.append(
            SignalDisposition(
                signal_id=read_string(fields["signal_id"], f"{item_path}.signal_id"),
                decision=decision,
                rationale=read_string(fields["rationale"], f"{item_path}.rationale"),
                owners=owners,
                owner_unavailable_reason=unavailable,
            )
        )
    if len({item.signal_id for item in result}) != len(result):
        raise ValidationError("duplicate-value", path, "Disposition IDs must be unique.")
    return tuple(result)


def _request_owners(value: object, path: str) -> tuple[OwnerReference, ...]:
    if not isinstance(value, list):
        raise ValidationError("invalid-type", path, "Expected a list of owners.")
    result: list[OwnerReference] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        fields = read_mapping(item, item_path, {"path"}, {"source", "repository", "package"})
        if ("source" in fields) == ("repository" in fields):
            raise ValidationError(
                "invalid-value", item_path, "Supply source or repository, exclusively."
            )
        if "package" in fields and "repository" not in fields:
            raise ValidationError("invalid-value", item_path, "Package owners require repository.")
        result.append(
            OwnerReference(
                path=read_relative_path(fields["path"], f"{item_path}.path"),
                source=read_identifier(fields["source"], f"{item_path}.source")
                if "source" in fields
                else None,
                repository=_optional_request_text(
                    fields.get("repository"), f"{item_path}.repository"
                ),
                package=_optional_request_text(fields.get("package"), f"{item_path}.package"),
            )
        )
    if len(set(result)) != len(result):
        raise ValidationError("duplicate-value", path, "Owner references must be unique.")
    return tuple(result)


def _request_publications(value: object) -> tuple[PublicationEvidence, ...]:
    if not isinstance(value, list):
        raise ValidationError("invalid-type", "publications", "Expected a list of publications.")
    result = tuple(
        _request_publication(item, f"publications[{index}]") for index, item in enumerate(value)
    )
    if len({item.repository for item in result}) != len(result):
        raise ValidationError(
            "duplicate-value", "publications", "Publication repositories must be unique."
        )
    return result


def _request_publication(value: object, path: str) -> PublicationEvidence:
    fields = read_mapping(
        value,
        path,
        {"status", "repository", "publication_verified"},
        {
            "pull_request",
            "commit",
            "checkout",
            "before_revision",
            "after_revision",
            "unavailable_reason",
        },
    )
    status = read_string(fields["status"], f"{path}.status")
    if status not in {"published", "not-required", "unavailable", "pending"}:
        raise ValidationError("invalid-value", f"{path}.status", "Unknown publication status.")
    repository = read_string(fields["repository"], f"{path}.repository")
    verified = fields["publication_verified"]
    if not isinstance(verified, bool):
        raise ValidationError("invalid-type", f"{path}.publication_verified", "Expected a boolean.")
    number = fields.get("pull_request")
    if number is not None and (
        isinstance(number, bool) or not isinstance(number, int) or number < 1
    ):
        raise ValidationError(
            "invalid-value", f"{path}.pull_request", "Expected a positive integer."
        )
    if ("before_revision" in fields) != ("after_revision" in fields):
        raise ValidationError("missing-field", path, "Provide both revision boundaries.")
    values = {
        key: _optional_request_text(fields.get(key), f"{path}.{key}")
        for key in (
            "commit",
            "checkout",
            "before_revision",
            "after_revision",
            "unavailable_reason",
        )
    }
    commit = values["commit"]
    if commit is not None and not _COMMIT.fullmatch(commit):
        raise ValidationError("invalid-value", f"{path}.commit", "Expected a full commit hash.")
    if status == "unavailable" and values["unavailable_reason"] is None:
        raise ValidationError(
            "missing-field", f"{path}.unavailable_reason", "Explain unavailable evidence."
        )
    return PublicationEvidence(
        status=status,
        repository=repository,
        publication_verified=verified,
        pull_request=number,
        **values,
    )


def _optional_request_text(value: object, path: str) -> str | None:
    return None if value is None else read_string(value, path)


def _optional_handle(value: object, path: str) -> str | None:
    result = _optional_request_text(value, path)
    if result is not None and (
        len(result) > 256
        or any(
            character.isspace() or ord(character) < 32 or character in "/\\$`"
            for character in result
        )
    ):
        raise ValidationError("invalid-value", path, "Expected a short opaque handle.")
    return result


__all__ = [
    "CompoundDecision",
    "CompoundRequest",
    "OwnerReference",
    "PublicationEvidence",
    "PullRequestCandidate",
    "PullRequestSelection",
    "SignalDisposition",
    "SignalSnapshot",
    "can_drain",
    "drainable_snapshots",
    "eligible_pull_request",
    "select_pull_request",
    "parse_compound_request",
]


def _optional_worker_handle(value: object, path: str) -> str | None:
    """Keep exact exposed worker handles, including provider path-shaped IDs."""
    result = _optional_request_text(value, path)
    if result is not None and (
        len(result) > 256
        or any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in result
        )
    ):
        raise ValidationError("invalid-value", path, "Expected a short opaque worker handle.")
    return result
