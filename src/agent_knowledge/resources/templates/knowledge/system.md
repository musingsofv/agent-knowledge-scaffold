---
schema_version: knowledge.v1
kind: system
title: "<system title>"
description: "<when this system map is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<service-entity-id>"]
languages: ["<language-id>"]
technologies: ["<technology-id>"]
environments: ["<environment-id>"]
aliases: ["<alternate system name>"]
terms: ["<discovery phrase>"]
---

# <System title>

## Responsibility

Describe the component boundary, ownership and runtime responsibility.

## Components and relationships

Describe upstream and downstream components, queues, events and providers.
Use links for navigation and explain runtime relationships in this body with
evidence; a hyperlink alone is not a dependency edge.

## Configuration

Describe non-secret controls that change behavior. Do not copy secret values or
volatile inventories.

## Verification

- State safe checks that establish the system is working.

## Related Knowledge

- [Owning feature](../product/features/<feature-slug>.md)
- [Operational runbook](../runbooks/<runbook-slug>.md)

## Provenance

- Source code, diagram, deployment or observed runtime evidence.
