"""Inspect external profile env files through the guarded adapter."""

import hashlib
from pathlib import Path

import pytest

from agent_knowledge.domain.profiles import EnvironmentVariable
from agent_knowledge.infrastructure.environment import (
    inspect_environment,
    mapped_environment_values,
    pin_session_environment,
)
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.profiles import ResolvedProfileEnvironment


def _environment(path: Path) -> ResolvedProfileEnvironment:
    return ResolvedProfileEnvironment(
        path,
        (
            EnvironmentVariable(
                "github", "GITHUB_V_TOKEN", "GH_TOKEN", "Personal GitHub repositories"
            ),
        ),
    )


def test_private_regular_environment_file_returns_names_only(tmp_path: Path) -> None:
    secret = "environment-adapter-secret-canary"
    path = tmp_path / "personal.env"
    path.write_text(f"GITHUB_V_TOKEN={secret}\nUNDECLARED=ignored\n", encoding="utf-8")
    path.chmod(0o600)

    result = inspect_environment(_environment(path))

    assert result.names == frozenset({"GITHUB_V_TOKEN", "UNDECLARED"})
    assert secret not in repr(result)


def test_provider_mapping_returns_only_declared_targets(tmp_path: Path) -> None:
    path = tmp_path / "personal.env"
    path.write_text("GITHUB_V_TOKEN=secret\nUNDECLARED=ignored\n", encoding="utf-8")
    path.chmod(0o600)

    result = mapped_environment_values(_environment(path))

    assert result == (("GH_TOKEN", "secret"),)


def test_environment_file_rejects_group_or_world_access(tmp_path: Path) -> None:
    path = tmp_path / "personal.env"
    path.write_text("GITHUB_V_TOKEN=secret\n", encoding="utf-8")
    path.chmod(0o640)

    with pytest.raises(AdapterError) as error:
        inspect_environment(_environment(path))

    assert error.value.code == "environment-file-permissions"
    assert "secret" not in error.value.message


def test_environment_file_rejects_symlink_traversal(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    path = real / "personal.env"
    path.write_text("GITHUB_V_TOKEN=secret\n", encoding="utf-8")
    path.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(AdapterError) as error:
        inspect_environment(_environment(alias / "personal.env"))

    assert error.value.code == "unsafe-path"
    assert "secret" not in error.value.message


def test_oversized_session_declaration_is_rejected_before_publication(
    tmp_path: Path,
) -> None:
    variables = tuple(
        EnvironmentVariable(
            str(index),
            f"SOURCE_{index:04d}_{'X' * 40}",
            f"TARGET_{index:04d}_{'Y' * 40}",
            "provider binding",
        )
        for index in range(300)
    )
    environment = ResolvedProfileEnvironment(tmp_path / "profile.env", variables)
    state = tmp_path / "state"

    with pytest.raises(AdapterError) as error:
        pin_session_environment(environment, state_directory=state, session_id="large")

    assert error.value.code == "environment-session-state-invalid"
    assert not list(state.glob("*.json"))


def test_session_pin_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    session_id = "duplicate-json"
    pin = state / f"{hashlib.sha256(session_id.encode()).hexdigest()}.json"
    pin.write_text(
        '{"schema":"profile-environment-session.v1",'
        '"schema":"profile-environment-session.v1",'
        f'"file":"{tmp_path / "profile.env"}",'
        '"variables":[{"from_env":"SOURCE","expose_as":"TARGET"}]}',
        encoding="utf-8",
    )
    pin.chmod(0o600)

    with pytest.raises(AdapterError) as error:
        pin_session_environment(
            _environment(tmp_path / "profile.env"),
            state_directory=state,
            session_id=session_id,
        )

    assert error.value.code == "environment-session-state-invalid"


@pytest.mark.parametrize("target", ["PS4", "HOME", "CLAUDE_ENV_FILE", "LD_PRELOAD"])
def test_session_pin_rejects_a_persisted_process_control_target(
    tmp_path: Path, target: str
) -> None:
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    session_id = f"process-control-json-{target}"
    pin = state / f"{hashlib.sha256(session_id.encode()).hexdigest()}.json"
    pin.write_text(
        '{"schema":"profile-environment-session.v1",'
        f'"file":"{tmp_path / "profile.env"}",'
        f'"variables":[{{"from_env":"SOURCE","expose_as":"{target}"}}]}}',
        encoding="utf-8",
    )
    pin.chmod(0o600)

    with pytest.raises(AdapterError) as error:
        pin_session_environment(
            _environment(tmp_path / "profile.env"),
            state_directory=state,
            session_id=session_id,
        )

    assert error.value.code == "environment-session-state-invalid"
