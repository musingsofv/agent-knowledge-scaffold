---
name: knowledge-compound
license: 0BSD
description: >
  Process durable knowledge signals into validated updates and dispositions.
  Use for scheduled, delegated or manual compounding. Do not use when
  doing first-time setup; use knowledge-setup. Success means every selected
  signal has a recorded outcome and safe drain decision.
---

# Knowledge compounding

Run this skill manually, from the selected local schedule, or as a delegated
worker requested by the prompt fallback. It is an
agent-driven workflow: the CLI validates explicit values and guards files, and
the agent chooses searches, owners, applicability, publication and when to
stop. There is no hidden search planner, semantic engine, scheduler or
automatic merge.

## Accept delegated work safely

For prompt-triggered compounding, native subagents are the execution interface.
The prompt hook is the scheduling fallback when durable native local scheduling
is unavailable. Delegate, message and reuse workers only through the active
harness's native subagent tools. Never launch a worker as a shell subprocess
running `codex exec`, `claude -p`, `copilot -p` or another model CLI. Shell tools
may run the selected knowledge runtime and repository checks; they do not
replace native delegation. If native subagent tools are unavailable, report
that prerequisite and leave prompt-triggered compounding pending.

A prompt reminder is advisory, not ownership of a run. The parent passes the
exact installed skill and runtime paths, explicit profile/registry or config
selector, originating consumer instructions and verified publication routes, and available
provider/parent-session/worker handles. Keep these separate from each signal's
origin. Omit unknown handles; never invent them or reuse a handle from another
provider. Prompt fallback has no scheduler-provided automation handle: omit
`automation_id` unless an actual scheduling surface exposes one. Never copy the
trigger owner, task name, workspace marker or worker ID into that field.
Preserve an existing signal's separate origin without inventing new provenance.
Keep the parent's ordinary task independent of this work.

Begin the native worker's task with the exact marker
`[agent-knowledge-compound-worker]`. It identifies an already assigned worker
so inherited prompt hooks omit another delegation reminder while preserving
reflection. This marker is role context, not authorization, a lock or evidence
that a run started. Preserve the original parent's handle in the handoff;
the worker's own hook session is not a replacement parent identity.

For a marked Copilot worker, the setup-bound child hook reasserts the exact
runtime, selector and installed skill. It exposes the child hook session as
`worker_id` and `session_id`, using the supported binding's verified mapping
to the native `agentId`. Keep `parent_session_id` from the explicit parent
handoff; never derive it from the child hook. This bound context grants no
authorization or run ownership. A missing or conflicting setup binding or
required handoff is a visible prerequisite: report it and do not substitute a
default or different profile. The hook does not supply the consumer instructions
or publication context required in the parent handoff above.

Load this skill in the worker. Do not delegate another opportunistic compound
worker or act on inherited reminders recursively. Reuse an existing worker
through the provider's supported mechanism when it is still available; a
stored ID does not prove that it can resume after the session ends. Record
`worker_id` and `parent_session_id` on the start request when exposed, alongside
`harness` and the worker's exact `session_id`. A provider may expose the native
worker handle only to the parent after delegation. The parent should pass it
through the provider's supported worker-message mechanism when available. Do
not wait indefinitely before starting, invent a handle or infer it from a local
filename when the provider has not exposed it.

When the exact native worker ID becomes available after start, the parent or
worker associates it with the exact returned run ID through the selected CLI's
metadata-only `record-worker` action. This also works after finish; do not rerun
compounding just to fill provenance. For example, replace these illustrative
handles only with provider-exposed values:

~~~yaml
action: record-worker
run_id: compound-returned-run-id
worker_id: exact-exposed-subagent-handle
parent_session_id: exact-exposed-parent-handle
harness: codex
~~~

Only `run_id` and `worker_id` are required. Optional parent/provider fields must
agree with already recorded values; omit unavailable ones. Repeating the same
identity is idempotent; a conflict needs inspection, not replacement with another
handle. The CLI records the association in the existing activity log and run
evidence without changing completion, ownership, publication or drain decisions.
The worker reports its returned run ID to the parent, which retains it alongside
the native delegation result. A later provider-exposed ID can then be attached
without guessing which run it belongs to.

