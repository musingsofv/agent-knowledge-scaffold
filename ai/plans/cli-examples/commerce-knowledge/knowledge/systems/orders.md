---
schema_version: knowledge.v1
kind: system
title: Orders service
description: TypeScript orders API, PostgreSQL storage, production consumers and change validation.
scope: [repo:orders-api]
topics: [architecture, reliability, data-design]
entities: [feature:order-history, service:orders]
languages: [typescript]
technologies: [postgresql]
environments: [dev, prod]
---

# Orders service

The TypeScript API stores orders in PostgreSQL. The production checkout UI
and support dashboard consume it. Check the current migrations and query
code before deciding that an additional index is needed.

## Related Knowledge

- [Index procedure](../runbooks/postgresql-index.md#adding-a-status-index)
- [Order-history behavior](../product/workflows/order-history.md)
