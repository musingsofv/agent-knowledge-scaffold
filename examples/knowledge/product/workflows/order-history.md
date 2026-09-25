---
schema_version: knowledge.v1
kind: workflow
title: Browse order history
description: Tenant isolation, ordering and pagination expected for past orders.
scope: [group:commerce]
topics: [product-behavior, testing]
entities: [feature:order-history, service:orders]
---

# Browse order history

Only the customer's own orders appear. Newest orders appear first; pagination
must not repeat or skip an unchanged order.

## Preconditions

- The customer is authenticated and belongs to the expected scope.

## Related Knowledge

- [Order history feature](../features/order-history.md)
- [Orders service](../../systems/orders.md)
