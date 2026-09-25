---
schema_version: knowledge.v1
kind: runbook
title: "<service runbook title>"
description: "<when this service runbook is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<service-entity-id>"]
languages: ["<language-id>"]
technologies: ["<technology-id>"]
environments: ["<environment-id>"]
aliases: ["<alternate service name>"]
terms: ["<discovery phrase>"]
---

# <Service runbook title>

## Scope

Describe the service responsibility, ownership boundary and runtime surfaces.

## Dependency Map

List upstream and downstream services, integrations, queues, events and external
providers. Link to the owning system document where appropriate.

## Configuration

Describe non-secret settings that materially change behavior and where to inspect
their current source of truth.

## Operational Checks

- Health, logs, deployment and verification checks.

## Procedures

- [Procedure name](<procedure-path>.md)

## Related Knowledge

- [System context](../systems/<system-slug>.md)
- [Feature behavior](../product/features/<feature-slug>.md)

## Provenance

- Source evidence, deploy check, incident or owner.
