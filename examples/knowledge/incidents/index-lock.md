---
schema_version: knowledge.v1
kind: incident
title: Index rollout lock contention
description: Historical locking lesson for future PostgreSQL index changes.
scope: [repo:orders-api]
topics: [reliability, performance]
entities: [service:orders]
technologies: [postgresql]
environments: [prod]
---

# Index rollout lock contention

## Summary

A production index rollout waited on an active transaction and delayed writes.

## Cause

The rollout plan did not check transaction duration or the selected creation mode.

## Lessons

- Verify locking behavior and recovery before scheduling a production index.

## Related Knowledge

- [Index procedure](../runbooks/postgresql-index.md)
