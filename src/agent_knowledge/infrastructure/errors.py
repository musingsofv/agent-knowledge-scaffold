"""Report external-state failures without disguising them as empty results."""

from dataclasses import dataclass


@dataclass
class AdapterError(Exception):
    """Carry a stable external-state diagnostic and CLI exit category."""

    code: str
    path: str
    message: str
    exit_code: int = 3

    def __str__(self) -> str:
        """Render a concise diagnostic without external-state payloads."""
        return f"{self.path}: {self.message}" if self.path else self.message
