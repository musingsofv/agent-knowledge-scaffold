"""Verify native payload normalization and single-channel rendering."""

from typing import Any

import pytest

from agent_knowledge.domain.hooks import HookProvider
from agent_knowledge.entrypoints.hooks.adapters import (
    ClaudeHookAdapter,
    CodexHookAdapter,
    CopilotHookAdapter,
    adapt_payload,
    handle_payload,
)
from agent_knowledge.resources.hook_messages import (
    PROVIDER_PREFIX,
    REFLECTION_REMINDER_MESSAGE,
    RESUME_DISCOVERY_MESSAGE,
    SESSION_ID_PREFIX,
    START_DISCOVERY_MESSAGE,
)


def _provider_context(provider: HookProvider, session_id: object) -> str:
    return PROVIDER_PREFIX + provider.value + "\n" + SESSION_ID_PREFIX + str(session_id)


@pytest.mark.parametrize(
    ("adapter", "payload"),
    [
        (
            CodexHookAdapter(),
            {"hook_event_name": "SessionStart", "source": "startup", "session_id": "c1"},
        ),
        (
            ClaudeHookAdapter(),
            {"hook_event_name": "SessionStart", "source": "new", "session_id": "c2"},
        ),
    ],
)
def test_snake_case_providers_render_hook_specific_context(
    adapter: Any, payload: dict[str, object]
) -> None:
    adapted = adapter.normalize(payload)

    result = handle_payload(payload, provider=adapted.provider)

    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                START_DISCOVERY_MESSAGE
                + "\n\n"
                + REFLECTION_REMINDER_MESSAGE
                + "\n\n"
                + _provider_context(adapted.provider, payload["session_id"])
            ),
        }
    }
    assert "systemMessage" not in result


@pytest.mark.parametrize("source", ["resume", "clear", "compact", "fork"])
def test_codex_resume_sources_use_one_context_channel(source: str) -> None:
    result = handle_payload(
        {"hook_event_name": "SessionStart", "source": source, "session_id": "resume-1"},
        provider=HookProvider.CODEX,
    )

    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert result["hookSpecificOutput"]["additionalContext"].startswith(
        RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
    )
    assert result["hookSpecificOutput"]["additionalContext"].endswith("resume-1")
    assert "systemMessage" not in result


@pytest.mark.parametrize("provider", [HookProvider.CODEX, HookProvider.CLAUDE])
def test_prompt_events_render_reflection_through_one_context_channel(
    provider: HookProvider,
) -> None:
    result = handle_payload(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "prompt-1",
        },
        provider=provider,
    )

    assert result == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                REFLECTION_REMINDER_MESSAGE + "\n\n" + _provider_context(provider, "prompt-1")
            ),
        }
    }
    assert "systemMessage" not in result


def test_copilot_transformed_prompt_appends_reflection_without_interpreting_content() -> None:
    original = "opaque model-facing content\nwith existing runtime context"

    result = handle_payload(
        {
            "sessionId": "prompt-1",
            "prompt": "user-visible prompt",
            "transformedPrompt": original,
        },
        provider=HookProvider.COPILOT,
    )

    assert result == {
        "modifiedTransformedPrompt": (
            original
            + "\n\n"
            + REFLECTION_REMINDER_MESSAGE
            + "\n\n"
            + _provider_context(HookProvider.COPILOT, "prompt-1")
        )
    }


def test_copilot_transformed_prompt_reminder_is_idempotent() -> None:
    rendered = (
        "opaque model-facing content"
        + "\n\n"
        + REFLECTION_REMINDER_MESSAGE
        + "\n\n"
        + _provider_context(HookProvider.COPILOT, "prompt-1")
    )

    assert (
        handle_payload(
            {
                "sessionId": "prompt-1",
                "prompt": "user-visible prompt",
                "transformedPrompt": rendered,
            },
            provider=HookProvider.COPILOT,
        )
        == {}
    )


@pytest.mark.parametrize("transformed", [None, "", 7])
def test_copilot_malformed_transformed_prompt_fails_open(transformed: object) -> None:
    assert (
        handle_payload(
            {"sessionId": "prompt-1", "transformedPrompt": transformed},
            provider=HookProvider.COPILOT,
        )
        == {}
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"hook_event_name": "SessionStart", "source": "startup"},
        {"hook_event_name": "SessionStart", "source": "startup", "session_id": ""},
        {"hook_event_name": "SessionStart", "source": "startup", "session_id": " "},
        {
            "hook_event_name": "SessionStart",
            "source": "startup",
            "session_id": "one",
            "sessionId": "two",
        },
    ],
)
def test_eligible_events_without_one_usable_session_id_fail_open(
    payload: dict[str, object],
) -> None:
    assert handle_payload(payload, provider=HookProvider.CODEX) == {}


def test_copilot_session_id_is_exposed_verbatim() -> None:
    result = handle_payload(
        {"sessionId": "copilot-opaque-7", "timestamp": 1, "source": "startup"},
        provider=HookProvider.COPILOT,
    )

    assert result["additionalContext"].endswith("copilot-opaque-7")
    assert result["additionalContext"].count("copilot-opaque-7") == 1
    assert (
        result["additionalContext"].count("origin.harness for a harness-origin signal): copilot")
        == 1
    )


