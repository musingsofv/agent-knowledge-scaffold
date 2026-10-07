# Agent knowledge contract

This guide describes the file-backed knowledge interface shipped with the
`agent-knowledge` command. It is intentionally organization-neutral. A
workspace supplies its own catalog, scopes, sources and knowledge files; the
command never guesses those values from the current directory or from an
environment variable.

## Start with the running installation

Run these commands from the same harness that will use the result:

```bash
agent-knowledge describe
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml doctor
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml context
```

`describe` needs no configuration. It reports the supported schemas, the eight
knowledge kinds, filter semantics, resource locations and the available
commands. `doctor` checks this process's interpreter, launcher, explicit
configuration, catalog and source roots. Its default is read-only and does not
scan document bodies or create a signal-storage probe. Use
`{"mode":"write"}` only when signal capture is about to be used. A terminal
doctor result describes that invocation; it does not prove that another GUI or
compiled harness sees the same executable and configuration.

Read the separate `readiness.read`, `write`, `receipts` and `environment`
results alongside the diagnostics. A private profile env file with unfinished
credentials can fail doctor overall while knowledge reads and reminder hooks
remain usable. Keep that selected profile and surface its diagnostics; do not
hide them by switching to direct configuration or an unrelated credential
source. Verify write/receipt readiness before recording or compounding signals,
and required credentials before credential-dependent publication.

Use `knowledge-setup` to install or repair the runtime and harness integration.
Its `managed` mode runs APM; existing repositories with their own installation
and compilation commands use `prepare`, their repository-owned integration,
then `bind` and repository checks. The setup skill owns that procedure. A
successful preparation does not establish hook installation or instruction
composition.

Configured operations use a named profile, its declared default, or direct
`--config`. Paths authored in the workspace resolve relative to that file;
paths authored in profile overrides resolve relative to the registry. Request-file paths resolve relative to the
process working directory, except paths in `documents` and `signal_files`,
which follow their operation's documented source/configuration base. Requests
are JSON or YAML and use one structured contract rather than ad-hoc filter
flags. JSON is the default output format; `--output text` renders the same
values. Exit 0 includes a valid empty result, exit 2 reports invalid input or
content, and exit 3 reports incomplete external-state or runtime failure.

When an operation's request shape or supported values are unfamiliar, inspect
its schema before guessing:

```bash
agent-knowledge describe --request-file - <<'JSON'
{"schema":"search"}
JSON
```

Use the operation name, such as `inspect` or `catalog`, in `schema`. Reuse this
information while it still describes the running installation; this is not a
required call before every query. Search uses plural `topics`, not `topic`.
`text` is an object with nonempty phrase arrays under `any`, `all`, or both;
for example, `{"text":{"any":["rollback","recovery"],"all":["migration"]}}`
requires `migration` and either alternative. Inspect takes one singular
`document` object with `source` and source-relative `path`, as shown below.

For a request-schema error, use the diagnostic's field and the operation schema
to correct the request while preserving its intended question and filters.
Do not discard fields arbitrarily until a different query happens to succeed.

## Check a launch route without preparing it again

Use the installed `preflight` operation for lightweight launch diagnostics:

```bash
agent-knowledge --settings /work/private/profiles.yaml --profile example preflight --request-file - <<'JSON'
{"provider":"codex","consumer":"/work/code/orders-api","expected_venv":"/opt/agent-knowledge","expected_execution":"container"}
JSON
```

All request fields are optional and strictly validated. `mode` defaults to `read`;
`provider` is `codex`, `claude` or `copilot`. `consumer` and `expected_venv` are
absolute paths in the current execution environment. `expected_workspace_id`
asserts the selected workspace. Omit `expected_execution` for an ordinary local
check; supply `container` or `host` only when that tool-process target is required.
Discover the exact request through `describe` with `{"schema":"preflight"}`.

The `knowledge-preflight.v1` report contains `status`, `diagnostics`, `execution`,
`runtime`, resolved `routes`, `selection`, `environment_declaration`, `hooks`, and
independent `readiness` fields. Selection retains the effective fingerprint.
The environment declaration contains only the resolved private-file path and
`from_env` / `expose_as` mappings, never values; it lets a prepared launcher reject
changed declarations that are outside the configuration fingerprint.

Preflight reuses doctor's configuration/catalog, source-directory, private-file
and storage checks. It compares this interpreter's venv, selected/expected venv,
PATH launchers and requested provider executable without running the provider.
It performs no installation, APM work, network/model invocation, corpus scan,
credential activation, receipt append or compounding. It does not copy private
files or repair paths. Unfinished blank credentials remain `environment:not-ready`
and non-success overall while independent `read` readiness can remain `ready`.

Execution observations describe **this tool process**. On Linux, marker presence,
recognized bounded cgroup entries or a bounded `systemd-detect-virt --container`
result support `container`; absent/unreadable markers and `0::/` remain `unknown`.
Native Darwin is `host` relative to a Linux-container target; that does not locate
a VM or the outer harness. Other kernels without supported positive evidence stay
`unknown`; Linux probes are not attempted there. Detection is evidence, not a
security boundary. An explicit expectation fails if unknown or mismatched.

