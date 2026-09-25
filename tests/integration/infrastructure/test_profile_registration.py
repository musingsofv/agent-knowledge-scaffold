"""Preserve reviewed YAML and refuse stale or interrupted setup writes."""

import hashlib
from pathlib import Path

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.profiles import replace_registry

INITIAL = b"# My private labels\nschema_version: knowledge-profiles.v1\nprofiles: {}\n"
UPDATED = INITIAL.replace(b"profiles: {}", b"profiles:\n  personal: {config: ./personal.yaml}")


def test_register_repeat_and_extend_preserve_reviewed_bytes(tmp_path: Path) -> None:
    path = tmp_path / "nested/config.yaml"
    replace_registry(path, INITIAL, expected_sha256=None)
    before = hashlib.sha256(INITIAL).hexdigest()
    replace_registry(path, INITIAL, expected_sha256=before)
    replace_registry(path, UPDATED, expected_sha256=before)
    assert path.read_bytes() == UPDATED


def test_stale_or_missing_precondition_cannot_overwrite_existing_registry(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_bytes(INITIAL)
    for expected in (None, hashlib.sha256(UPDATED).hexdigest()):
        with pytest.raises(ValidationError, match="Reinspect"):
            replace_registry(path, UPDATED, expected_sha256=expected)
        assert path.read_bytes() == INITIAL


def test_interrupted_replace_leaves_existing_registry_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.yaml"
    path.write_bytes(INITIAL)

    def interrupted(*args: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("agent_knowledge.infrastructure.profiles.os.replace", interrupted)
    with pytest.raises(AdapterError):
        replace_registry(path, UPDATED, expected_sha256=hashlib.sha256(INITIAL).hexdigest())
    assert path.read_bytes() == INITIAL
    assert sorted(item.name for item in tmp_path.iterdir()) == ["config.yaml", "config.yaml.lock"]


def test_invalid_candidate_does_not_create_registry(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with pytest.raises(ValidationError):
        replace_registry(path, b"profiles: {}", expected_sha256=None)
    assert not path.exists()
