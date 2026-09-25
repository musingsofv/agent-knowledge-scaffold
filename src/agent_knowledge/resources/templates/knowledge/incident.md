---
schema_version: knowledge.v1
kind: incident
title: "<incident title>"
description: "<when this historical incident and lesson is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<entity-id>"] # Optional: include only relevant registered entities.
technologies: ["<technology-id>"]
environments: ["<environment-id>"]
aliases: ["<alternate incident name>"]
terms: ["<discovery phrase>"]
---

# <Incident title>

## Summary

State the observed impact and the affected system or workflow.

## Timeline

- Record only durable milestones and link to evidence where appropriate.

## Cause

Describe the deepest supported cause and distinguish hypotheses from facts.

## Recovery

Describe the action that restored normal operation and link to the reusable procedure.

## Lessons

- Record durable prevention or detection guidance in the owning guidance or runbook.

## Related Knowledge

- [Affected system](../systems/<system-slug>.md)
- [Relevant limitation](limitation-slug.md)

## Provenance

- Incident record, logs, deployment or QA evidence.
