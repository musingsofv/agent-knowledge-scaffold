---
schema_version: knowledge.v1
kind: workflow
title: "<workflow title>"
description: "<when this behavior and acceptance contract is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<entity-id>"] # Optional: include only relevant registered entities.
aliases: ["<alternate workflow name>"]
terms: ["<discovery phrase>"]
---

# <Workflow title>

## Goal

Describe the actor, intended outcome and success condition.

## Preconditions

- Access, state or configuration that must already hold.

## Flow

1. Describe the first observable step.
2. Describe the next state and the expected outcome.

## Failure modes

- Describe user-visible or operational failure behavior and its owner.

## Related Knowledge

- [Feature owner](../features/<feature-slug>.md)
- [System context](../../systems/<system-slug>.md)

## Provenance

- Product evidence, acceptance test or source reference.
