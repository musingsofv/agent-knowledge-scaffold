---
schema_version: knowledge.v1
kind: runbook
title: PostgreSQL index procedure
description: Prerequisites, rollout checks and verification for a status index on order history.
scope: [repo:orders-api]
topics: [performance, data-design, reliability]
entities: [feature:order-history, service:orders]
technologies: [postgresql]
environments: [dev, prod]
---

# PostgreSQL index procedure

## Prerequisites

Confirm the current schema, migration runner and PostgreSQL version. Measure
the target query on representative data. Agree rollout and recovery with the
service owner before changing production. This example is not executable DDL.

## Adding a status index

Read [Prerequisites](#prerequisites) before using this procedure.
Check the existing indexes and the query's tenant, status and ordering clauses.
Choose an index based on the measured access pattern. Verify the migration's
transaction and locking behavior for the chosen creation method.

### Verification

Compare query plans and latency before and after; verify ordering, pagination
and tenant isolation. Observe write latency and storage impact as well.

## Recovery

Use the agreed recovery procedure for the actual deployed migration and
index state. Recheck behavior and record the outcome.

## Related Knowledge

- [Index design principle](../guidance/index-cost.md)
- [Orders service](../systems/orders.md)