`hooks.file_available` only reports the selected consumer registration file's
existence. Its contents/registration, native trust and hook firing remain
`unverified`; a filename or PATH executable is not native delivery proof.
`execution.harness_location`, credential activation and `harness_sandbox` also
remain unverified. Run native acceptance through the actual launcher and tool
sandbox to establish those separate facts.

Explicit `{"mode":"write"}` uses only doctor's disposable probes in existing,
validated signal/usage directories and reports their cleanup. A mismatched
execution/runtime route or unavailable launch prerequisite prevents these writes.
The reported `write_scope` is this process and its inherited restrictions; an
unrestricted shell result cannot certify another harness's sandbox. Requested
write readiness must verify both signal and receipt stores. No signal is added,
no user content is deleted and no missing directory is created.

Exit categories remain `0` for the checks that passed, `2` for invalid input,
route mismatches or unestablished requirements, and `3` for I/O/runtime failures.
A successful lightweight check can coexist with explicitly unverified native
harness evidence. Preserve visible failures when the consumer supports a degraded
launch; do not turn a failed check into a success marker. Relevant runtime, profile,
mount, credential-declaration or launcher changes require their owning preparation
and acceptance steps, rather than an unconditional reinstall on every launch.

## Select a knowledge profile for this session

The user-owned registry is `~/.config/agent-knowledge/config.yaml`. Resolution
uses explicit `--settings` first, then `AGENT_KNOWLEDGE_SETTINGS` when set, then
the standard user path. The environment override must be a nonempty absolute
registry path; it contains no credentials and never selects a profile by itself.
This lets the same portable hook resolve different local paths in each execution
environment. There is one registry per invocation, without directory scanning or
layering. Direct `--config` remains independent of the registry and its override.

```yaml
schema_version: knowledge-profiles.v1
default_profile: personal
profiles:
  personal:
    config: /work/personal/knowledge-workspace.yaml
    environment:
      file: /Users/me/.config/agent-knowledge/personal.env
      variables:
        github:
          from_env: GITHUB_V_TOKEN
          expose_as: GH_TOKEN
          description: Personal GitHub repository access
  work:
    config: /work/company/knowledge-workspace.yaml
    overrides:
      receipts:
        retention_days: 60
```

```bash
agent-knowledge profiles list
agent-knowledge context
agent-knowledge --profile personal doctor
agent-knowledge --profile work search --request-file - <<'YAML'
kind: [guidance, runbook]
text:
  any: [secondary index, index rollout]
YAML
agent-knowledge --settings /work/local/profiles.yaml --profile personal signal list --request-file - <<'YAML'
include_shared: true
session_id: opaque-id-copied-from-the-provider-hook
limit: 50
YAML
```

Use the user's session choice first, then an explicit project recommendation,
then discover the declared default with `context`. List profiles when the name
is unknown; listing opens no workspace or knowledge files. Confirm `context`
and `doctor`, then pass the returned name explicitly on **every** configured
call, including reflection, signals, compounding and usage export. Keep the
same nonstandard `--settings` path. The direct-path examples elsewhere in this
guide also work with that selector substituted before the command.

During named-profile onboarding, `knowledge-setup` writes a short project
recommendation into the consumer's authored instruction source, regenerates its
harness instructions through the owned compilation flow, and verifies the
result. The hook remains generic; creating a registry entry alone does not
establish this recommendation. Repeated setup preserves an equivalent entry,
and a temporary session choice does not rewrite it.

A project instruction can say: "Default to profile work from
/work/local/profiles.yaml unless the user chooses another profile for this
session." A user can then say "Use personal for this session." Do not edit
`default_profile` to implement this choice. After resume/compaction, recover
the selected name and registry from retained instructions; if lost, ask rather
than silently switching to today's global default. A default change affects
unqualified calls. It does not affect explicit profile calls. There is no
session-ID binding database or access-control boundary: selection is followed
by the agent, and separate stores/sources must be configured deliberately.

Names are exact lowercase slugs such as `personal`, `work` or `example-project`.
Missing registry/default, unknown name or invalid settings fail explicitly;
there is no first-profile fallback. `--config` bypasses the registry completely
and cannot accompany `--profile` or `--settings`. `describe` accepts no selector;
`profiles list` accepts only `--settings` and output/provenance options, not
`--profile` or `--config`.

### Profile environments

A profile may declare one external dotenv file and explicit mappings from a
source name in that file to the name expected by a tool. The registry stores
only paths, names and descriptions. Values stay in the external private file,
except while a provider copies declared values into its private native runtime
environment channel.
Relative `environment.file` paths resolve from the registry.

`from_env` and `expose_as` use exact POSIX identifiers. Source and target names
must be unique. `expose_as` cannot name shell-control variables or the
setup-owned `_ak_` namespace, and the complete value-free declaration must fit
the bounded Claude session pin. Invalid declarations fail registry/setup
validation before a harness starts.