Run the readiness, activity and complete signal inventory steps below. Before
editing any owner, publishing, draining or finalizing a run, call compound
`start` with `automatic: true` and the selected snapshots. It atomically
rechecks the configured trigger and due state under the shared lifecycle lock.
If it returns `started: false`, exit quietly without touching the winning run;
this includes a stale reminder whose earlier worker has already finished.
Redundant worker spawns are acceptable. Never replace this guard with a
handwritten timestamp, pre-spawn reservation or elapsed-time takeover.

If activity identifies this exact worker's already started run, inspect its
archives, dispositions and publication/drain evidence before continuing that
run. A foreign, interrupted or ambiguous active run is not permission to start
another one. Resolve the actual worker and evidence, then finish or continue
that recorded run truthfully before a new attempt. If a recovered attempt uses
a different worker, retain the earlier run identity with `recovery_of` on the
new start, after resolving the earlier active run. Do not fabricate resumability
or finish another live worker's run merely to clear the guard.

After a successful start, the rest of this skill applies unchanged: discover
actual owners, isolate edits, run native checks, verify remote publication and
use guarded drainage. Background execution grants no additional policy or
merge permission. Report meaningful results, ready-for-review PR links and
required owner actions to the parent; a duplicate or empty run stays quiet.

## Start from the originating workspace

Use the exact profile and absolute registry carried by the task/reminder, or its
explicit configuration path. Run `describe` and follow the installed guide's
session-selection procedure before configured work. Confirm `context`/`doctor`
and keep that selector on every call, including `--compound-run-id` calls.
Do not substitute the current global default or the base file alone: either
would discard the selected overrides. Direct-path examples below also accept
`--settings /absolute/profiles.yaml --profile work` in place of `--config PATH`.
Run doctor's explicit write-mode probe and check its separate read and
signal/receipt write readiness before mutating compounding state. An overall doctor failure caused only by unrelated
profile-environment diagnostics does not prevent local compounding. Keep those
diagnostics visible, and require the credentials actually needed for each
operation; unavailable publication authentication retains the affected inputs.
Do not bypass the selected profile or borrow unrelated ambient credentials to
make readiness appear complete.
Run the configured absolute launcher from the same harness process:

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml context
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml doctor \
  --request-file - <<'YAML'
mode: write
YAML
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml compound \
  --request-file - <<'YAML'
action: status
YAML
~~~

Read the activity result before doing any work. If an active run is recorded,
inspect it and report the interrupted/ambiguous state; do not treat elapsed
time as a lock takeover and do not start a second drain. For a new run, list
signals first and snapshot every selected id, absolute path and complete-byte
fingerprint. Preserve the signal's workspace, project, configured scopes,
source IDs, harness, session ID and automation ID as provenance. Origin tells
where an observation came from; it does not grant the resulting document the
same applicability.

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml signal list \
  --request-file - <<'YAML'
include_shared: true
limit: 100
YAML
~~~

Omit `session_id` for this initial inventory so it includes pending observations
from all authoring sessions in the configured project/shared buckets. Follow
continuations with the same request until the inventory is complete. A session
filter is useful only for an explicitly targeted investigation of a selected
signal. The compounding run's own session ID does not identify the earlier
authoring sessions. Read selected bodies with ordinary file tools; the CLI
returns previews and compounding decides the final disposition.

If the originating project/configuration cannot be resolved, retain that
signal and report the missing context. Never substitute the compounding
checkout's scopes or source roots. A safe originating session may be resumed
through the harness when supported; if it is absent, unavailable or belongs to
another provider, continue self-contained from the signal body and evidence.
Do not copy a transcript into canonical knowledge.

