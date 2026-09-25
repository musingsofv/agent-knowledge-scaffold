---
schema_version: knowledge.v1
kind: system
title: Orders service
description: TypeScript orders API and PostgreSQL storage used by order history.
scope: [repo:orders-api]
topics: [architecture, data-design, reliability]
entities: [service:orders, feature:order-history]
languages: [typescript]
technologies: [postgresql]
environments: [dev, prod]
---

# Orders service

The TypeScript API stores orders in PostgreSQL. The production checkout UI and
support dashboard consume it. Runtime relationships described here need source
evidence; a hyperlink alone is not a dependency edge.

## Related Knowledge

- [Order-history behavior](../product/workflows/order-history.md)
- [Service runbook](../runbooks/orders.md)