`profiles list` shows declarations without opening env files. `context` shows
the selected declaration and per-source availability; `doctor` checks that the
file is a current-user-owned regular file with no symlink traversal or
group/world permissions, validates strict UTF-8 `NAME=value` data, and verifies
every declared source name. Values are never returned. Direct `--config` has no
profile environment. Environment metadata and file contents never affect
knowledge fingerprints, continuations, receipts, usage exports or compounding
routes.

Use literal assignments, optionally prefixed by `export `. Empty, duplicate,
quoted, interpolated or shell-evaluated values are unsupported. Keep the file
mode at `0600` or stricter and rotate values there without editing the registry.

Blank assignments may be left as unfinished setup placeholders. They remain
invalid for activation: setup reports credentials pending and supplies no
activation command while allowing independent reminder-hook binding. After
filling the private file, rerun setup with the same profile in `managed` or
`bind` mode before following its new-session activation action.

Credential activation is fixed at harness startup. One session activates at
most one credential profile. A later `--profile work` changes only the
knowledge request; it cannot mutate the parent harness environment. Rerun
`knowledge-setup` for the intended profile, then start a new session to activate
it, and pin one profile in scheduled work.
Claude local sessions use a setup-bound `SessionStart` hook that guards the
source file again, writes shell-quoted declared exports to Claude's private
`CLAUDE_ENV_FILE`, and pins the value-free declaration by session ID across
resume/compaction. These private pins live under
`~/.cache/agent-knowledge/claude-environments/<consumer-hash>/`, contain only
the external path and mappings, and remain until that cache directory is
explicitly removed. Removing it resets the binding for a later start/resume.
Hook output and durable evidence never contain values. Setup creates a
content-addressed, value-free launcher that loads the selected mapping and
starts Codex CLI or Copilot CLI without printing shell exports. Codex replaces
the launcher process. For Copilot, the launcher passes protected internal
aliases for native redaction without replacing parent values under declared
targets such as `GH_TOKEN`. It restores the mapped values only inside
Bash tools through a private mode-`0600` activation file, unsets the inherited
file pointer there, and removes the file on ordinary wrapper exit. The launcher
injects and owns the required Copilot activation/redaction flags, so callers do
not reproduce or override them. Copilot may
retain its provider-global Bash-support preference; that setting contains no
profile path or value. An abruptly terminated wrapper can leave its private file for
operating-system temporary-file cleanup. Codex and
Copilot desktop do not expose a documented generic per-task env-file injection,
so use their native stores or explicit credentialed-command sourcing. Provider
keychains remain outside this contract; profiles are not an access-control
boundary.

Follow the exact provider status, launch command and profile-aware
`doctor.command` returned by `knowledge-setup`. Do not reconstruct provider
flags. A failed activation emits a value-free remediation pointing back to that
doctor command.

One local consumer hook binds one credential profile for all new Claude
sessions. A profile written into a recurring-task prompt selects knowledge, not
credentials. Concurrent Claude tasks needing different profiles require
separately launched local sessions with verified profile bindings.

Supported overrides are `applicable_scopes`, `sources`, `signal_storage`,
`receipts` and `setup`. Known map fields merge; lists replace entirely. For
`sources`, supply complete source records, including any publication settings
you want to retain. Nulls, unknown fields and overrides of workspace identity
or schema are errors. No shell expansion or environment interpolation occurs.
The base workspace must be schema-valid before the overlay; only the effective
sources need to be available. An empty scope list is valid; an empty source
list is not. Technology, taxonomy and matching semantics are unchanged.

Every configured response has `selection`: mode, profile, registry path, base
config path and effective fingerprint. `context`/`doctor` also return
`configuration.values`, `field_origins` and `overridden_fields`. Paths and
implicit defaults keep the location that authored them; a registry-level venv
override does not rebase an inherited signal directory. Setup owns deliberate
registry edits. Local overrides do not justify changing a shared base workspace.

Tool receipts and exported descriptors retain this same selection and effective
configuration, without including unrelated registry entries. Continuations bind
to the effective snapshot: default/unrelated-profile edits do not invalidate an
explicitly selected unchanged profile. Source/scope/catalog changes do. Compound
runs freeze routing, publication and storage across invocations while permitting
normal document/catalog content updates. If routing changes, retain signals and
restore the original selection before continuing. Aliases of one store share
its existing run coordination and must share one automation owner.

## Discover vocabulary before filtering

Use `catalog` to find registered identifiers. Names in a request are not free
text and are never silently corrected:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml catalog \
  --request-file - <<'YAML'
dimension: entities
text:
  any: [past orders, order history]
limit: 10
YAML
```

Catalog dimensions are `scopes`, `entities`, `topics`,
`languages`, `technologies`, `technology_families` and `environments`. Text is
literal, case/Unicode normalized discovery. An alias can return multiple
candidates; choose an exact ID before issuing a narrower search. A catalog is
vocabulary and provenance, not an approved-stack decision.

Scope records may declare parents. That relationship describes an
organization's configured hierarchy, but it does not grant access, expand a
query, or establish local-over-shared precedence. Include every applicable
scope explicitly in a request. A source may combine several catalogs when
their definitions agree; conflicting definitions are a configuration error.

## Search and read progressively

Search returns file previews and locations, never body excerpts:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml search \
  --request-file - <<'YAML'
kind: [feature, workflow]
scope: [org:example, group:commerce, repo:orders-api]
text:
  any: [order history, past orders]
limit: 10
YAML
```