def test_copilot_resume_keeps_reflection_and_exact_session_id() -> None:
    result = handle_payload(
        {"sessionId": "copilot-resume-7", "timestamp": 1, "source": "resume"},
        provider=HookProvider.COPILOT,
    )

    assert result["additionalContext"].startswith(
        RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
    )
    assert result["additionalContext"].endswith("copilot-resume-7")
    assert PROVIDER_PREFIX + "copilot" in result["additionalContext"]


def test_snake_case_resume_output_contains_session_id() -> None:
    result = handle_payload(
        {"hook_event_name": "SessionStart", "source": "resume", "session_id": "resume-1"},
        provider=HookProvider.CLAUDE,
    )

    assert result["hookSpecificOutput"]["additionalContext"].endswith("resume-1")
    assert PROVIDER_PREFIX + "claude" in result["hookSpecificOutput"]["additionalContext"]


def test_previous_resume_shape_remains_single_context_channel() -> None:
    result = handle_payload(
        {"hook_event_name": "SessionStart", "source": "resume", "session_id": "resume-1"},
        provider=HookProvider.CODEX,
    )

    assert set(result) == {"hookSpecificOutput"}
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert result["hookSpecificOutput"]["additionalContext"].startswith(
        RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
    )
    assert result["hookSpecificOutput"]["additionalContext"].endswith("resume-1")
    assert PROVIDER_PREFIX + "codex" in result["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("source", ["startup", "new", "resume"])
def test_copilot_camel_case_payload_uses_top_level_context(source: str) -> None:
    result = handle_payload(
        {"sessionId": "p1", "timestamp": 1, "cwd": "/tmp", "source": source},
        provider=HookProvider.COPILOT,
    )

    expected = START_DISCOVERY_MESSAGE if source in {"startup", "new"} else RESUME_DISCOVERY_MESSAGE
    assert result["additionalContext"].startswith(expected + "\n\n" + REFLECTION_REMINDER_MESSAGE)
    assert result["additionalContext"].endswith("p1")
    assert PROVIDER_PREFIX + "copilot" in result["additionalContext"]
    assert "hookSpecificOutput" not in result


def test_copilot_pascal_compatibility_payload_is_accepted() -> None:
    result = handle_payload(
        {
            "hook_event_name": "SessionStart",
            "session_id": "p1",
            "timestamp": "2026-09-11T00:00:00Z",
            "source": "resume",
        },
        provider=HookProvider.COPILOT,
    )

    assert result["additionalContext"].startswith(
        RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
    )
    assert result["additionalContext"].endswith("p1")
    assert PROVIDER_PREFIX + "copilot" in result["additionalContext"]


def test_copilot_pascal_payload_is_inferred_without_provider_hint() -> None:
    result = handle_payload(
        {
            "hookEventName": "SessionStart",
            "sessionId": "p1",
            "timestamp": "2026-09-11T00:00:00Z",
            "source": "resume",
        }
    )

    assert result["additionalContext"].startswith(
        RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
    )
    assert result["additionalContext"].endswith("p1")
    assert PROVIDER_PREFIX + "copilot" in result["additionalContext"]
    assert "hookSpecificOutput" not in result


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"hook_event_name": "PostToolUse", "session_id": "s1"},
        {"hook_event_name": "SessionStart", "source": "unknown"},
        {
            "hook_event_name": "SessionStart",
            "source": "startup",
            "reason": "compact",
            "session_id": "s1",
        },
        {"sessionId": "p1", "source": 4},
    ],
)
def test_malformed_or_ineligible_payloads_fail_open_to_empty_output(payload: object) -> None:
    assert handle_payload(payload) == {}


def test_adapters_ignore_transcript_and_path_fields() -> None:
    payload = {
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_id": "s1",
        "transcript_path": "/forbidden/transcript.jsonl",
        "cwd": "/forbidden/worktree",
        "prompt": "should never be inspected",
    }

    adapted = adapt_payload(payload, provider=HookProvider.CLAUDE)

    assert adapted is not None
    assert adapted.event.session_id == "s1"
    assert adapted.event.source == "startup"
    assert adapted.event.reason is None
    assert adapted.event.event.name == "SESSION_START"


def test_copilot_prompt_body_stays_out_of_the_domain_event() -> None:
    adapted = adapt_payload(
        {
            "sessionId": "copilot-1",
            "prompt": "user-visible prompt",
            "transformedPrompt": "opaque model-facing content",
        },
        provider=HookProvider.COPILOT,
    )

    assert adapted is not None
    assert adapted.event.event.name == "USER_PROMPT"
    assert adapted.event.session_id == "copilot-1"
    assert adapted.transformed_prompt == "opaque model-facing content"
    assert not hasattr(adapted.event, "prompt")


def test_adapter_classes_are_available_for_each_supported_provider() -> None:
    assert CodexHookAdapter().provider is HookProvider.CODEX
    assert ClaudeHookAdapter().provider is HookProvider.CLAUDE
    assert CopilotHookAdapter().provider is HookProvider.COPILOT
