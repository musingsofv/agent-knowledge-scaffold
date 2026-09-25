---
schema_version: knowledge.v1
kind: runbook
title: PostgreSQL index procedure
description: Prerequisites, rollout checks and recovery for a status index.
scope: [repo:orders-api]
topics: [performance, data-design, reliability]
entities: [feature:order-history, service:orders]
technologies: [postgresql]
environments: [dev, prod]
---

# PostgreSQL index procedure

## Purpose

Use this procedure when a measured order-history query may need an index.

## Preconditions

Confirm the current schema, migration runner and PostgreSQL version. Measure
the target query on representative data and agree recovery with the owner.

## Steps

1. Inspect existing indexes and the query's tenant, status and ordering clauses.
2. Choose an index from the measured access pattern.
3. Verify migration transaction and locking behavior.

## Verification

- Compare query plans and latency before and after the change.

## Recovery

- Use the agreed recovery procedure for the deployed migration and index state.

## Related Knowledge

- [Index principle](../guidance/testing.md)
- [Orders service](../systems/orders.md)