Facet values within one field are OR alternatives. Different supplied fields
are AND restrictions. Omitted fields are unrestricted. Missing document
metadata is not `any`. On documents, `[any]` is the only valid value for an
unrestricted language, technology or environment. A query may explicitly use
`[any, typescript]` or `[any, postgresql, family:relational-database]` to retain
general and specific guidance. Family membership in a catalog does not expand a
query; request `family:<id>` when family-level guidance is wanted.

The initial search can be broad by kind and text. Once the task is understood,
issue focused searches for separate questions such as product behavior, system
context, topics and operational procedures. Use descriptions and match locations
to assess relevance; a result matching a broad word such as `review` may concern
another task. Use catalog-discovered identifiers when adding filters. When
narrowing by scope, explicitly include relevant shared and consumer scopes,
such as `org:example` and `repo:orders-api`; neither implies the other. Add only
facets supported by the question, retaining general guidance through `any` or
an unfiltered pass where appropriate. The command does not plan those passes
or infer a task from prose. The agent decides which questions matter at the
current stage.

An exact phrase, library name or guessed title returning no matches does not
establish that the owner is absent. Try terms for the underlying behavior and
review likely owners and applicable facets. If the configured source and path
are already known, use `inspect` directly instead of repeatedly guessing search
phrases. Distinguish a missing observation from existing guidance described in
different language.

Each result identifies its source, source-relative path, resolved local path,
kind, description and authored facets. It also reports bytes, physical lines,
frontmatter/body ranges, a complete-byte fingerprint, link count and matching
line ranges. Metadata-only matches are marked as such. Results and locations
are bounded and paged with opaque continuations tied to the original request
and source snapshot. A changed snapshot requires a fresh search.
Follow returned continuations with the original request when the task needs
coverage beyond the first page, including further match locations when relevant.
A truncated page cannot support an exhaustive coverage or absence claim.

Use `inspect` after selecting a file:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml inspect \
  --request-file - <<'JSON'
{"document":{"source":"commerce-knowledge","path":"runbooks/postgresql-index.md"},"limit":20}
JSON
```

Inspection returns the same preview plus a bounded heading and link outline.
It does not follow links or read linked bodies. Use ordinary tools with the
returned path and line ranges to read a complete file or only the relevant
procedure and its prerequisites:

```bash
sed -n '15,32p' /work/code/commerce-knowledge/knowledge/runbooks/postgresql-index.md
```

Read warnings, prerequisites and recovery sections when the procedure depends
on them. A matching sentence is not proof that the surrounding caveats were
read. Refresh the preview when a fingerprint is stale. Links expose resolved,
missing, unsafe, unresolved or external status; external references are never
fetched. Navigation is a graph of pointers for the agent to explore, not an
automatic recursive retrieval or runtime dependency graph.

## Apply guidance and report review results

Use applicable guidance before consequential decisions and while doing the work.
Include relevant general and specialised guidance in your selected searches;
search again when the task reveals a new surface. Assess applicability from the
task, actual changes and their effects, not just filenames or diff size. A
failed lookup does not establish that no guidance exists.

Review the final state against the relevant expectations. Reuse evidence that
still covers that state; later changes can invalidate earlier results. Reading
a document or receiving a retrieval receipt does not establish compliance.
Reference existing automated checks where they cover the expectation.

Report material fulfilled constraints, unresolved gaps and verification limits
in the task response, PR or owning review artifact. Keep reporting proportional:
use a checklist when useful, and exhaustive accounting only when requested or
warranted by the task's consequences. Avoid repeating an existing review or
listing every irrelevant check. Explain material non-applicability using task
context; do not count it as a pass.

If using completion checkboxes, reserve `[x]` for verified outcomes supported by
actual evidence. Distinguish failed from unverified or blocked outcomes; leave
them unresolved. For judgement, evidence can support that the required assessment
was performed, not that a design is objectively optimal. State uncertainties or
conflicts instead of inventing an exemption. An interruption leaves outstanding
work in the ordinary handoff, not a fabricated completion report.

Task outcomes belong in the task response or review, never as completion ticks
in shared guidance. Conversational tasks need no empty checklist. This is a
reporting convention, not a required output schema or an independent audit of
the agent's claims.

## Follow relationships and check dependants

Use the default `inspect` navigation view for headings and authored outgoing
links. To discover documents that refer to a selected owner, request incoming
links explicitly:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml inspect \
  --request-file - <<'YAML'
document:
  source: commerce-knowledge
  path: product/features/order-history.md
view: incoming
sources: [commerce-knowledge]
limit: 10
YAML
```

Here `sources` selects the configured sources to scan for references, not the
target's applicability. Omit it to scan all configured sources; it is accepted
only with `view: incoming`. The incoming view also accepts a safe missing target
path after a move or deletion. Its absence is explicit, and anchors on a missing
target cannot be verified. Ordinary navigation requires a readable target.

