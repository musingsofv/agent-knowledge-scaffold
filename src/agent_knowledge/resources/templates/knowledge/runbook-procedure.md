---
schema_version: knowledge.v1
kind: runbook
title: "<procedure runbook title>"
description: "<when this operational procedure is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<entity-id>"] # Optional: include only relevant registered entities.
technologies: ["<technology-id>"]
environments: ["<environment-id>"]
aliases: ["<alternate procedure name>"]
terms: ["<discovery phrase>"]
---

# <Procedure runbook title>

## Purpose

Describe when to run this procedure and what outcome it proves or repairs.

## Preconditions

- Required access, environment, credentials, branch or current state.

## Steps

1. Complete the first bounded step.
2. Complete the next step and record the relevant evidence.

## Verification

- State the command, observation or check that establishes success.

## Recovery

- Describe the safe inverse or link to the recovery owner.

## Related Knowledge

- [Service runbook](../<service-runbook-path>.md)
- [System context](../systems/<system-slug>.md)

## Provenance

- Source evidence, change record, incident or QA reference.
