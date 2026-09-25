"""UTC intervals remain explicit and independent of machine clock/timezone."""

from datetime import UTC, datetime

import pytest

from agent_knowledge.domain.usage import parse_usage_export_query
from agent_knowledge.domain.validation import ValidationError


def test_export_request_uses_half_open_utc_interval() -> None:
    query = parse_usage_export_query(
        {
            "since": "2026-09-08T00:00:00Z",
            "until": "2026-09-14T00:00:00+00:00",
            "destination": "./review",
        }
    )
    assert query.since == datetime(2026, 9, 8, tzinfo=UTC)
    assert query.until == datetime(2026, 9, 14, tzinfo=UTC)
    assert query.destination == "./review"


@pytest.mark.parametrize(
    "field,value",
    [
        ("since", "2026-09-08"),
        ("since", "2026-09-08T00:00:00"),
        ("since", "2026-09-08T00:00:00+01:00"),
        ("since", "2026-02-30T00:00:00Z"),
        ("until", "2026-09-08T00:00:00Z"),
        ("until", "2026-09-07T00:00:00Z"),
        ("until", 1),
        ("extra", True),
        ("destination", "$HOME/review"),
    ],
)
def test_export_rejects_ambiguous_or_invalid_contract(field: str, value: object) -> None:
    request: dict[str, object] = {
        "since": "2026-09-08T00:00:00Z",
        "until": "2026-09-14T00:00:00Z",
        "destination": "./review",
    }
    request[field] = value
    with pytest.raises(ValidationError):
        parse_usage_export_query(request)
