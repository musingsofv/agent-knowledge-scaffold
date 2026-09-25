---
schema_version: knowledge.v1
kind: guidance
title: "<behavior-first guidance title>"
description: "<when this approach or requirement is useful>"
scope: ["<scope-id>"]
topics: ["<topic-id>"]
entities: ["<entity-id>"]
languages: [any]
technologies: [any]
environments: [any]
aliases: ["<alternate discovery phrase>"]
terms: ["<discovery phrase>"]
---

# <Behavior-first guidance title>

## Approach and requirements

State the behavior, constraints or standards to follow and why they matter.
Make mandatory requirements explicit; guidance does not make them optional.

## Applies when

Describe the task or change surface that should cause an agent to search this
guidance. Replace `[any]` with registered applicability where restricted.
Keep task-stage guidance here as prose rather than inventing an activity
facet.

## Guidance

- Describe the approach, rationale and trade-offs in the form that communicates
  them best. Prose is valid without a special justification.
- Keep executable steps in a linked runbook and participants/stages in a workflow.
- Keep vendor-specific instructions in a narrower document or linked procedure.

## Review checks (optional)

Keep this section when short checks make supported expectations easier to apply
or verify; otherwise remove it. State when each check applies and what should be
true, with useful evidence where appropriate. Preserve recommendation versus
requirement wording and keep rationale and supported exceptions nearby. Reference
existing automated checks instead of copying their rules. Keep these canonical
boxes unticked; task-specific outcomes belong in the task response or review.

- [ ] <When applicable, the supported expectation; useful evidence or exception.>

## Verification

- Identify useful evidence or existing checks, without duplicating the review
  items or creating unnecessary verification work. State verification limits.

## Limitations

- Describe a known boundary, exception or unresolved trade-off when one exists.

## Decision history (optional)

Keep this section only when consequential prior choices and their rationale help
future decisions. State the current adopted choice above; label historical
choices, experiments and proposals explicitly. Record dates only when known,
retain evidence and trade-offs, and name conditions for reconsidering. A Git
commit date does not establish the effective business date. Link the current
procedure instead of copying obsolete steps into active guidance.

## Related Knowledge

- [Relevant procedure](../runbooks/<procedure-slug>.md)

## Provenance

- Source evidence, review, decision or owner.
