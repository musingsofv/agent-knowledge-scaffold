"""Validate usage export intervals without reading files or consulting a clock."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from .configuration import read_config_path
from .validation import ValidationError, read_mapping, read_string


@dataclass(frozen=True, slots=True)
class UsageExportQuery:
    """Select a UTC half-open interval and one new local export directory."""

    since: datetime
    until: datetime
    destination: str


def read_utc_timestamp(value: object, path: str) -> datetime:
    """Require explicit UTC, including seconds, without inventing a local timezone."""
    text = read_string(value, path)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", text):
        raise ValidationError("invalid-timestamp", path, "Expected an explicit UTC timestamp.")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as error:
        raise ValidationError(
            "invalid-timestamp", path, "Expected a valid UTC timestamp."
        ) from error


def parse_usage_export_query(value: object) -> UsageExportQuery:
    """Reject ambiguous dates, reversed intervals and extra query fields."""
    fields = read_mapping(value, "", {"since", "until", "destination"})
    since = read_utc_timestamp(fields["since"], "since")
    until = read_utc_timestamp(fields["until"], "until")
    if since >= until:
        raise ValidationError("invalid-interval", "until", "until must be later than since.")
    return UsageExportQuery(since, until, read_config_path(fields["destination"], "destination"))
