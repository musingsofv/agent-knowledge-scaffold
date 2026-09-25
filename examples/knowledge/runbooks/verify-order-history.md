---
schema_version: knowledge.v1
kind: runbook
title: Order-history status-filter verification
description: Procedure to check isolation, ordering and pagination after a status-filter change.
scope: [repo:orders-api]
topics: [testing, product-behavior]
entities: [feature:order-history, service:orders]
languages: [typescript]
technologies: [postgresql]
environments: [dev]
---

# Order-history status-filter verification

## Scenario

Verify that adding a status filter preserves tenant isolation and ordering.

## Preconditions

- Use a deterministic fixture with two customers and multiple statuses.

## Steps

1. Request each status page for each customer.
2. Compare ordering and the empty state with the workflow contract.

## Result

Record the observed result and the exact revision tested in the owning repository
or CI run. Preserve failures and fixture conditions alongside the result.

## Evidence

- Link to the test run and sanitized output in the external report.
- Compound only supported durable conclusions into knowledge, retaining their
  evidence citation and applicability.

## Related Knowledge

- [Order-history workflow](../product/workflows/order-history.md)