Call compound start with the workspace ID, selected snapshots, harness and
opaque provider handles for this compounding run. Delegated prompt-triggered workers
add `automatic: true` plus the available worker fields described above; manual
and native-scheduled runs use the normal explicit start. The tool supplies the UTC
timestamp and archives each selected input before recording the run:

~~~yaml
action: start
workspace_id: workspace:example
harness: codex
session_id: opaque-session-id
selected:
  - id: index-observation
    path: /work/knowledge/ai/signals/projects/orders/20260910T090000Z-one.md
    fingerprint: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
~~~

Use that object as the compound start request. Native scheduled runs may also
include their exact provider-exposed `automation_id`; this example does not
supply one. Prompt-triggered workers must not manufacture an automation handle.
The returned run_id is required
for drain and finish. The tool owns immutable signal archives, receipts and
pre-removal intent; never create these manually or move/delete inbox inputs.
Archival is mandatory even when optional diagnostic collection is disabled.

For catalog/search/inspect and validate calls during this run, pass global
`--compound-run-id <returned-run-id>` before the command. It resolves this
workspace's recorded harness/session defaults. Outside a run, use `--harness`
and `--session-id` with the exact hook handle when available; unknown context
stays absent. The shared guide owns usage and export semantics.

## Discover and decide

Run `agent-knowledge describe` and read its installed guide for catalog/filter,
reflection and link-navigation semantics. Before choosing a destination, follow
[owner-discovery.md](references/owner-discovery.md) to inventory relevant skills
and active instruction sources alongside knowledge, then choose the smallest
sufficient owner using its skill-only, knowledge-only or combined decision rules.
Reuse the inventory across the batch; refresh it when available sources change.
Names and descriptions are
candidates, not confirmed owners. Record unavailable originating skill or
instruction coverage explicitly and retain unresolved updates when their
source or publication route is unavailable.

Read each selected signal body with ordinary file tools after its metadata
preview. Resolve unfamiliar terms through the configured catalog:

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml catalog \
  --request-file - <<'YAML'
dimension: technologies
text:
  any: [postgres, relational database]
limit: 20
YAML
~~~

Reuse registered scope, entity, topic, language, technology and
technology-family identifiers. Search existing owners with text first and
canonical filters second. Search plausible kinds when the advisory kind hint
is not enough:

~~~yaml
kind: [feature, workflow, system, guidance, runbook, limitation]
scope: [org:example, group:commerce, repo:orders-api]
topics: [technology-choice, provisioning, data-design]
entities: [service:orders]
technologies: [postgresql, family:relational-database, any]
text:
  any: [secondary index, order history]
limit: 20
~~~

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml search \
  --request-file /work/knowledge/search.yaml
~~~

Use the installed guide's deterministic filter semantics. Inspect selected
previews before reading bodies, then use ordinary grep or line-range reads.
Do not claim that a narrow search or successful validation proves semantic
completeness.

When a finding has a concrete relationship to another owner, add an informative
Markdown link near the relevant claim or prerequisite. Use incoming discovery
for reverse navigation. Before moving, retiring or materially changing an owner,
follow the guide's "Follow relationships and check dependants" procedure:
inspect affected incoming sections, check catalog entity `documents` references
separately, and validate repairs in the same publication state. An incomplete
scan does not prove that no dependants exist. Preserve each owner's independent
applicability and report unresolved impact.

Assign canonical applicability from evidence. A repository-origin observation
does not become organization-wide policy automatically. Use technologies:

- any for technology-independent guidance;
- one or more concrete IDs when the claim is supported for those engines;
- family:<id> only when the evidence supports the family-level claim.

Catalog family membership alone is not family-wide evidence. Split a general
principle from a vendor-specific procedure when they are independently useful;
otherwise keep the narrower owner and explain the limitation. If a required
identifier is genuinely absent, propose a catalog addition with evidence rather
than inventing an ID. Keep any catalog edit in the same validated publication
state as its owner.

