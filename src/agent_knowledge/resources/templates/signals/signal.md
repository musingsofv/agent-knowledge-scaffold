---
schema_version: knowledge-signal.v1
id: "<stable-signal-id>"
created_at: "<2026-01-01T00:00:00Z>"
kind_hint: guidance
origin:
  workspace_id: "<workspace-id>"
  project_path: null
  applicable_scopes: ["<scope-id>"]
  source_ids: ["<source-id>"]
  # Manual/non-harness signals may omit harness and session_id.
  # When harness is present, session_id is required: copy the exact hook value.
  # Use opaque provider handles only, never credentials or invented placeholders.
  harness: "<codex|claude|copilot>"
  session_id: "<opaque-session-id>"
  # Independently optional; automation_id cannot replace session_id.
  automation_id: "<opaque-automation-id>"
entities: ["<entity-id>"]
technologies: ["<technology-id>"]
evidence:
  - type: file
    reference: "<safe evidence reference>"
---

# <Durable observation title>

Describe the reusable observation and the evidence that supports it. Keep the
claim in the Markdown body; do not duplicate the full claim in frontmatter.
