---
schema_version: knowledge-signal.v1
id: example-index-observation
created_at: "2026-01-15T12:00:00Z"
kind_hint: guidance
origin:
  workspace_id: workspace:orders-api
  project_path: null
  applicable_scopes: [org:example, group:commerce, repo:orders-api]
  source_ids: [example-knowledge]
entities: [service:orders]
technologies: [postgresql]
evidence:
  - type: file
    reference: docs/index-measurements.md
---

# Index maintenance cost was missing from the guidance

Measurements should be recorded before an index rule is broadened. This
observation does not by itself justify organization-wide or family-wide policy.
