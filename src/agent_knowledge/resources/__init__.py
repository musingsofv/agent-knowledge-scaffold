"""Locate the neutral authoring resources shipped with the CLI."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent


def guide_path() -> Path:
    """Return the installed guide, falling back to the source-owned copy."""
    installed = _ROOT / "agent-contract.md"
    if installed.exists():
        return installed
    for parent in _ROOT.parents:
        candidate = parent / "docs" / "agent-contract.md"
        if candidate.exists():
            return candidate
    return installed


def template_paths() -> tuple[Path, ...]:
    """Return all shipped Markdown templates in deterministic path order."""
    return tuple(sorted(_ROOT.joinpath("templates").rglob("*.md")))


__all__ = ["guide_path", "template_paths"]
