"""Exercise pure PR-selection and signal-disposition algebra."""

from dataclasses import replace

import pytest

from agent_knowledge.domain.compounding import (
    CompoundDecision,
    OwnerReference,
    PublicationEvidence,
    PullRequestCandidate,
    SignalDisposition,
    SignalSnapshot,
    can_drain,
    drainable_snapshots,
    eligible_pull_request,
    parse_compound_request,
    select_pull_request,
)
from agent_knowledge.domain.validation import ValidationError


def _pr(
    number: int,
    *,
    author: str = "alice",
    state: str = "OPEN",
    branch: str = "knowledge/commerce",
    updated: str = "2026-09-10T10:00:00Z",
) -> PullRequestCandidate:
    return PullRequestCandidate(number, author, state, branch, "Knowledge", updated)


def _snapshot(name: str, fingerprint: str = "sha256:" + "a" * 64) -> SignalSnapshot:
    return SignalSnapshot(name, f"/tmp/signals/{name}.md", fingerprint)


def _disposition(name: str, decision: CompoundDecision) -> SignalDisposition:
    return SignalDisposition(
        name,
        decision,
        f"Evidence supports {decision.value}.",
        (OwnerReference("guidance/example.md", source="knowledge"),),
    )


def test_pr_eligibility_requires_open_operator_owned_prefix() -> None:
    assert eligible_pull_request(_pr(1), operator_login="alice", branch_prefix="knowledge/")
    assert not eligible_pull_request(
        _pr(2, author="bob"), operator_login="alice", branch_prefix="knowledge/"
    )
    assert not eligible_pull_request(
        _pr(3, state="closed"), operator_login="alice", branch_prefix="knowledge/"
    )
    assert not eligible_pull_request(
        _pr(4, branch="feature/thing"), operator_login="alice", branch_prefix="knowledge/"
    )


def test_pr_selection_honors_explicit_eligible_then_latest_with_stable_tie() -> None:
    candidates = (
        _pr(1, updated="2026-09-10T10:00:00Z"),
        _pr(2, updated="2026-09-10T11:00:00Z"),
        _pr(3, updated="2026-09-10T11:00:00Z"),
        _pr(4, author="bob", updated="2026-09-10T12:00:00Z"),
    )
    selected = select_pull_request(candidates, operator_login="alice", branch_prefix="knowledge/")
    assert selected.selected == candidates[2]
    assert "most recently" in selected.reason
    explicit = select_pull_request(
        candidates, operator_login="alice", branch_prefix="knowledge/", explicit_number=1
    )
    assert explicit.selected == candidates[0]
    rejected = select_pull_request(
        candidates, operator_login="alice", branch_prefix="knowledge/", explicit_number=4
    )
    assert rejected.selected is None
    assert "not eligible" in rejected.reason


def _publication(
    repository: str = "example/knowledge", *, verified: bool = True, status: str = "published"
) -> PublicationEvidence:
    return PublicationEvidence(status, repository, verified, commit="a" * 40)


@pytest.mark.parametrize(
    ("decision", "verified", "expected"),
    [
        (CompoundDecision.UPDATE, True, True),
        (CompoundDecision.UPDATE, False, False),
        (CompoundDecision.CREATE, True, True),
        (CompoundDecision.DELETE_RETIRE, False, False),
        (CompoundDecision.KEEP, False, True),
        (CompoundDecision.SKIP, False, True),
        (CompoundDecision.DEFER, True, False),
    ],
)
def test_drain_gate_requires_publication_for_writes(
    decision: CompoundDecision, verified: bool, expected: bool
) -> None:
    assert (
        can_drain(
            _disposition("one", decision),
            publications=(_publication(verified=verified),),
            source_repositories={"knowledge": "example/knowledge"},
        )
        is expected
    )


def test_drainable_snapshots_retain_changed_missing_and_deferred_inputs() -> None:
    snapshots = (_snapshot("one"), _snapshot("two", "sha256:" + "b" * 64))
    dispositions = (
        _disposition("one", CompoundDecision.UPDATE),
        _disposition("two", CompoundDecision.DEFER),
    )
    assert drainable_snapshots(
        snapshots,
        dispositions,
        current_fingerprints={"one": snapshots[0].fingerprint, "two": "sha256:" + "c" * 64},
        publications=(_publication(),),
        source_repositories={"knowledge": "example/knowledge"},
    ) == (snapshots[0],)
    assert (
        drainable_snapshots(
            snapshots,
            dispositions,
            current_fingerprints={"one": "sha256:" + "c" * 64},
            publications=(_publication(),),
            source_repositories={"knowledge": "example/knowledge"},
        )
        == ()
    )