The catalog YAML registers vocabulary, descriptions, aliases and relations.
The workspace YAML selects sources, membership, paths and runtime/publication
settings. Profile registry overrides are local policy: inspect context field
origins before proposing base edits. Compounding maintains knowledge/catalog
content; it does not rewrite labels, defaults, sources or storage to make a
query match. Routing changes during a run require restoring the original
selection; retain signals until resolved. A new marketing procedure ordinarily changes a document and possibly
the catalog, not workspace settings. Discover and reuse an existing
`lead-generation` topic or equivalent before proposing a narrowly defined new
one. Publish a supported registration with its validated document. Signals do
not require topics, so an unclear concept can remain captured while awaiting
clarification. New sources, membership changes and wider applicability require
a deliberate configuration decision; never broaden them to make a result match.
Setup establishes initial vocabulary; compounding maintains supported additions.

When an adopted business choice changes, update the existing owner and current
procedure, preserving consequential earlier rationale in clearly labelled
history. Distinguish trials and proposals from adoption; do not infer business
dates from commits or invent missing motives. Create another document only for
an independently useful purpose or different applicability, and explain that
choice in the disposition. For a worked example and current-versus-historical
retrieval, read [business-decisions.md](references/business-decisions.md).

Keep routine verification reports in their owning repository, CI run or evidence
system. Extract only supported durable conclusions: constraints into limitations,
approaches or requirements into guidance, repeatable steps into runbooks. Cite
the original report and retain the conditions under which its finding holds;
do not replace the report or generalize a one-time result into universal truth.

When creating or updating guidance, follow "Author canonical knowledge" in the
installed guide and read [guidance-authoring.md](references/guidance-authoring.md)
for contrasting examples. Consider short checks for supported organisational
expectations, consequential constraints and recurring omissions. A single
successful approach does not establish a general requirement. Prose, a discovery
repair or no update can be the right outcome; no special justification for prose
is needed.

Update the existing owner, consolidating overlapping checks and retiring obsolete
ones when supported. If the expectation already exists, investigate discovery,
wording, applicability or the skill's procedure rather than adding another rule.
An already-covered observation needs no edit. Do not expand individual guidance
merely to repeat the installed guide's shared execution or reporting conventions.
Preserve requirement strength, rationale, exceptions and supported scope; a
task-specific exemption is not automatically permanent. Keep canonical boxes
unticked and task-specific assessments in the task response or review.

Before publishing knowledge changes, validate selected or changed documents.
Skill/instruction changes use their owning repository's native checks as
described in owner discovery:

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml validate \
  --request-file - <<'YAML'
documents:
  - source: example-knowledge
    path: guidance/indexing.md
YAML
~~~

Search and inspect the effective publication state, including the configured base and
the eligible current-user knowledge PR. Do not assume a signal's advisory kind
is its final owner. Record a concrete disposition and evidence for every
selected signal: update an existing owner, create a validated new owner,
delete-retire an obsolete owner, keep an already-covered observation, skip an
out-of-scope observation, or defer an unresolved one. A no-update disposition
still states which owner/evidence covered it.

## Publish and drain safely

For a configured publication source, verify the authenticated Git identity,
remote and base branch before changing files. Reuse an explicitly selected
eligible PR by the current user. Otherwise reuse the current user's most
recently updated eligible PR whose branch starts with the configured prefix.
If none exists, prepare an isolated branch from the current configured base and create a PR
only after validated central changes exist. Never append to another author's
PR, an unrelated code PR, or an empty PR. Merge the current configured base normally, resolve
ordinary conflicts without force-push, validate and push the intended commit,
then verify the remote commit and PR head. A human merges or closes the PR.

