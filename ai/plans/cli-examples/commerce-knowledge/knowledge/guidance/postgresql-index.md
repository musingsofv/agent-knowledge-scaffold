---
schema_version: knowledge.v1
kind: guidance
title: Plan PostgreSQL index rollout
description: Check PostgreSQL migration transaction behavior and production index rollout before applying a change.
scope: [group:commerce]
topics: [data-design, reliability]
languages: [any]
technologies: [postgresql]
environments: [any]
---

# Plan PostgreSQL index rollout

Check the migration runner and deployment constraints before choosing how to
create the index. Use the procedure for the selected engine and environment.

## Related Knowledge

- [PostgreSQL index procedure](../runbooks/postgresql-index.md)