def test_compound_request_parses_action_specific_contract() -> None:
    request = parse_compound_request(
        {
            "action": "drain",
            "run_id": "compound-" + "a" * 32,
            "selected": [
                {
                    "id": "one",
                    "path": "/tmp/signals/one.md",
                    "fingerprint": "sha256:" + "a" * 64,
                }
            ],
            "dispositions": [
                {"signal_id": "one", "decision": "keep", "rationale": "Already covered."}
            ],
        }
    )
    assert request.action == "drain"
    assert request.dispositions[0].decision is CompoundDecision.KEEP


def test_finish_request_cannot_fabricate_drained_ids() -> None:
    with pytest.raises(ValidationError, match="drained"):
        parse_compound_request(
            {"action": "finish", "run_id": "compound-1", "outcome": "published", "drained": ["one"]}
        )


@pytest.mark.parametrize(
    ("value", "code", "path"),
    [
        ({"action": "start"}, "missing-field", "workspace_id"),
        ({"action": "finish", "workspace_id": "repo:orders"}, "missing-field", "run_id"),
        (
            {"action": "drain", "run_id": "compound-" + "a" * 32, "selected": []},
            "missing-field",
            "selected",
        ),
        ({"action": "status", "unknown": True}, "unknown-field", "unknown"),
        (
            {
                "action": "drain",
                "run_id": "compound-" + "a" * 32,
                "selected": [{"id": "one", "path": "/tmp/one", "fingerprint": "bad"}],
                "dispositions": [],
            },
            "invalid-value",
            "selected[0].fingerprint",
        ),
    ],
)
def test_compound_request_rejects_ambiguous_or_unsafe_inputs(
    value: object, code: str, path: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_compound_request(value)
    assert (caught.value.code, caught.value.path) == (code, path)


def test_duplicate_snapshot_and_disposition_ids_are_rejected() -> None:
    duplicate = {
        "action": "drain",
        "run_id": "compound-" + "a" * 32,
        "selected": [
            {"id": "one", "path": "/tmp/one", "fingerprint": "sha256:" + "a" * 64},
            {"id": "one", "path": "/tmp/two", "fingerprint": "sha256:" + "b" * 64},
        ],
        "dispositions": [],
    }
    with pytest.raises(ValidationError, match="unique"):
        parse_compound_request(duplicate)


@pytest.mark.parametrize(
    "publications",
    [
        (),
        (replace(_publication(), commit=None),),
        (replace(_publication(), commit="abc"),),
        (_publication(status="pending"),),
        (_publication(verified=False),),
        (replace(_publication(status="unavailable"), unavailable_reason="No access."),),
        (replace(_publication(), unavailable_reason="Owner is unavailable."),),
    ],
)
def test_write_drain_requires_concrete_publication_evidence(publications) -> None:
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publications=publications,
        source_repositories={"knowledge": "example/knowledge"},
    )


def test_external_owner_must_match_the_declared_publication_repository() -> None:
    owner = OwnerReference(
        "skills/example/SKILL.md", repository="example/package", package="skills"
    )
    decision = SignalDisposition("one", CompoundDecision.UPDATE, "Fixed source skill.", (owner,))
    assert not can_drain(decision, publications=(_publication("example/other"),))
    assert can_drain(decision, publications=(_publication("example/package"),))


def test_write_request_requires_owner_or_explicit_unavailable_reason() -> None:
    decision = {"signal_id": "one", "decision": "update", "rationale": "Needs a source fix."}
    with pytest.raises(ValidationError, match="owners"):
        parse_compound_request({"action": "status", "dispositions": [decision]})
    request = parse_compound_request(
        {
            "action": "status",
            "dispositions": [
                {
                    **decision,
                    "owner_unavailable_reason": "Authoritative source package is unavailable.",
                }
            ],
        }
    )
    assert not can_drain(
        request.dispositions[0],
        publications=(_publication("example/pkg"),),
    )


