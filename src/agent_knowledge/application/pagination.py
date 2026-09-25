"""Bind local result pages to an explicit request and immutable scan snapshot."""

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from agent_knowledge.domain.validation import ValidationError, read_mapping


@dataclass(frozen=True)
class Cursor:
    """Address a result page or a selected file's match-location page."""

    offset: int = 0
    channel: str = "items"
    target: str | None = None


def request_fingerprint(request: Mapping[str, object]) -> str:
    """Hash normalized request data without the transport continuation field."""
    fields = dict(request)
    fields.pop("continuation", None)
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def encode_cursor(operation: str, request: str, snapshot: str, cursor: Cursor) -> str:
    """Encode a bounded page reference; cursors confer no access authority."""
    data = {
        "version": 1,
        "operation": operation,
        "request": request,
        "snapshot": snapshot,
        "offset": cursor.offset,
        "channel": cursor.channel,
        "target": cursor.target,
    }
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode()


def decode_cursor(token: str | None, operation: str, request: str, snapshot: str) -> Cursor:
    """Reject malformed, foreign and stale tokens before returning a position."""
    if token is None:
        return Cursor()
    try:
        if len(token) > 4096:
            raise ValueError("oversized cursor")
        decoded: object = json.loads(base64.b64decode(token, altchars=b"-_", validate=True))
        fields = read_mapping(
            decoded,
            "continuation",
            {
                "version",
                "operation",
                "request",
                "snapshot",
                "offset",
                "channel",
                "target",
            },
        )
        offset, channel, target = fields["offset"], fields["channel"], fields["target"]
        if (
            type(fields["version"]) is not int
            or fields["version"] != 1
            or fields["operation"] != operation
            or fields["request"] != request
            or type(offset) is not int
            or offset <= 0
            or not isinstance(channel, str)
            or channel not in {"items", "matches"}
            or not isinstance(fields["snapshot"], str)
            or (target is not None and not isinstance(target, str))
            or (channel == "matches" and not target)
            or (channel == "items" and target is not None)
        ):
            raise ValueError("invalid cursor")
    except (ValueError, UnicodeError, binascii.Error, RecursionError) as error:
        raise ValidationError(
            "invalid-continuation", "continuation", "Invalid cursor for this request."
        ) from error
    if fields["snapshot"] != snapshot:
        raise ValidationError(
            "stale-snapshot", "continuation", "Source snapshot changed; start a fresh request."
        )
    return Cursor(offset, channel, target)


def check_offset(cursor: Cursor, total: int) -> None:
    """Reject a continuation beyond the selected result set."""
    if cursor.offset and cursor.offset >= total:
        raise ValidationError(
            "invalid-continuation", "continuation", "Cursor is outside the result set."
        )
