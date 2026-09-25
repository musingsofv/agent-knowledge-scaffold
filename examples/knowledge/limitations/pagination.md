---
schema_version: knowledge.v1
kind: limitation
title: Unchanged pagination is required for reliable order history
description: Known boundary to preserve when adding order-history filters.
scope: [repo:orders-api]
topics: [reliability, product-behavior]
entities: [feature:order-history]
languages: [typescript]
technologies: [postgresql]
environments: [prod]
---

# Unchanged pagination is required for reliable order history

## Constraint

Pagination is only comparable while the underlying order set is unchanged.

## Impact

Concurrent inserts can change page boundaries during a customer session.

## Workaround

- Use the workflow's stable cursor contract and explain refresh behavior.
