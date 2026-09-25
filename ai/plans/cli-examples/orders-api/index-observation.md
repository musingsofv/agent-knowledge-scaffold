---
schema_version: knowledge-signal.v1
id: example-order-status-index
created_at: "2026-09-09T12:00:00Z"
kind_hint: guidance
origin:
  workspace_id: repo:orders-api
  project_path: orders-api
  applicable_scopes: [org:example, group:commerce, repo:orders-api]
  source_ids: [commerce-knowledge]
entities: [service:orders, feature:order-history]
technologies: [postgresql]
evidence:
  - type: file
    reference: repo:orders-api/docs/index-measurements.md
---

# Index rollout guidance needs the migration-runner constraint

In this fictional task, query measurements support the new index but the
migration runner wraps statements in a transaction. The PostgreSQL procedure
should describe how to check that constraint before selecting a creation method.
Review the existing procedure as the potential owner; this observation does
not establish a MySQL or organization-wide requirement.