Incoming results contain referencing-document previews, link labels, physical
reference locations and anchor/status information. Read the relevant referring
sections with ordinary tools. Same-document section links stay in the navigation
outline. Shared entities or topics do not create links. Neither direction
inherits metadata, establishes precedence or rewrites the other document.

The scan reads Markdown internally and returns metadata, not body prose. Follow
continuations until the selected scan is complete; changes to the target or scan
sources require a fresh request. An incomplete scan, unreadable source, unsafe
path or invalid document is not proof that there are no dependants. Coverage is
authored Markdown links in the selected sources. Catalog entity `documents`
references are separate: check them too when moving or retiring an owner.
Unconfigured and unselected sources remain outside this coverage.

When authoring, link concrete relationships with informative labels. Keep
prerequisite and constraint links near the prose that depends on them. Incoming
discovery makes reverse navigation possible without a reciprocal edit; write
links in both documents only when each helps its reader. Before renaming,
retiring or materially changing an owner, inspect incoming references and assess
relevant dependent claims. Repair affected links and catalog references in the
same validated publication state, preserve independent applicability, and report
unresolved impact without extending edits into unrelated owners.

## Validate before authoring or publishing

`validate` uses the same strict codec, catalog and link rules as retrieval. It
requires exactly one explicit target family:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml validate \
  --request-file - <<'JSON'
{"sources":["commerce-knowledge"]}
JSON
```

For a smaller authoring iteration, use `documents` with source-qualified
paths. For a signal that has not been captured, use `signal_files` with paths
relative to the workspace configuration. Validation checks structure,
registered IDs, frontmatter, fingerprints and local references. It does not
judge whether a claim is true, fetch evidence, publish changes or move a file.
Missing files, malformed metadata, unknown IDs and broken local references are
explicit diagnostics rather than a successful empty result.

## Author canonical knowledge

Knowledge files are Markdown with strict YAML frontmatter. The initial kinds
are `concept`, `feature`, `workflow`, `system`, `guidance`, `runbook`,
`limitation` and `incident`. Folders are conventional; the
validated `kind` is authoritative. Use the shipped templates for the body
shape, and keep independently useful procedures, warnings and prerequisites
together or explicitly linked.

The eight kinds and metadata fields are fixed; catalog vocabulary is
configurable. Register marketing or lead-generation as topics, and a particular
campaign or qualification workflow as an entity. Guidance describes approaches,
requirements, constraints and standards; a runbook gives executable steps; a
workflow describes stages, participants and outcomes. Guidance can express
mandatory requirements. Nontechnical guidance uses `[any]` for language,
technology and environment when those dimensions are unrestricted.

Within guidance, prefer short conditional checks when they make supported
expectations easier to apply or verify. Each check should make clear when it
applies and what should be true. Indicate useful evidence where appropriate;
reference existing automated checks or runbooks instead of reproducing their
internals or inventing extra verification work. Keep rationale and supported
exceptions nearby, preserving mandatory versus recommended wording.

Prose is equally valid and needs no special justification. Describe judgement
and trade-offs in the form that helps the decision; do not turn every principle
into an assessment to document. Group coherent checks with shared applicability,
splitting documents only when they serve independently useful purposes. Keep
canonical checkboxes unticked. Markdown checks introduce no new kind, metadata
or runtime state, and descriptive facts and history need no conversion.

Test and verification reports stay with the owning repository, CI run, PR or
external evidence system. Preserve a durable conclusion as guidance, a
limitation or a repeatable runbook procedure, citing the report and the
conditions under which its finding holds. Keep the original evidence; a single
successful test does not establish a universal rule.

The canonical frontmatter shape is:

```yaml
---
schema_version: knowledge.v1
kind: guidance
title: "<short behavior-first title>"
description: "<when this document is useful>"
scope: ["<registered-scope-id>"]
topics: ["<registered-topic-id>"]
entities: ["<registered-entity-id>"]     # optional
languages: [any]                         # required for guidance
technologies: [any]                      # required for guidance
environments: [any]                      # required for guidance
aliases: ["<discovery phrase>"]          # optional
terms: ["<discovery phrase>"]            # optional
---
```

Required fields are `kind`, `title`,
`description`, `scope` and `topics`. Guidance must state
its language, technology and environment applicability explicitly. Do not
use legacy names such as `scopes`, `subjects`, `concerns`, `engineering_concerns`, `strength` or
`activity`.

`scope` describes where a claim applies. `entities` names the feature, service
or other registered thing discussed. `topics` describes reusable business or engineering subjects, such as
lead-generation, positioning, architecture, testing or reliability. `languages`, `technologies` and `environments` describe explicit
applicability. Keep general principles at `[any]` and split vendor-specific
procedures when their instructions differ.

Signals use a separate `knowledge-signal.v1` envelope. Their `origin` records
the workspace and producer context; it is provenance, not automatic canonical
applicability. A compounding workflow must load the originating configuration,
search existing owners and assign the narrowest applicability supported by
evidence. It must not promote a repository-origin observation to an
organization or technology-family rule merely because the producer belongs to
that scope or technology family.

## Reflect and record useful observations

At a natural stopping point, review work already performed using this procedure:

1. Identify durable discoveries and user corrections, misleading or missing
   knowledge, retrieval misses, and skill instructions, references, templates or
   scripts that caused an omission or incorrect action. A routine success or
   transient tool failure alone is not a reason to record a signal.
2. Reuse relevant discovery already performed in this session. For a plausible
   knowledge gap, use `catalog` to identify the vocabulary, then focused `search`
   and `inspect` calls before claiming an owner is absent. Preview first and read
   selected sections. A failed or narrow search is not a confirmed gap.
3. For a possible skill or instruction gap, inspect likely advertised names,
   descriptions and source locations, then only plausible bodies or attachments.
   Skill inventory is supplied by the harness and accessible package metadata;
   the knowledge catalog and CLI do not index skills. Record a likely source or
   version in the signal body/evidence when known. The fuller owner investigation
   belongs to `knowledge-compound`; a skill-only correction can be a complete
   outcome without a canonical knowledge document. Unavailable discovery or
   uncertain ownership must not prevent evidence capture or be reported as proof
   of absence.
4. Before recording, list pending signals for the configured workspace/project
   using the exact hook session ID and inspect likely equivalent bodies. Follow
   continuations when needed to complete that same-session duplicate check.
   Record one useful observation only when an equivalent is not already pending.
5. Use the installed signal template and preserve concrete evidence, what happened
   and the useful lesson or correction. Describe an unverified gap as unverified.
   Copy the hook's normalized provider and opaque handle exactly into
   `origin.harness` and `origin.session_id`; do not guess either value. Record
   nothing when there is no useful finding. Compounding decides whether an
   observation changes canonical knowledge or another owner.

The duplicate-check request is:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml signal list \
  --request-file - <<'YAML'
include_shared: true
session_id: "provider-session-123"
limit: 50
YAML
```