@pytest.mark.parametrize(
    "owner",
    [
        {"source": "knowledge", "repository": "example/pkg", "path": "guide.md"},
        {"source": "knowledge", "path": "../escape.md"},
        {"source": "knowledge", "package": "pkg", "path": "guide.md"},
        {"path": "guide.md"},
    ],
)
def test_owner_identity_is_unambiguous_and_contained(owner) -> None:
    with pytest.raises(ValidationError):
        parse_compound_request(
            {
                "action": "status",
                "dispositions": [
                    {
                        "signal_id": "one",
                        "decision": "update",
                        "rationale": "Needs a source fix.",
                        "owners": [owner],
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"automatic": "yes"},
        {"completion": "succeeded"},
        {"worker_id": "bad\nhandle"},
        {"parent_session_id": "bad\nhandle"},
        {"expected_trigger": {"mode": "prompt", "owner": "shared", "unknown": True}},
    ],
)
def test_reject_invalid_automatic_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_compound_request({"action": "status", **changes})


def test_exact_worker_context_and_trigger_compare_are_parsed() -> None:
    request = parse_compound_request(
        {
            "action": "start",
            "workspace_id": "workspace:example",
            "automatic": True,
            "worker_id": "provider:opaque/worker",
            "parent_session_id": "parent:opaque/session",
            "recovery_of": "compound-prior",
        }
    )
    assert request.worker_id == "provider:opaque/worker"
    assert request.parent_session_id == "parent:opaque/session"
    trigger_request = parse_compound_request(
        {"action": "configure-trigger", "expected_trigger": {"mode": "prompt", "owner": "shared"}}
    )
    assert trigger_request.expected_trigger.interval_seconds == 86400


@pytest.mark.parametrize(
    "value",
    [
        {"action": "record-worker", "run_id": "compound-example"},
        {"action": "record-worker", "worker_id": "native-worker"},
        {
            "action": "record-worker",
            "run_id": "compound-example",
            "worker_id": "native-worker",
            "selected": [],
        },
        {
            "action": "record-worker",
            "run_id": "compound-example",
            "worker_id": "native-worker",
            "automation_id": "trigger-owner",
        },
    ],
)
def test_worker_attachment_accepts_only_complete_identity_metadata(
    value: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_compound_request(value)


def _multi_owner_disposition(identifier: str = "one") -> SignalDisposition:
    return SignalDisposition(
        identifier,
        CompoundDecision.UPDATE,
        "Published the durable decision and owning consumer procedure.",
        (
            OwnerReference("guidance/example.md", source="knowledge"),
            OwnerReference(".apm/skills/example/SKILL.md", repository="example/consumer"),
        ),
    )


@pytest.mark.parametrize("fault", [None, "missing", "pending", "unverified", "mismatch"])
def test_multi_repository_writes_require_every_authoring_owner(fault: str | None) -> None:
    consumer = _publication("example/consumer")
    publications = (_publication(), consumer)
    if fault == "missing":
        publications = (_publication(),)
    elif fault == "pending":
        publications = (_publication(), replace(consumer, status="pending"))
    elif fault == "unverified":
        publications = (_publication(), replace(consumer, publication_verified=False))
    elif fault == "mismatch":
        publications = (_publication(), replace(consumer, repository="example/other"))
    assert can_drain(
        _multi_owner_disposition(),
        publications=publications,
        source_repositories={"knowledge": "example/knowledge"},
    ) is (fault is None)


def test_each_signal_uses_its_own_owner_coverage_and_unrelated_evidence_is_irrelevant() -> None:
    selected = tuple(_snapshot(name) for name in ("covered", "partial", "deferred", "kept"))
    dispositions = (
        _disposition("covered", CompoundDecision.UPDATE),
        _multi_owner_disposition("partial"),
        _disposition("deferred", CompoundDecision.DEFER),
        _disposition("kept", CompoundDecision.KEEP),
    )
    result = drainable_snapshots(
        selected,
        dispositions,
        current_fingerprints={item.id: item.fingerprint for item in selected},
        publications=(_publication(), _publication("example/unrelated", verified=False)),
        source_repositories={"knowledge": "example/knowledge"},
    )
    assert tuple(item.id for item in result) == ("covered", "kept")


@pytest.mark.parametrize("source_repositories", [None, {}, {"other": "example/knowledge"}])
def test_source_owner_requires_its_configured_publication_route(source_repositories) -> None:
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publications=(_publication(),),
        source_repositories=source_repositories,
    )


def test_source_id_and_repository_name_are_not_interchangeable() -> None:
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publications=(_publication("knowledge"),),
        source_repositories={"knowledge": "example/knowledge"},
    )


