---
description: Use the installed agent-knowledge CLI for explicit workspace discovery.
---

# Agent knowledge discovery

Owner: `knowledge-agent-pack`. Authored source:
`.apm/instructions/agent-knowledge-discovery.instructions.md` within that package.
Resolve its owning checkout through package installation metadata before editing;
this installed or compiled copy is a projection, not the authoring source.

## Locate the installed contract

Use the installed `agent-knowledge` command for knowledge relevant to the task.
Confirm it with `command -v agent-knowledge`. If missing, use `knowledge-setup`;
do not call a repository-relative Python module or copied package path.
Run `agent-knowledge describe` and use its installed guide and template paths.
Follow the installed guide to select a named profile or explicit workspace;
`doctor` and `context` establish its readiness and configured sources. Retain
that selection on every call, including reflection and after resume. Never infer
configuration from the current directory or ambient organization variables.

When the selected profile declares an external environment, treat its `context`
metadata as names and routing only. Never print, copy into a prompt or persist
the file's values. A harness session activates at most one credential profile;
using another `--profile` changes knowledge routing only. Start a new session to
activate another credential profile and keep scheduled work pinned to one name.

## Discover before reading

Follow the installed guide's discovery and progressive-reading procedure.
The command owns matching, schema and path validation. The agent chooses queries,
relevance, selected body reads and when to stop. Validate proposed knowledge
changes before publication.

Use "Apply guidance and report review results" in the installed guide when
applying discovered expectations and reporting material outcomes.

## Reflect through the shared guide

Follow "Reflect and record useful observations" in the installed guide for
durable discoveries, corrections and gaps. Use the exact hook session handle
for signal provenance and same-session duplicate checks. Record nothing when
there is no useful observation. `knowledge-compound` owns final owner evaluation
and publication; do not duplicate either procedure in compiled instructions.