`session_id` is an exact, case-sensitive predicate. The list remains a
metadata-only preview: it returns the signal path, body range, line count and
fingerprint, but not the Markdown claim. Use ordinary file tools to inspect
likely duplicates, then record at most one concise observation for the same
issue. The CLI does not deduplicate; compounding decides the final disposition.
Signals with `origin.harness` must contain a valid nonblank
`origin.session_id`. Manual signals without harness provenance may omit it.
`origin.automation_id` is independently optional and cannot replace the session
handle. For compounding's initial inventory, omit `session_id` so observations
from every authoring session in the configured project/shared selection remain
visible; reserve the filter for authoring deduplication or targeted inspection.

## Usage receipts and archived signals

The CLI writes one terminal `knowledge-retrieval-receipt.v1` event for each
`catalog`, `search` and `inspect` invocation when collection is enabled. The
complete structured response and parsed request are preserved, including empty
results, diagnostics, previews, pagination and incoming references. A malformed
request is recorded as null without copying its raw input. `body_read: unknown`
means ordinary grep/editor reads remain unobserved. Elapsed milliseconds and
canonical-JSON UTF-8 response bytes measure tool work and payload size, not tokens
or relevance. A diagnostic write failure does not turn a successful lookup into
an error. Invalid configuration never causes a guessed receipt destination.

Pass provenance as global flags before the command, separately from filters:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml \
  --harness claude --session-id provider-session-123 search --request-file - <<'YAML'
kind: [guidance, runbook]
topics: [testing]
limit: 10
YAML
```

During compounding add `--compound-run-id` with the exact ID returned by start.
The recorded run must belong to this workspace; it supplies consistent harness
and session defaults. Carry this context on catalog/search/inspect and validate
calls. Missing manual provenance remains null and limits later evaluation.
Validation events support the run's evidence; success does not establish the
semantic truth of a claim.

Setup defaults `receipts.enabled: true`, `directory: ./ai/usage`, and
`retention_days: 30`. Paths resolve relative to the explicit configuration;
setup uses the durable scaffold location when the config is in a consumer.
Usage stays outside source and signal roots and is ignored in Git. Doctor
reports collection readiness. Diagnostic collection can be disabled, but safe
compounding still requires archived inputs and durable drain decisions.

`compound start` validates and archives the exact selected signal bytes under a
new run. `compound drain` requires that run ID and matching snapshots, persists
its decision/intent, verifies archives and current inbox bytes, and reports actual
removals and retained inputs. Never remove or move inbox files yourself. Archives
are evidence, not pending signals or searchable canonical knowledge. Finish
records an agent-reported outcome; actual drain counts come from prior tool events.
Publication claims remain agent-reported unless independently checked.

### Publication coverage and completed knowledge work

The compounding agent determines the useful knowledge, skill or instruction
outcome. Recording an accepted decision with implementation explicitly deferred
can complete that outcome; preserve its status and link the owning product
plan. Do not claim implementation proof or retain a fully handled signal solely
as a reminder of future product work. If a necessary authoring correction is
still unresolved, retain the signal and state the missing prerequisite.

For write decisions (`update`, `create`, `delete-retire`), disposition `owners`
lists every actual required authoring destination. Use `{source, path}` for
knowledge and `{repository, path, package?}` for the resolved authored skill or
instruction source. Discovery candidates, citations, unchanged references and
future implementation repositories are not additional write destinations;
preserve their relevance in the rationale. Never remove a required authoring
owner to make coverage pass. An unresolved owner requires an
`owner_unavailable_reason` and retains the actionable update.

A drain request supplies `publications`, with one entry per exact repository.
Each entry requires `repository`, `status` and boolean `publication_verified`.
The statuses are `published`, `pending`, `unavailable` and `not-required`.
Drainable writes require matching `published` entries with
`publication_verified: true` and a full exact remote `commit`; a reviewed PR
route also records its positive integer `pull_request` number. A PR number
alone does not identify the verified commit. These illustrative entries cover
a central runbook and a consumer skill in one request:

```yaml
action: drain
run_id: compound-returned-run-id
selected:
  - id: release-migration
    path: /work/knowledge/ai/signals/shared/release-migration.md
    fingerprint: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