@pytest.mark.parametrize("decision", [CompoundDecision.KEEP, CompoundDecision.SKIP])
def test_non_write_decisions_need_only_a_rationale(decision: CompoundDecision) -> None:
    disposition = SignalDisposition(
        "one",
        decision,
        "The accepted deferral is already recorded in the durable owner.",
        owners=(OwnerReference("missing.md", source="unavailable"),),
        owner_unavailable_reason="No new authoring required.",
    )
    assert can_drain(disposition)
    assert not can_drain(replace(disposition, rationale="  "))


def test_same_repository_can_cover_multiple_distinct_owners() -> None:
    disposition = replace(
        _multi_owner_disposition(),
        owners=(
            OwnerReference("guidance/one.md", source="knowledge"),
            OwnerReference(".apm/skills/example/SKILL.md", repository="example/knowledge"),
        ),
    )
    assert can_drain(
        disposition,
        publications=(_publication(),),
        source_repositories={"knowledge": "example/knowledge"},
    )


def _publication_input(repository: str = "example/knowledge") -> dict[str, object]:
    return {
        "status": "published",
        "repository": repository,
        "publication_verified": True,
        "commit": "a" * 40,
    }


def test_publications_parse_independent_verification_and_exact_commits() -> None:
    publications = [
        {**_publication_input(), "pull_request": 17},
        {**_publication_input("example/consumer"), "commit": "b" * 64},
    ]
    request = parse_compound_request({"action": "status", "publications": publications})
    assert len(request.publications) == 2
    assert request.publications[0].pull_request == 17
    assert request.publications[1].commit == "b" * 64
    assert all(item.publication_verified for item in request.publications)


@pytest.mark.parametrize("field", ["publication", "publication_verified"])
def test_legacy_publication_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_compound_request({"action": "status", field: True})
    assert (caught.value.code, caught.value.path) == ("unknown-field", field)


@pytest.mark.parametrize("field", ["status", "repository", "publication_verified"])
def test_each_publication_requires_its_own_identity_status_and_verification(field: str) -> None:
    value = _publication_input()
    value.pop(field)
    with pytest.raises(ValidationError) as caught:
        parse_compound_request({"action": "status", "publications": [value]})
    assert caught.value.code == "missing-field"
    assert caught.value.path == f"publications[0].{field}"


@pytest.mark.parametrize("value", [None, {}, "example/knowledge", True])
def test_publications_must_be_a_list(value: object) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_compound_request({"action": "status", "publications": value})
    assert (caught.value.code, caught.value.path) == ("invalid-type", "publications")


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "merged"},
        {"repository": ""},
        {"publication_verified": "true"},
        {"publication_verified": 1},
        {"commit": "abc"},
        {"commit": "A" * 40},
        {"commit": "a" * 41},
        {"commit": "--HEAD"},
        {"pull_request": True},
        {"pull_request": 0},
        {"before_revision": "a" * 40},
        {"after_revision": "b" * 40},
        {"status": "unavailable"},
        {"unknown": "field"},
    ],
)
def test_publication_rejects_malformed_or_ambiguous_evidence(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_compound_request(
            {"action": "status", "publications": [{**_publication_input(), **changes}]}
        )


@pytest.mark.parametrize("changes", [{}, {"commit": "b" * 40}, {"publication_verified": False}])
def test_duplicate_repository_evidence_is_rejected_even_if_identical(changes) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_compound_request(
            {
                "action": "status",
                "publications": [_publication_input(), {**_publication_input(), **changes}],
            }
        )
    assert (caught.value.code, caught.value.path) == ("duplicate-value", "publications")
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publications=(_publication(), _publication()),
        source_repositories={"knowledge": "example/knowledge"},
    )


@pytest.mark.parametrize("commit", [None, "missing"])
def test_pr_number_without_exact_commit_parses_but_cannot_drain(commit: str | None) -> None:
    value = {**_publication_input(), "pull_request": 17}
    if commit == "missing":
        value.pop("commit")
    else:
        value["commit"] = commit
    request = parse_compound_request({"action": "status", "publications": [value]})
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publications=request.publications,
        source_repositories={"knowledge": "example/knowledge"},
    )
