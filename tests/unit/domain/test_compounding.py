"""Exercise pure PR-selection and signal-disposition algebra."""

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
            publication_verified=verified,
            publication=PublicationEvidence(
                "published", repository="example/knowledge", commit="a" * 40
            ),
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
        publication_verified=True,
        publication=PublicationEvidence(
            "published", repository="example/knowledge", commit="a" * 40
        ),
    ) == (snapshots[0],)
    assert (
        drainable_snapshots(
            snapshots,
            dispositions,
            current_fingerprints={"one": "sha256:" + "c" * 64},
            publication_verified=True,
            publication=PublicationEvidence(
                "published", repository="example/knowledge", commit="a" * 40
            ),
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
    "publication",
    [
        None,
        PublicationEvidence("published"),
        PublicationEvidence("published", repository="example/knowledge"),
        PublicationEvidence("pending", repository="example/knowledge", commit="abc"),
        PublicationEvidence("unavailable", unavailable_reason="No publication route."),
    ],
)
def test_write_drain_requires_concrete_publication_evidence(publication) -> None:
    assert not can_drain(
        _disposition("one", CompoundDecision.UPDATE),
        publication_verified=True,
        publication=publication,
    )


def test_external_owner_must_match_the_declared_publication_repository() -> None:
    owner = OwnerReference(
        "skills/example/SKILL.md", repository="example/package", package="skills"
    )
    decision = SignalDisposition("one", CompoundDecision.UPDATE, "Fixed source skill.", (owner,))
    publication = PublicationEvidence("published", repository="example/other", commit="abc")
    assert not can_drain(decision, publication_verified=True, publication=publication)


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
        publication_verified=True,
        publication=PublicationEvidence("published", repository="example/pkg", commit="abc"),
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