dispositions:
  - signal_id: release-migration
    decision: update
    rationale: The runbook and release skill now require the verified migration step.
    owners:
      - source: example-knowledge
        path: runbooks/release.md
      - repository: example/orders-api
        path: .apm/skills/release/SKILL.md
publications:
  - repository: example/knowledge
    status: published
    publication_verified: true
    commit: "0123456789abcdef0123456789abcdef01234567"
    pull_request: 12
  - repository: example/orders-api
    status: published
    publication_verified: true
    commit: "89abcdef89abcdef89abcdef89abcdef89abcdef"
    pull_request: 34
```

Replace the illustrative IDs, paths and publication evidence with inspected
values. The selected knowledge source must configure `example/knowledge` as
its publication repository for this example to cover that owner. Profile
selection and its effective source overrides remain authoritative. A source
without a publication route cannot have a required write certified by an
arbitrary repository entry. Skill/instruction owners match their explicit
repository. Duplicate repository entries are rejected. Every required owner
must have matching verified evidence; one missing, pending or mismatched entry
retains the affected signal without blocking independently completed signals.
Verified PR publication is sufficient; human review or merge need not finish
before eligible unchanged inputs drain.

For bounded per-repository change evidence, each entry may also provide
`checkout` and the `before_revision` / `after_revision` pair. Capture only
this run's change, not a whole pre-existing PR. `unavailable_reason` describes
unavailable publication, not a missing optional patch, and prevents that entry
from certifying a write. Patch capture reports its own unavailable reason.
Optional patch capture and publication assertions are separate: a local
patch cannot verify a remote commit, and a missing patch does not invalidate
separately verified publication. The CLI records the declarations as
agent-reported and captures patches only when the supplied revisions can be
safely read. It does not contact GitHub, establish authorization, infer semantic
owner coverage or independently verify a PR. The agent performs those checks;
a tool-written receipt preserves their asserted result.

`keep` (already covered) and `skip` (out of scope) require a supported rationale
and relevant owner/evidence, but no new publication for unchanged owners. Omit
`publications` or supply `[]` for a no-write round. Do not relabel an unfinished
write as no-write to bypass publication. `defer` retains unresolved work.
All dispositions still use the recorded snapshots, mandatory archives and
pre-removal intent; current signal bytes and file-safety checks remain decisive.
Historical run records remain evidence of their original assertions, not new
publication requests or a reason to rewrite past receipts.

### Local trigger agreement and delegated workers

The setup skill selects one local trigger for a shared signal store. Configure
`setup.compounding` in the workspace or an explicit profile override:

```yaml
setup:
  compounding:
    mode: prompt
    owner: shared-workspace-compounding
    interval_seconds: 86400
    retry_seconds: 3600
