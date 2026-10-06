"""Reject observable model-CLI launches inside agent shell tool commands."""

import re
import shlex
from pathlib import PurePath


def _without_heredoc_bodies(command: str) -> str:
    lines, pending = [], []
    for line in command.splitlines():
        if pending:
            if line.lstrip("\t") == pending[0]:
                pending.pop(0)
            continue
        lines.append(line)
        pending.extend(
            match[1] for match in re.findall(r"<<-?\s*(['\"]?)([A-Za-z_][\w-]*)\1", line)
        )
    return "\n".join(lines)


def reject_model_shell_launch(command: str, *, _depth: int = 0) -> None:
    """Check executable positions, not strings printed or read as documentation."""
    if _depth > 5:
        raise ValueError("Shell wrapper depth exceeds observable model-launch verification.")
    lexer = shlex.shlex(_without_heredoc_bodies(command), posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return  # Unrecognized shell syntax is not invented launch evidence.
    segments, current = [], []
    for token in tokens:
        if token and all(character in ";&|()\n" for character in token):
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    for words in segments:
        while words and (
            words[0] in {"then", "do", "exec", "command", "nohup"}
            or re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*=.*", words[0])
        ):
            words = words[1:]
        if not words:
            continue
        program = PurePath(words[0]).name
        if program == "env":
            words = words[1:]
            while words and (words[0].startswith("-") or "=" in words[0]):
                words = words[2:] if words[0] in {"-u", "--unset", "-C", "--chdir"} else words[1:]
            if not words:
                continue
            program = PurePath(words[0]).name
        if program in {"bash", "zsh", "sh", "dash"}:
            for index, word in enumerate(words[1:], 1):
                if word.startswith("-") and "c" in word and index + 1 < len(words):
                    reject_model_shell_launch(words[index + 1], _depth=_depth + 1)
                    break
        if program in {"codex", "claude", "copilot"} and words[1:] not in (
            ["--version"],
            ["--help"],
            ["-h"],
        ):
            raise ValueError(
                "Agent shell command launches a model CLI; native subagent tools are required."
            )