For skill/instruction updates, follow
[standing consumer PR authorization](references/owner-discovery.md#standing-authorization-for-consumer-prs)
and the authoring repository's publication route. Participating consumers are
authorized for compounding PRs; do not add another approval gate before opening
one. A skill-only update needs no central PR. Report published PRs as ready for
human review; review is not a blocked compounding run.
If a required update has no available publication route, defer it with an
actionable proposal and retain the signal. Record a no-write disposition only
when evaluation establishes that no change is needed or the finding is out of
scope. Do not pretend a local commit is remote publication.

After verified publication, or after a confirmed no-write disposition, drain
only selected unchanged inputs. Include every selected disposition in the
request:

~~~bash
agent-knowledge --config /work/knowledge/knowledge-workspace.yaml compound \
  --request-file - <<'YAML'
action: drain
run_id: compound-opaque-run-id
selected:
  - id: index-observation
    path: /work/knowledge/ai/signals/projects/orders/20260910T090000Z-one.md
    fingerprint: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
dispositions:
  - signal_id: index-observation
    decision: keep
    rationale: The existing indexing guidance already covers this observation.
    owners:
      - source: example-knowledge
        path: guidance/indexing.md
publication_verified: false
YAML
~~~

Dispositions identify actual knowledge owners with `{source, path}`. Skill or
instruction owners use `{repository, path, package?}` for the resolved authoring
source, never an installed projection. If ownership cannot be resolved, supply
`owner_unavailable_reason` and retain the actionable update. An owner reference
is a candidate until resolved; it does not establish publication.

For write decisions, include `publication` with the reported status and available
repository, pull_request and commit evidence. If capturing a patch, give the
actual checkout plus before_revision and after_revision delimiting this run's
changes, or an unavailable_reason. Do not attribute a whole pre-existing PR to
this run. The tool records assertions as agent-reported and captures a patch
only when the declared revisions can be safely read.

For update, create or delete-retire decisions set publication_verified true
only after remote verification, with publication status `published`, the
repository, and a commit or pull_request reference. Keep, skip and explicit no-write outcomes may
drain with a stated rationale. The tool binds drain to the recorded snapshots,
persists dispositions and intent, verifies archived bytes, then rechecks inbox
containment, file identity and complete bytes immediately before unlinking.
Missing archives or failed durable writes retain inputs. Changed, new, missing,
malformed, symlinked or uncertain inputs remain in the inbox. Partial cleanup
is reported; never recreate a removed signal merely to make a count match.

Finish every started run with its agent-reported outcome, dispositions and a
truthful structured `completion` value. Free-form `outcome` text alone never
establishes automatic completion:

- `completed`: every selected signal has a supported disposition, including
  confirmed no-update cases. Retention is still possible for edited/new inputs.
- `deferred`: every selected signal has a disposition, but a prerequisite or
  unresolved owner means some work remains. State the concrete reason.
- `failed`: this attempt could not complete its evaluation; preserve unfinished
  work and report the next inspection. It has a bounded retry delay.
- `empty`: complete discovery found no eligible work and no selected inputs.
  It does not postpone consideration of later-arriving signals. Malformed or
  unresolved candidates are not proof of emptiness; report them with `failed`
  or fully dispositioned `deferred` instead of causing a fresh worker per prompt.

For prompt fallback, `completed` and `deferred` wait the configured interval
(default rolling 24 hours); `failed` waits the retry interval (default one
hour). A failure does not shorten an earlier completion interval; wait until
both applicable deadlines have passed. A later completed/deferred run supersedes
earlier failed attempts. Reminder delivery or worker creation does not start
either interval.
An unfinished active run remains active until evidence-based recovery; no timer
clears it. Do not label failed or interrupted work `empty` to evade the guard.
Do not submit drained counts: the tool derives them from recorded drain results:

~~~yaml
action: finish
run_id: compound-opaque-run-id
outcome: published
completion: completed
dispositions:
  - signal_id: index-observation
    decision: update
    rationale: Updated the existing procedure with the measured index warning.
    owners:
      - source: example-knowledge
        path: runbooks/indexing.md
~~~

If the agent is interrupted, publication or cleanup is uncertain, or an
activity log is malformed, leave inputs and activity evidence intact and
report the exact next inspection. A subsequent run must inspect the confirmed
PR/commit and current fingerprints before retrying. Never force-push, merge a
PR automatically, delete a signal on an unverified response, or silently
convert a failed run into success.
