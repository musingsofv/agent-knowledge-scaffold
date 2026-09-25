"""The measured payload uses one documented encoding, independent of presentation."""

from agent_knowledge.infrastructure.usage import canonical_json


def test_canonical_json_counts_utf8_not_characters() -> None:
    payload = {"z": "café", "a": [1, True, None]}
    expected = '{"a":[1,true,null],"z":"café"}'.encode()
    assert canonical_json(payload) == expected
    assert len(expected) > len(expected.decode("utf-8"))
