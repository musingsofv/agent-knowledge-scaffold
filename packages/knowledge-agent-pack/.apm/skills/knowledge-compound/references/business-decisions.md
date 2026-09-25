# Preserve useful business decisions

Use this when a signal changes an adopted business approach or explains why a
prior approach was replaced. Update the existing claim owner, retain consequential
reasoning and link the current procedure. Keep routine document-edit history in
Git when available. Neither Git timestamps nor a recent experiment establishes
an adoption date.

The following is a fictional example, not a scaffold default or evidence about
its user's business. Its tool names occur in the prose to explain the decision;
this business-choice guidance applies independently of a document's technology.
A vendor-specific operational runbook should carry its own supported narrower
applicability using registered IDs.

## Existing guidance after confirmed adoption

```markdown
---
schema_version: knowledge.v1
kind: guidance
title: Choose the current lead-generation approach
description: Current outreach approach, why prior tools were replaced, and when to reconsider.
scope: [org:studio]
topics: [lead-generation]
languages: [any]
technologies: [any]
environments: [any]
---

# Choose the current lead-generation approach

## Current approach

Use Apollo for the next outreach campaign. The adopted choice supports the
required qualification-to-outreach handoff with less manual reconciliation in
our evaluation. Follow the [current campaign procedure](../runbooks/campaign.md).
Reconsider if that handoff no longer preserves qualification evidence or our
required export workflow changes.

## Decision history

We previously used Pipedrive. It supported our early manual follow-up, but the
later campaign workflow required repeated reconciliation between qualification
and outreach. The evaluation recorded this as the reason to reconsider.

Solution X was an experiment, not an adopted replacement. Its trial left the
same handoff unresolved. The subsequent Apollo evaluation supported the required
handoff, and the owner confirmed adoption. The effective dates were not recorded.

These choices explain the current approach; historical tools are not current
operating instructions. Evidence: the owner-approved evaluation and adoption
notes retained with this fictional example.
```

A real publication cites the accessible decision/evaluation records. The example
is not permission to fabricate those records, the dates or the claimed reasons.
If only the Solution X trial signal exists, retain Pipedrive as the current
choice and label the trial accordingly. Change the current choice and procedure
only after evidence of Apollo adoption. Do not create a parallel guidance file
for each observation, or copy obsolete procedures into active steps.

## Two retrieval intentions

To run a campaign, discover `lead-generation` in the catalog, search guidance and
runbooks with that topic, inspect their previews, and read the current approach
and linked procedure. The description and headings distinguish current actions
from history; the matching tool does not infer that distinction.

To answer "Why did we leave Pipedrive?", search the same topic with text
`Pipedrive`, inspect the selected guidance and read its `Decision history`
section. Use that rationale to assess alternatives without treating its obsolete
steps as instructions. Both intentions can select the same file and different
line ranges. No temporal fields, separate history kind or as-of query is needed.
