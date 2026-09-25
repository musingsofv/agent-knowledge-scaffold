---
schema_version: knowledge.v1
kind: runbook
title: Orders service runbook
description: Ownership, dependencies and safe checks for the orders service.
scope: [repo:orders-api]
topics: [reliability, architecture]
entities: [service:orders]
languages: [typescript]
technologies: [postgresql]
environments: [dev, prod]
---

# Orders service runbook

## Scope

Describe the service boundary, ownership and runtime surfaces.

## Dependency Map

The API reads and writes PostgreSQL and serves the order-history workflow.

## Operational Checks

- Check service health and current deployment before a change.

## Procedures

- [PostgreSQL index procedure](postgresql-index.md)

## Related Knowledge

- [Orders system](../systems/orders.md)