```

Modes are `disabled`, `manual`, `local-schedule` and `prompt`. Missing configuration
is unconfigured, never implicit permission. The owner is a stable logical name for
this shared store, not a profile spelling, provider or container path. All profile
aliases/providers that share storage must agree. Both intervals accept integer
seconds from 3600 through 2592000. A prompt interval is rolling elapsed time;
native local schedules retain their own cadence and timezone.

Run the following with the same explicit selector on every invocation:

```bash
agent-knowledge --profile example compound --request-file - <<'YAML'
action: configure-trigger
YAML
agent-knowledge --profile example compound --request-file - <<'YAML'
action: due
YAML
```

`configure-trigger` prepares the validated receipt directory and records the
selected configuration in the existing `ai/signals/compound-activity.jsonl`. Repeating the same agreement is a no-op.
For an intentional mode/owner change, inspect `compound` with `action: status`,
change the authored setup configuration, then include `expected_trigger` with the
exact previous `trigger` mapping. The compare-and-swap rejects stale replacements
and refuses changes while a run is unfinished. Setting `disabled` and reconciling
its agreement pauses the fallback; `manual` retains explicit manual runs.
Removing package-owned hooks uses the setup skill's removal procedure. Changing
this agreement does not remove an external scheduler; reconcile that scheduler
before enabling a different trigger.

`action: due` returns `due`, `reason`, `next_due_at`, `active_runs` and
`inbox_probe`. It is advisory, not a reservation. It uses a nonblocking lifecycle
lock and a bounded metadata probe: `potential` means candidate files exist,
`inconclusive` means the entry budget was reached, and only a complete probe can
say `empty`. It reads no signal claim bodies, runs no model and contacts no
network. Busy, conflicting, corrupt, future-dated or otherwise ambiguous
coordination state never authorizes a run. An obviously missing or unwritable
receipt directory returns `receipts-unavailable` using metadata only; authoritative
start still verifies actual writes because permissions/mounts can race. Prompt transport further bounds the
check's elapsed time; discovery/reflection continue independently on failure.

When prompted to delegate, load the installed `knowledge-compound` skill and
retain the exact selector and parent context. Discover/snapshot the inbox before
starting, but do not edit owners, publish or drain before the atomic start:

```yaml
action: start
workspace_id: workspace:example
automatic: true
harness: codex
parent_session_id: exact-exposed-parent-handle
session_id: exact-exposed-worker-session
worker_id: exact-exposed-subagent-handle
selected: [] # Replace with the exact signal-list snapshots chosen for this run.
```

Omit unavailable handles; never invent them. Prompt fallback has no native
automation handle. Set `automation_id` only from an actual scheduler's exposed
handle, never from the logical trigger owner, task name or workspace marker.
Do not wait indefinitely to start merely because the provider has not yet
exposed the worker ID. `automatic: true` rechecks the same
eligibility under the lifecycle lock. `started: false` means exit without touching
another run, including when a stale reminder arrives after another worker has
finished. A winner receives `started: true` and `run_id`. Associate subsequent
calls with `--compound-run-id`; do not recursively delegate another compound
worker. The parent continues its own task. A recorded worker handle supports
reuse only where that provider actually exposes a live/resumable worker.

Some providers return the native worker handle only to the parent after it
starts or finishes. Pass that exact handle to the worker through the supported
provider messaging mechanism when available. Once the exact compound run ID is
known, the parent or worker can attach exposed identity using the same selected
CLI without repeating compounding:

```yaml
action: record-worker
run_id: compound-returned-run-id
worker_id: exact-exposed-subagent-handle
parent_session_id: exact-exposed-parent-handle
harness: codex
```

These are illustrative placeholders, not values to invent. `run_id` and
`worker_id` are required; optional `parent_session_id` and `harness` must agree
with existing recorded identity. The action accepts an active or finished exact
run, is idempotent for the same values, and rejects conflicting identity. Its
result includes `action`, `run_id`, `worker_id`, `parent_session_id`, `harness`
and `updated`. Metadata is recorded in the existing activity JSONL and run
archive, survives rollover, and does not restart work, change completion or
authorize edits, publication or drainage. Unknown identity stays absent.

Automatic finish requires `completion` in addition to the existing free-form
`outcome` and dispositions:

| Completion | Meaning and next prompt eligibility |
| --- | --- |
| `completed` | Every selected input has a disposition; wait `interval_seconds` from finish. |
| `deferred` | Every selected input has a disposition and prerequisites are reported; wait the same interval, retaining unresolved inputs. |
| `failed` | Attempt failed; retain unresolved inputs and wait `retry_seconds` from finish, without shortening an earlier completed check's interval. |
| `empty` | No selected inputs or dispositions; no success interval is recorded, so later-arriving signals are eligible. |

Malformed or inapplicable candidate files are not proof that the inbox is empty;
report an appropriate failure/deferral rather than repeatedly claiming an empty
successful run. `completed` or `deferred` may retain inputs. Neither classification
proves publication or permits drainage. Existing publication assertions, owner
validation and unchanged-byte drain checks remain mandatory. A manual finish may
omit `completion`; its free-form outcome alone does not establish automatic
success. Readiness problems are visible without spawning on every prompt.

Unmatched starts remain active indefinitely, with exact recorded identities.
Never take over because a timestamp is old. Inspect archived inputs, owner edits,
publication and drain evidence and reconcile the original run before another
worker starts. A new attempt may include `recovery_of` naming the prior, already
finished run; this preserves lineage without impersonating its worker. An
interrupted finish with durable evidence but no terminal coordination record
requires inspection, not a blind retry. No additional timestamp/lease database is
maintained. Rollover retains unmatched starts, the latest relevant terminal
start/end pair, the latest check needed for clock safety and the current trigger;
a later failed attempt does not discard the most recent completed check. Older
records remain in the existing coordination/run archives. If storage fails before
an attempt can be durably started, report unavailable readiness; do not fabricate
a successful or failed terminal record.

For a local review of a UTC interval (inclusive start, exclusive end):

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml usage export \
  --request-file - <<'YAML'
since: "2026-09-08T00:00:00Z"
until: "2026-09-14T00:00:00Z"
destination: /work/reviews/knowledge-usage-september-8-13
YAML
```

The destination must be fresh. Export preserves originals and includes this
workspace's events, relevant earlier run context, available archived inputs and
change patches, vocabulary descriptors, checksums and coverage diagnostics. It
never uploads data or claims that no records proves no activity. Missing session
IDs, expired/missing artifacts, partial records and unavailable source versions
remain explicit. Retention preserves active/unresolved evidence; completed-run
retention begins at completion. Evaluate quality using these records and reviewed
examples; receipts do not infer relevance or recreate historical document bodies.
