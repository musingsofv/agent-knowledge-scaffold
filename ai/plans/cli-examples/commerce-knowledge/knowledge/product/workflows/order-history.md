---
schema_version: knowledge.v1
kind: workflow
title: Browse order history
description: Tenant isolation, ordering and pagination expected when customers browse past orders.
scope: [group:commerce]
topics: [product-behavior, testing]
entities: [feature:order-history, service:orders]
---

# Browse order history

Only the customer's own orders appear. Newest orders appear first; pagination
must not repeat or skip an unchanged order. A new status filter must retain
those properties and explain the empty state.

## Related Knowledge

- [Orders service](../../systems/orders.md)
