"""Prove strict dotenv parsing never returns credential values."""

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.environment import parse_dotenv_names


def test_dotenv_parser_returns_names_only() -> None:
    secret = "canary-secret-never-returned"

    result = parse_dotenv_names(
        f"# profile\nGITHUB_V_TOKEN={secret}\nexport AWS_TOKEN=plain-token\n".encode()
    )

    assert result == frozenset({"GITHUB_V_TOKEN", "AWS_TOKEN"})
    assert secret not in repr(result)
    assert "plain-token" not in repr(result)


@pytest.mark.parametrize(
    "content",
    [
        b"BROKEN\n",
        b"BAD-NAME=value\n",
        b"EMPTY=\n",
        b"DUPLICATE=one\nDUPLICATE=two\n",
        b"QUOTE='unterminated\n",
        b"NUL=value\x00hidden\n",
        b"NOT_UTF8=\xff\n",
    ],
)
def test_dotenv_parser_rejects_unsafe_or_ambiguous_input_without_echoing_it(
    content: bytes,
) -> None:
    with pytest.raises(ValidationError) as error:
        parse_dotenv_names(content)

    assert "one" not in error.value.message
    assert "two" not in error.value.message
    assert "hidden" not in error.value.message
    assert "unterminated" not in error.value.message
