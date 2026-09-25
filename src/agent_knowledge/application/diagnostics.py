"""Render validated values and stable diagnostics at the public CLI boundary."""

from dataclasses import dataclass

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.errors import AdapterError


@dataclass(frozen=True)
class Diagnostic:
    """Explain a failure without exposing source bodies or process secrets."""

    code: str
    path: str
    message: str
    remediation: str | None = None


def from_error(error: ValidationError | AdapterError) -> Diagnostic:
    """Attach targeted setup guidance to known configuration and I/O failures."""
    remediation = {
        "profile-settings-unavailable": (
            "Run knowledge-setup to register profiles, or supply --config directly."
        ),
        "default-profile-required": (
            "Choose --profile NAME, or configure default_profile during setup."
        ),
        "unknown-profile": "Use profiles list to discover exact names in the selected registry.",
        "environment-file-unavailable": (
            "Check the selected profile's environment.file path and current-user access."
        ),
        "environment-file-unsafe": (
            "Use a current-user-owned regular file with no symlink traversal."
        ),
        "environment-file-permissions": "Set the environment file mode to 0600 or stricter.",
        "environment-file-too-large": "Keep the external dotenv file within the documented limit.",
        "environment-file-invalid": (
            "Use strict UTF-8 NAME=value lines without duplicates or shell expressions."
        ),
        "environment-variable-missing": (
            "Add the named source assignment to the selected profile's external env file."
        ),
        "configuration-route-mismatch": (
            "Restore the run's original sources/storage before continuing; retain signals."
        ),
        "configuration-required": "Supply --config with the intended knowledge-workspace.yaml.",
        "workspace-mismatch": "Select the configuration for the intended workspace.",
        "unknown-identifier": "Discover valid identifiers with catalog and correct the input.",
        "catalog-conflict": "Reconcile the conflicting definitions in the configured catalogs.",
        "stale-snapshot": "Repeat the original request without continuation to start a fresh page.",
        "file-too-large": "Reduce the input size to the documented limit.",
        "signal-storage-required": "Configure signal_storage with scaffold_root and code_root.",
        "directory-missing": "Create or select the intended directory, then rerun doctor.",
        "file-missing": "Check the supplied configuration, catalog or request file path.",
        "package-metadata-unavailable": "Reinstall the package in the documented environment.",
        "origin-mismatch": "Use the configured origin; keep it distinct from applicability.",
        "project-origin-required": "Use a project config or explicitly include shared signals.",
        "origin-outside-code-root": "Set code_root to the durable checkout's parent tree.",
        "git-unavailable": "Install Git and ensure the launcher process can find it.",
        "origin-unsupported": "Use a standard checkout or linked worktree for project capture.",
        "temporary-signal-scaffold": "Point scaffold_root at the durable primary checkout.",
        "context-changed": "Reload the explicit workspace context before retrying.",
        "signal-publication-uncertain": "Inspect the stored path before retrying; retain inputs.",
        "write-probe-failed": "Check signal-directory permissions and available storage.",
        "broken-reference": (
            "Repair the local Markdown link or label external evidence explicitly."
        ),
        "missing-anchor": "Update the link to an existing heading anchor.",
        "receipt-write-failed": (
            "Search or inspect succeeded; check the optional receipt path separately."
        ),
    }.get(error.code)
    return Diagnostic(error.code, error.path, error.message, remediation)
