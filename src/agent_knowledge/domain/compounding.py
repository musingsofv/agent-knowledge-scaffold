"""Pure decisions used by the scheduled and on-demand compounding workflow.

The compounding skill owns agent judgement, Git and GitHub commands.  This
module owns only the small deterministic decisions that must remain stable
across harnesses: knowledge-PR eligibility/selection and safe disposition
gates for signal drainage.  It does not read files, inspect Git, or contact a
provider.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

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
    repository: str | None = None
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
    publication_verified: bool = False
    publication: PublicationEvidence | None = None


_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}\Z")


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
    publication_verified: bool,
    publication: PublicationEvidence | None = None,
) -> bool:
    """Gate removal on a confirmed write or an explicit non-write decision."""
    if not disposition.rationale.strip():
        return False
    if disposition.decision in _NON_WRITE_DECISIONS:
        return True
    return (
        disposition.decision in _WRITE_DECISIONS
        and publication_verified
        and bool(disposition.owners)
        and disposition.owner_unavailable_reason is None
        and publication is not None
        and publication.status == "published"
        and publication.repository is not None
        and bool(publication.commit or publication.pull_request)
        and publication.unavailable_reason is None
        and all(
            owner.repository is None or owner.repository == publication.repository
            for owner in disposition.owners
        )
    )


def drainable_snapshots(
    snapshots: tuple[SignalSnapshot, ...],
    dispositions: tuple[SignalDisposition, ...],
    *,
    current_fingerprints: dict[str, str],
    publication_verified: bool,
    publication: PublicationEvidence | None = None,
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
            disposition, publication_verified=publication_verified, publication=publication
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
            "workspace_id",
            "selected",
            "harness",
            "session_id",
            "automation_id",
            "run_id",
            "outcome",
            "dispositions",
            "publication",
            "publication_verified",
        },
    )
    action = read_string(fields["action"], "action")
    if action not in {"status", "start", "finish", "drain"}:
        raise ValidationError("invalid-value", "action", "Expected status, start, finish or drain.")
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
    publication = _request_publication(fields.get("publication"))
    publication_verified = fields.get("publication_verified", False)
    if not isinstance(publication_verified, bool):
        raise ValidationError("invalid-type", "publication_verified", "Expected a boolean.")
    if action == "start":
        if workspace_id is None:
            raise ValidationError("missing-field", "workspace_id", "Start requires workspace_id.")
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
    return CompoundRequest(
        action=action,
        workspace_id=workspace_id,
        selected=selected,
        harness=harness,
        session_id=session_id,
        automation_id=automation_id,
        run_id=run_id,
        outcome=outcome,
        dispositions=dispositions,
        publication_verified=publication_verified,
        publication=publication,
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


def _request_publication(value: object) -> PublicationEvidence | None:
    if value is None:
        return None
    fields = read_mapping(
        value,
        "publication",
        {"status"},
        {
            "repository",
            "pull_request",
            "commit",
            "checkout",
            "before_revision",
            "after_revision",
            "unavailable_reason",
        },
    )
    status = read_string(fields["status"], "publication.status")
    if status not in {"published", "not-required", "unavailable", "pending"}:
        raise ValidationError("invalid-value", "publication.status", "Unknown publication status.")
    number = fields.get("pull_request")
    if number is not None and (
        isinstance(number, bool) or not isinstance(number, int) or number < 1
    ):
        raise ValidationError(
            "invalid-value", "publication.pull_request", "Expected a positive integer."
        )
    if ("before_revision" in fields) != ("after_revision" in fields):
        raise ValidationError("missing-field", "publication", "Provide both revision boundaries.")
    values = {
        key: _optional_request_text(fields.get(key), f"publication.{key}")
        for key in (
            "repository",
            "commit",
            "checkout",
            "before_revision",
            "after_revision",
            "unavailable_reason",
        )
    }
    if status == "unavailable" and values["unavailable_reason"] is None:
        raise ValidationError(
            "missing-field", "publication.unavailable_reason", "Explain unavailable evidence."
        )
    return PublicationEvidence(status=status, pull_request=number, **values)


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
