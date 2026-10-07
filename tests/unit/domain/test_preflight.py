"""The diagnostic request stays strict, immutable and free of machine guesses."""

import pytest

from agent_knowledge.domain.preflight import PreflightRequest, parse_preflight_request
from agent_knowledge.domain.validation import ValidationError


def test_defaults_do_not_choose_a_provider_or_execution_target():
    assert parse_preflight_request({}) == PreflightRequest()


@pytest.mark.parametrize(
    "payload",
    [
        {"install": True},
        {"mode": "repair"},
        {"provider": "other"},
        {"expected_execution": "unknown"},
        {"mode": True},
        {"consumer": "/work\nsecret"},
        {"expected_workspace_id": "Unknown Workspace"},
        {"expected_venv": None},
    ],
)
def test_request_rejects_unsupported_or_ambiguous_actions(payload):
    with pytest.raises(ValidationError):
        parse_preflight_request(payload)


def test_explicit_request_keeps_exact_selection_expectations():
    parsed = parse_preflight_request(
        {
            "mode": "write",
            "provider": "copilot",
            "expected_execution": "container",
            "expected_venv": "/opt/runtime",
            "consumer": "/work/orders",
            "expected_workspace_id": "repo:orders",
        }
    )
    assert parsed.mode == "write"
    assert parsed.provider == "copilot"
    assert parsed.expected_execution == "container"
    assert parsed.expected_venv == "/opt/runtime"
