"""Source-owned provider-neutral discovery and reflection reminder text."""

from importlib.resources import files
from types import MappingProxyType

from agent_knowledge.domain.hooks import HookMessage, HookProvider

START_DISCOVERY_MESSAGE = (
    "Before starting work, run `agent-knowledge describe`, then use targeted "
    "`search` and `inspect` calls for the task. Follow the installed guide."
)
RESUME_DISCOVERY_MESSAGE = (
    "Context may have been compacted. Run `agent-knowledge describe` again, then "
    "rediscover relevant metadata with targeted `search` and `inspect` calls."
)
REFLECTION_REMINDER_MESSAGE = (
    files("agent_knowledge.resources")
    .joinpath("reflection-reminder.txt")
    .read_text(encoding="utf-8")
    .strip()
)
SESSION_ID_PREFIX = (
    "Provider session ID (copy exactly into origin.session_id for a harness-origin signal): "
)
PROVIDER_PREFIX = (
    "Provider harness (copy exactly into origin.harness for a harness-origin signal): "
)
CREDENTIAL_ACTIVATION_FAILURE_MESSAGE = (
    "Profile credential activation failed. Run the exact profile-aware `doctor` command "
    "reported by `knowledge-setup`, repair the named environment, then start a new session."
)

DISCOVERY_MESSAGES = MappingProxyType(
    {
        HookMessage.START_DISCOVERY: START_DISCOVERY_MESSAGE,
        HookMessage.RESUME_DISCOVERY: RESUME_DISCOVERY_MESSAGE,
    }
)


def discovery_message(message: HookMessage) -> str:
    """Return the static discovery prefix for a message identifier."""
    if message is HookMessage.REFLECTION:
        return REFLECTION_REMINDER_MESSAGE
    return DISCOVERY_MESSAGES[message]


def render_message(message: HookMessage, provider: HookProvider, session_id: str) -> str:
    """Render one reminder with the normalized provider and exact session handle."""
    if not session_id:
        raise ValueError("A session ID is required to render a reminder.")
    match message:
        case HookMessage.START_DISCOVERY:
            body = START_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
        case HookMessage.RESUME_DISCOVERY:
            body = RESUME_DISCOVERY_MESSAGE + "\n\n" + REFLECTION_REMINDER_MESSAGE
        case HookMessage.REFLECTION:
            body = REFLECTION_REMINDER_MESSAGE
    return body + "\n\n" + PROVIDER_PREFIX + provider.value + "\n" + SESSION_ID_PREFIX + session_id


__all__ = [
    "CREDENTIAL_ACTIVATION_FAILURE_MESSAGE",
    "DISCOVERY_MESSAGES",
    "REFLECTION_REMINDER_MESSAGE",
    "RESUME_DISCOVERY_MESSAGE",
    "PROVIDER_PREFIX",
    "SESSION_ID_PREFIX",
    "START_DISCOVERY_MESSAGE",
    "discovery_message",
    "render_message",
]
