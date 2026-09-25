# Knowledge Scaffold Final Pass

**Date:** 2026-09-14
**Implementation status:** B1-B5 are implemented and the final deterministic, fresh-install and live Claude checks passed. The user approved committing the completed work and integrating it onto `main` after review. The user authorized completing all remaining Bs without intermediate review stops.
**Working plan:** use this file for the current follow-up and all subsequent
slice decisions, edits and build evidence. It replaces the follow-up previously
appended to the [master core plan](organization-neutral-knowledge-core.md).
The master retains the original architecture, R1-R8 history and earlier proof;
it is not a second owner of these follow-up requirements.

The outcome is a business-flexible knowledge scaffold with clearer compounding
and source ownership, progressive incoming-link discovery, and tool-written
usage evidence that the user can evaluate with a real agent.

## Delivery at a glance

| Slice | Change | Depends on | Status |
| --- | --- | --- | --- |
| [B1](#b1-taxonomy) | Rename engineering concerns to topics and operating-rule to guidance; remove qa-evidence | Existing core | Complete; user authorized proceeding |
| [B2](#b2-business-onboarding) | Assist business-context discovery and create a small validated catalog/configuration | B1 | Complete; live Claude onboarding passed |
| [B3](#b3-incoming-links) | Add optional incoming-link inspection and reference-maintenance guidance | B1 | Complete; live incoming discovery and rename passed |
| [B4](#b4-reflection-and-compounding) | Strengthen reflection/owner discovery, instruction traceability, catalog maintenance and business decision history | B1 | Complete; live reflection, owner discovery and business history passed |
| [B5](#b5-usage-receipts-and-signal-archives) | Add automatic receipts, archive before draining, retention and date-range export | B1-B4 | Complete; deterministic, installed and manual live Claude proof passed |

The user authorized completing B3-B5 together after B1/B2. Implement the accepted
slices directly. Preserve the pure domain/application/infrastructure/CLI
boundaries, fast semantic tests and source-owned APM instructions/resources.
This remains a fresh implementation: no compatibility aliases or legacy
runtime/corpus imports. Native scheduling tests remain paused. The user also requested that real-harness
model tests run once the whole B1-B5 plan is implemented, rather than per slice.
Continue fast domain/unit/integration tests and isolated CLI/APM package checks
during implementation. This extraction
changes plan ownership, not implementation or the accepted proof boundaries.

Each slice's full contract is below. [Implementation notes](#implementation-notes)
cover synchronized surfaces; [verification](#verification) retains the agreed
fixtures, failure cases and live-harness limits. Examples describe the supported
contracts; the build evidence records what was verified.

## Acceptance and scope boundaries

**Status:** the user accepted the `engineering_concerns` to `topics` rename,
the `operating-rule` to `guidance` rename, removal of `qa-evidence` from the
knowledge kinds, and an onboarding follow-up that understands the business,
proposes its initial catalog, confirms meaningful choices and creates
validated configuration.
Targeted questions are allowed when existing context or documentation is
unclear. The user also accepted optional incoming-link discovery and its
authoring/compounding guidance. The user also requested stronger procedural
reflection, skill-owner discovery, an explicit catalog-versus-workspace
boundary for compounding, and consolidated, traceable always-on instructions.
The user accepted preserving consequential business decision history in
ordinary knowledge documents, maintained through compounding.
The user accepted tool-written retrieval and compounding receipts, archived
signal inputs and a date-range usage export as the final improvement (B5)
before their real-agent evaluation. Agents do not author receipt files.
Implementation details and proof below distinguish deterministic checks, installed
package checks and observed live-harness behavior.
User-configurable document kinds remain a separate discussion; this acceptance does not add
them. R1-R8 and the later hook/reflection work keep their existing
completion/proof boundaries.

## B1: Taxonomy

**Accepted rename:** replace the required `engineering_concerns` facet with
`topics` across catalog, document metadata and search requests. Keep its current
registered-ID validation and matching semantics. A solo founder or a squad can
register topics such as testing, architecture, positioning and lead-generation
without changing the parser. `topics` describes business and engineering
subjects without an engineering-only field name. Avoid
adding a separate business-only retrieval path or another mandatory domain
hierarchy.

**Accepted document taxonomy:** the new default set is `concept`, `feature`,
`workflow`, `system`, `guidance`, `runbook`, `limitation` and `incident`.
Rename `operating-rule` to `guidance` throughout the active new-core contract,
templates and examples. Guidance describes the approach, requirements,
constraints and standards to follow across engineering and business work.
Its wording must distinguish guidance from the executable steps of a runbook
and the stages/participants of a workflow. The rename does not make an
existing requirement optional or introduce a new authority/priority facet.
Preserve the current explicit language, technology and environment
applicability requirement for this renamed kind; nontechnical or unrestricted
guidance uses `[any]` where appropriate.

Remove `qa-evidence` from knowledge parsing, search kind selection, signal
`kind_hint`, `describe`, installed templates and active examples. Routine
test/verification reports stay with the owning repository, CI run, PR or
external evidence system. Compounding extracts a supported durable conclusion
into the appropriate remaining kind: a constraint into a limitation, an
approach into guidance, or a repeatable verification procedure into a runbook.
Keep citations and relevant conditions in the resulting document rather than
copying a run report or silently treating a one-time result as universal truth.
Retain ordinary evidence/provenance links and signal evidence fields; removing
a document kind does not remove evidence support. Do not delete source test
artifacts or add a replacement experiment/finding kind in this slice.

Preserve these distinct meanings:

| Field | Question answered | Example |
| --- | --- | --- |
| kind | What sort of record is this? | workflow, concept, guidance, runbook |
| topics | What reusable subject does it address? | lead-generation, positioning, testing |
| entities | Which particular named thing is discussed? | product:launchpad, workflow:lead-qualification |
| scope | Where does this knowledge apply? | org:my-startup |
| source | Where is the knowledge stored? | business-knowledge |

User extensibility lives in the registered vocabulary and authored knowledge,
including labels, descriptions, aliases and existing scope/family relations.
Keep the metadata fields and the eight accepted document kinds fixed for this
follow-up; marketing is a topic, not another record kind. A genuinely new
document shape can motivate a later kind extension. Do not build arbitrary
metadata schemas, dynamic parser plugins, topic inheritance, a taxonomy UI or
automatic query expansion. A marketing skill remains an APM workflow that
calls the same knowledge interface; it is not a searchable knowledge kind.

The query shape below is supported by B1. Its scope/topic identifiers must
first be registered in the selected workspace catalog:

```yaml
kind: [workflow, guidance, runbook]
scope: [org:my-startup]
topics: [lead-generation, positioning]
```

An agent selects topics for the current task; there is no compulsory marketing
search on engineering tasks. Broad searches may still discover cross-cutting
knowledge. Topic lists remain flat and explicit, and adding a topic never
changes scope membership, document truth or permissions.

Topics describe reusable questions rather than mandatory departmental silos.
For example, `[marketing, privacy]` still means either topic; use a specific
topic with entity/text filters, or separate searches, for a narrower question.
A file still has one applicability envelope. Keep a general privacy principle
at technology `any` and link its HubSpot-specific procedure rather than hiding
the general claim inside a HubSpot-only document. Nontechnical guidance
can explicitly use `any` for language, technology and environment.

### B1 implementation and proof (2026-09-14)

Implemented on `build/b1-taxonomy`, with no compatibility aliases:

- Domain models, catalog validation, matching, search/inspect previews and CLI
  schema discovery now use `topics` and the eight accepted kinds. Knowledge,
  search and signal hints reject retired kinds; catalog/knowledge/search reject
  `engineering_concerns`. Existing OR/AND and explicit applicability behavior
  remains intact. Signals gain no required topic field.
- The wheel exposes nine knowledge templates (including both runbook variants)
  and one signal template. Guidance retains explicit applicability, supports
  business requirements and distinguishes approaches from procedures/workflows.
  The guide, CLI examples, compound skill and startup reminder use the broader
  wording. Stronger reflection and owner discovery remain B4.
- Both neutral fixture sets (`examples/` and `ai/plans/cli-examples/`) are updated.
  The former example QA-evidence form is now a verification procedure runbook;
  no source verification report is deleted. A fictional lead-qualification
  example proves catalog alias discovery, broad business/engineering discovery,
  topic-filtered exclusion and explicit `any` applicability.
- A scripted compounding fixture captures a signal from a dated verification
  report, prepares a scoped limitation, validates it and closes the activity
  while preserving the original report and unpublished signal. This checks the
  tool/authoring contract for a supplied agent decision; it does not evaluate
  an LLM's semantic extraction quality or prove remote publication.

Checks:

- `uv run pytest -q`: **1,028 passed**.
- `uv run pytest -q tests/unit/domain`: **542 passed**; in-memory domain suite.
- `uv run ruff check .`, `uv run ruff format --check src tests` and
  `uv run mypy`: passed (43 typed source files).
- `uv build --out-dir .cache/b1-dist`: wheel and source distribution built.
- Repository skill validation: **33 skills valid**. The two neutral skills
  also pass the skill-creator frontmatter validator.
- `tests/e2e/fresh-consumer-smoke --output .cache/b1-fresh-consumer.json --keep`:
  passed. Built/installed outside the source checkout, verified exact eight kinds
  and ten installed templates, compiled Codex/Claude/Copilot APM projections,
  exercised setup/repeat setup and hook uninstall/reinstall, signal provenance
  and guarded compounding. Provider events here are adapter fixtures, not live
  model or scheduler proof. Additional installed CLI calls verified topic
  discovery/filtering and rejection of retired names.

Review scope: existing uncommitted fixes and prior plan edits were preserved;
`.cache/b1-baseline/` captures the state before this slice. No commits or pushes
were made for B1. The user waived the B1 review stop and authorized B2 next;
B2-B5 are not implemented by B1. Native scheduling
experiments remain paused, and populated-organization/live-agent semantic proof
retains its existing separate boundary.

## B2: Business onboarding

**Onboarding behavior:** extend the existing `knowledge-setup` skill and its
on-demand references, rather than adding a competing setup skill.

1. Inspect the user's selected workspace and relevant existing configuration,
   catalogs, business/product documentation and local instructions. Reuse
   established vocabulary and identify conflicting or missing context.
2. If needed, ask a short batch of targeted business questions: what the
   business does and for whom, what work agents should help with, and which
   information or rules are shared versus restricted to this workspace.
   Ask only unanswered questions; do not require a standard questionnaire or
   ask the user to invent raw schema IDs.
3. Propose a small initial catalog with descriptions and evidence for its
   scope assignments and topic choices. A solo workspace can start with one
   business scope and one source; do not fabricate squads or group layers.
   Let the user confirm or correct the meaningful business choices together.
4. Register the agreed identifiers, then create or complete the YAML catalog
   and workspace file using the existing contract and path defaults. This
   explicitly handles an empty catalog: replace the present blanket rule that
   stops at every unknown scope with a deliberate proposal/registration path.
   Unknown IDs in ordinary searches must still fail validation.
5. Reuse the runtime/setup helper, `describe`, `context` and `doctor`, and
   validate any authored knowledge. Preserve existing configuration and
   unrelated hooks. Publication stays opt-in; retain the established handling
   for missing Python, authentication and unavailable native scheduling.

The user confirms semantic choices, not generated workspace IDs or routine
runtime/storage paths. Setup may prepare an empty knowledge source; it must
not manufacture business facts to populate it. Compounding uses the same
catalog discipline: reuse a suitable topic, introduce a supported durable
concept with a clear definition only when needed, and keep the catalog change
in the same validated publication state as its document. Conflicting business
context or an unsupported scope expansion requires clarification or retention
of the signal, not guessed applicability.

### B2 implementation and proof (2026-09-14)

Implemented by extending the existing `knowledge-setup` skill; no new onboarding
CLI, metadata schema or alternate setup skill was added.

- Setup reads the business/product context and existing configuration first,
  asks only for missing/conflicting meaning, proposes a small vocabulary with
  evidence, and registers it after confirmation. It no longer requires the
  developer to invent raw scope IDs or treats every absent scope as a dead end.
- Routine IDs/paths, empty sources, runtime and harness defaults remain owned
  by setup. Existing configuration, catalog definitions and user-owned resources
  are preserved. Unknown IDs in ordinary searches still fail validation.
- The on-demand `references/business-onboarding.md` includes business questions,
  vocabulary selection, the catalog/workspace boundary and paired valid YAML
  examples for a solo business. The main skill, package README, root README and
  fresh-consumer guide describe the same flow. The reference also explains
  empty registries and scopes, conflicts, and preserving current configuration.
- `tests/integration/apm/test_business_onboarding.py` validates the actual paired
  examples, starts an empty source, discovers a business topic by its alias,
  and validates/retrieves a workflow with the same metadata contract.
- `tests/e2e/setup_onboarding_acceptance.py` prepares a fresh installed APM
  consumer and stages five Claude Opus 5 turns: proposal, confirmation/setup,
  repeated setup with unrelated vocabulary, a marketing signal/compounding
  workflow, and conflicting context. Deterministic checks and semantic-review
  evidence are separate. This driver must receive the final built wheel when
  run after B5; it does not create or trigger a native scheduler.

Checks: **1,029 tests passed** with `uv run pytest -q`; Ruff lint/format and
Mypy passed; **33 skills passed** repository validation. The skill-creator
validator also accepted the setup skill. A no-model preparation run passed
APM installation/compilation, wheel installation and installed-reference parity
(`.cache/b2-onboarding-prepared.json`).

The initial live attempt was stopped at the user's request during its proposal
turn, before a result was returned; no catalog/configuration had been created.
It is not counted as live proof. Real onboarding proposal quality, repeated
agent setup, conflict handling and the marketing signal/compounding flow were
deferred until the final B1-B5 live run, whose results are recorded below. The fast suite continues to
cover malformed/duplicate YAML, unknown IDs and setup-runtime preservation.
No commits or pushes were made for this slice.

## B3: Incoming links

**Incoming-link discovery:** extend `inspect` with an explicitly requested
incoming view. Preserve the default heading/outgoing-link navigation for a
single selected file. The implemented incoming request is:

```yaml
document:
  source: business-knowledge
  path: product/features/order-history.md
view: incoming
sources: [business-knowledge]
limit: 10
```

Use `view: navigation` as the default and `view: incoming` for references to
the selected document. In the incoming view, `sources` selects the configured
sources to scan for referencing documents; omitting it scans all configured
sources. This selection does not change the identity of the target document
and does not infer applicability from its scope or topics. Reject unknown
source IDs, and reject `sources` on the ordinary navigation view rather than
silently ignoring it.

The incoming view must also accept a safe source-qualified Markdown target
that is now missing, so the old path remains usable after a rename/deletion.
Validate containment and symlink safety without requiring the target file to
exist. Report its absence explicitly, retain referring anchors with unverified
anchor status, and include target absence/presence in the snapshot identity.
The normal navigation view still requires an existing readable document.

Reuse the existing Markdown parser, path resolver and source-boundary guards
to find authored references to the selected source-qualified document. Return
bounded, deterministically ordered referencing-document previews with link
labels, physical reference locations and target anchor/status information.
References to sections of the target still count as incoming document links;
show a missing target anchor as a diagnostic rather than hiding the reference.
Keep same-document section links in the ordinary outline, not the incoming
view. Matching an entity or a text phrase does not create a graph edge.

The initial implementation scans files on demand and keeps its working state
in memory. It reads Markdown internally to locate references but returns no
body prose to the agent. There is no persistent index, background watcher,
recursive traversal, network fetch, automatically authored reciprocal link,
metadata inheritance or automatic rewriting of related documents. An incoming
link does not establish an ACL or a policy override. Measure scan time and
bytes on a representative fixture before considering persistent indexing.

Page incoming results using the existing cursor/snapshot conventions. The
snapshot must cover the target and the selected scan sources, so editing,
adding or deleting a referencing document invalidates a continuation. Report
the actual scan scope and completion state. Unreadable sources, invalid files,
unsafe paths, interruptions or changed scans cannot produce an unqualified
empty incoming result. Optional inspect receipts must describe the requested
view, scanned sources and returned references without claiming body reads or
semantic completeness.

Coverage is explicitly authored Markdown links in the selected sources.
Unconfigured/unselected sources remain outside that coverage. Entity catalogs
also contain `documents` references; incoming Markdown results do not claim
to enumerate those or prove that every reference to a file has been found.

**Authoring and compounding changes:** the shared agent guide owns the
navigation contract; the compounding skill adds a small workflow step and
links to that owner. Teach agents to:

- Add a meaningful authored link when a finding relates to an existing
  concept, feature, workflow, limitation or other owner. Use an informative
  label and keep prerequisite/constraint links close to the relevant prose.
  Shared topic/entity tags are not a substitute for a concrete relationship.
- Rely on incoming discovery for reverse navigation. Do not write a second
  link solely to make the first discoverable in reverse; deliberate links
  in both documents remain valid when both help their readers.
- Inspect incoming references when renaming, retiring or materially changing
  a document could affect its dependants. Read only relevant referencing
  sections; update paths or dependent claims when the evidence requires it,
  preserving each document's independent applicability. Avoid unrelated or
  out-of-scope edits and report unresolved impact.
- Validate affected links and documents in the same effective publication
  state as the compounding update. Check catalog entity `documents`
  references separately when moving or retiring an owner, and repair those
  references when affected. An incomplete incoming scan is not proof
  that there are no dependants. Existing publication and drain safeguards
  remain unchanged.

Incoming-link discovery needs no new hook or setup setting. A future agent
starting at a feature can request its incoming view, discover a limitation that links to that
feature, then inspect/read the limitation without a reciprocal feature edit.

## B4: Reflection and compounding

**Catalog maintenance boundary:** teach this explicitly in the compounding
skill, with the shared guide retaining ownership of catalog/filter semantics.
The catalog YAML registers vocabulary, descriptions, aliases and relations.
`knowledge-workspace.yaml` selects sources, applicable scopes, paths and
runtime/publication settings. Adding knowledge about marketing ordinarily
changes documents and possibly the catalog; it does not require a workspace
edit. New sources, workspace membership, publication settings and wider
organizational applicability remain deliberate setup/configuration choices.

For example, a signal describes an evidenced lead-qualification procedure.
The compounder discovers existing topics, entities and owners, reuses
`lead-generation` or an equivalent if present, and proposes a clearly defined
catalog addition only if needed. Register that addition and its runbook in the
same validated publication state. Preserve evidence and narrow applicability;
do not change workspace settings merely to make the new topic searchable.
An author can record the observation before that registration: signals do not
require a topic. Unclear business meaning or unsupported scope expansion
requires clarification or retention of the signal. Setup establishes the
initial vocabulary; compounding maintains supported additions through the
existing review/publication process.

**Business context and decision history:** preserve the consequential evolution
of business choices so future agents can understand the current approach,
avoid repeating rejected approaches and recognize when reconsideration is
appropriate. This is authored knowledge about decisions and their rationale;
Git remains available for inspecting document edits when source history exists.
A commit timestamp does not establish when a business decision took effect.

For example, an illustrative "Our lead-generation approach" guidance document
states the current choice of Apollo, the supported reasons and trade-offs, and
conditions that would justify reconsidering. An optional "Decision history"
section explains the progression from Pipedrive through solution X to Apollo,
with dates where known and evidence for the reasons behind each consequential
change. Link to the current Apollo runbook for operational steps. These are
example tool choices, not scaffold defaults or claims about the user's actual
business. Do not invent missing dates, motives or evidence.

Teach compounding to update the existing owner when an adopted business
decision changes, preserving earlier reasoning that remains useful. Clearly
distinguish current guidance, historical choices, experiments and proposals;
trying a tool does not establish its adoption. Update or replace the related
procedure so obsolete instructions cannot be mistaken for the current
workflow. Keep meaningful prior decisions in a labelled history section or
linked context, without appending every minor edit or duplicating obsolete
procedures in the active steps. Create a separate document when it has an
independently useful purpose or different applicability, not merely because
another signal arrived about the same subject. Explain that choice in the
compounding disposition or PR.

Normal task retrieval selects the current approach and procedure; an agent
can read the decision-history section when recommendations, alternatives or
changed constraints make it relevant. Use existing descriptions, topics,
entities, ordinary Markdown headings and links. This adds no knowledge kind,
mandatory history section, temporal metadata, automatic historical filtering,
or "as of" query system. History labels guide agent interpretation through the
existing preview/read workflow; the deterministic matcher does not infer
whether a mentioned technology is current or historical.

**Procedural reflection and skill-owner discovery:** replace vague reflection
guidance with explicit steps, while retaining one short, source-owned hook
reminder. Proposed responsibility split:

1. The working agent reviews work already performed for durable discoveries,
   user corrections, misleading/missing knowledge, retrieval misses, and skill
   instructions, references, templates or scripts that caused a failure or
   omission. Routine successes and transient tool failures alone do not
   justify a signal. Reuse relevant discovery from the current session; inspect
   likely advertised skill descriptions and use catalog/search/inspect for
   focused knowledge checks when needed. Distinguish confirmed gaps from
   incomplete searches. Check same-session pending signals and likely bodies
   before recording a new observation, preserve evidence and the exact hook
   session ID, and record nothing when there is no useful finding. Uncertain
   ownership or unavailable discovery must not prevent evidence capture or
   become a claim that no owner exists.
2. The compounder performs the fuller owner-discovery procedure before choosing
   a destination. Review the available skill inventory by name, description
   and source/location, including skills not used by the author. Use the
   harness-provided inventory and accessible package metadata for identified
   source packages; open only plausible skill bodies and relevant attached
   references/templates/scripts. Reuse the inventory across a batch, refreshing
   when its available sources change; do not reload every skill body for every
   signal or user prompt. Report the coverage boundary when the originating
   workspace's skills are unavailable in the compounding harness.
3. Discover the configured knowledge vocabulary with `catalog`, then use
   text searches and canonical filters, previews and selected body reads to
   compare existing knowledge owners. Skill inventory and knowledge discovery
   are complementary: the knowledge catalog/CLI does not index skills. Do not
   invent a skill catalog dimension, a `skill` knowledge kind or a new signal
   hint merely to express a possible owner. Record skill candidates and safe
   source/version references in the existing signal body/evidence where known.
4. Decide whether the finding concerns a knowledge claim, a reusable skill
   procedure, or an applicable always-on or file-scoped instruction. Check the
   actual owner before proposing changes; a description match is only a candidate. A misleading
   skill plus missing supporting knowledge may need linked proposals for both.
   Resolve the authoritative package/repository before a skill change; an
   installed copy or global harness projection is not a canonical write target.
   Catalog/knowledge validation does not validate a skill or its package assets.
   Use native skill/APM checks for authorized package changes. When the source
   or an authorized publication route is unavailable, retain an actionable
   deferred signal/proposal; discovering an external skill owner is not verified
   publication and does not justify draining its unresolved update.

The shared installed guide owns the working-agent reflection procedure and
discovery semantics; `knowledge-compound` owns final owner evaluation and
publication. Hook and compiled discovery instructions point to those owners
rather than copying a second procedure. Broaden the startup reminder beyond
"engineering work" and make reflection explicitly cover durable discoveries
and corrections as well as gaps. Keep the reminder's no-observation outcome,
same-session duplicate check and exact session handle. No catalog contents,
skill inventory or lookup logic is embedded in the hook. Provider events,
single-channel advisory behavior and non-blocking failure semantics remain
unchanged. Stronger instructions are agent guidance, not a deterministic
guarantee of reflection or exhaustive relevance.

**One discoverable always-on instruction owner:** keep the always-on rules
authored by this package in one APM instruction file. The distributed
`knowledge-agent-pack` already has that source at
`packages/knowledge-agent-pack/.apm/instructions/agent-knowledge-discovery.instructions.md`;
extend that owner rather than adding separate global reflection, catalog or
compounding policy instructions. Detailed procedures remain in their installed
guide/skill owners. Organization- or workspace-owned packages should follow the
same one-file convention for their own always-on instructions. Ownership is
per package/workspace; do not merge independently maintained dependencies or
hand-authored consumer instructions into the scaffold package.

Treat global instructions and patterns that apply to all files under the
supported APM semantics as always-on. A wildcard alone does not mean global:
`src/**/*.py`, for example, remains file-scoped. Keep genuinely scoped rules
separate when combining them would widen applicability; make their sources
equally traceable. Do not flatten scoped rules into the always-on file or
create another instruction registry/custom compiler to group them.

Include a concise attribution in the owned compiled content that identifies
the owning package and package-relative authored source, with identifiable
section headings for individual rules. Preserve it through
normal APM installation/compilation into `AGENTS.md`, `CLAUDE.md` and Copilot
instruction/rule surfaces. Resolve the owning checkout using available package
installation metadata; a portable source label must not depend on an author's
absolute machine path or imply that an installed projection is writable source.
Verify the supported APM output rather than assuming it already provides
sufficient provenance.

Teach compounding to inspect the originating workspace's active instruction
sources alongside skills and knowledge when a signal concerns agent behavior.
Trace the relevant compiled instruction to its authoring source, inspect its
applicability and referenced owners, and decide whether to amend, remove, narrow
or move excessive detail into the appropriate guide/skill/knowledge owner.
Within an authorized source, edit that owner and use normal package
reinstallation/compilation to refresh projections. Check that the old text is
absent and the intended text/applicability appears without duplicate copies.
Preserve unrelated consumer instructions; retain the signal when the owning
source or publication route is unavailable. Neither a knowledge search nor
the existence of a generated `AGENTS.md` proves complete instruction coverage.

## B5: Usage receipts and signal archives

**Usage evaluation and tool-owned receipts (accepted):** B5 closes the gap
between the existing optional Python receipt writer and routine agent CLI use.
Today the public CLI does not supply `receipt_path`; its searches therefore
do not create receipts. Compounding writes a coordination log at
`<scaffold>/ai/signals/compound-activity.jsonl`, but that log does not retain
signal bodies, complete discovery responses, owner references or change
evidence. These are implementation gaps to close, not claims that a populated
six-day usage dataset already exists. Earlier R5/H1 optional-receipt checkpoints
remain historical; the following contract supersedes their runtime collection
and configuration boundary for the new core. It preserves advisory hooks,
explicit sources and honest unknown body reads.

All receipts are written by CLI/application/infrastructure code. Reuse the
existing structured requests/responses and compound start/drain/finish calls;
do not ask agents to construct receipt JSON, write report files or narrate every
search. Agents supply only invocation context and the small disposition/evidence
additions described below. Domain code retains pure schema/decision logic;
filesystem writes, timing, serialization and Git evidence reads stay outside it.

**Retrieval receipt contract:** one terminal `knowledge-retrieval-receipt.v1`
JSONL record per `catalog`, `search` or `inspect` call when collection is enabled.
The following illustrates a successful empty search; identifiers, hashes and
measurements are examples rather than live evidence:

```yaml
schema_version: knowledge-retrieval-receipt.v1
event_id: retrieval-8c14
recorded_at: "2026-09-14T10:15:00Z"
context:
  workspace_id: workspace:startup
  harness: claude
  session_id: provider-session-123
  compound_run_id: null
cli_version: "0.1.0"
workspace_fingerprint: "sha256:<digest>"
operation: search
request:
  kind: [guidance, runbook]
  topics: [lead-generation]
  text:
    any: [Apollo]
  limit: 10
response:
  status: ok
  diagnostics: []
  results: []
  total_matches: 0
  returned: 0
  truncated: false
  continuation: null
  fingerprint: "sha256:<corpus-snapshot-digest>"
  scan_status: complete
  page_channel: items
measurements:
  elapsed_ms: 24
  response_bytes: 412
body_read: unknown
```

`response` is the command's complete structured response with the receipt-status
field removed, not a second preview schema. Preserve nonempty previews,
descriptions, facets, file sizes, match/heading/link locations, pagination and
scan diagnostics exactly as returned, including B3 incoming views. Preserve the
structured attempted request and record normal errors/handled interruptions.
When input cannot be parsed, record a null request plus safe diagnostics, not
raw malformed input. If configuration fails before a safe receipt destination
can be resolved, report unavailable collection without guessing a path.

Use UTC timestamps and monotonic duration measurements; define response_bytes
as UTF-8 bytes of the structured response's canonical JSON serialization,
excluding receipt status. These are payload bytes, not tokens or total agent
context consumption. Ordinary grep/editor/body reads remain unknown. Search
result fingerprints identify snapshots but do not reconstruct historical bodies.
Retain a workspace/source/catalog descriptor per workspace fingerprint for
export interpretation; do not copy credentials or transcripts into receipts.

Add explicit global CLI invocation context for `--harness`, `--session-id` and
`--compound-run-id`; keep this separate from query filters. The harness/session
values are caller-supplied provenance, using the exact hook session handle.
Manual or unavailable context is null, never invented, and its absence is an
evaluation coverage limitation. A supplied compound run must resolve to the
selected workspace; its recorded context can supply consistent defaults.
Update the shared guide/compound skill to carry this context on calls, without
adding a per-query purpose/rationale field or making hooks perform logging.
Correlate `validate` results during compounding with the same run as supporting
operation evidence; do not claim that a validation success proves semantic truth.

**Compounding receipt contract:** append `knowledge-compound-receipt.v1` events
for the existing lifecycle operations. Common fields are schema_version,
event_id, recorded_at, context, cli_version, operation and measurements. Context
contains workspace_id, harness, session_id and compound_run_id. Keep the
coordination activity log separate and join it by run ID.

| Operation | Tool-owned record |
| --- | --- |
| compound.start | Selected IDs, original paths/fingerprints and exact archived signal inputs; tool-generated run ID and start time |
| compound.drain | Submitted dispositions, owner/publication references, durable pre-removal intent and actual removal/retention results |
| compound.finish | Explicitly agent-reported overall outcome, tool-recorded finish time and links to the run's earlier evidence |

The terminal drain payload below illustrates the division of responsibility;
it carries the common fields above as well:

```yaml
operation: compound.drain
agent_report:
  dispositions:
    - signal_id: apollo-adoption
      decision: update
      rationale: >
        Updated the existing lead-generation approach after confirmed
        Apollo adoption; retained the earlier decision rationale.
      owners:
        - source: business-knowledge
          path: guidance/lead-generation.md
  publication:
    status: published
    repository: example/startup-knowledge
    pull_request: 42
    commit: "<commit-sha>"
    verification: agent-reported
tool_result:
  drained: [apollo-adoption]
  retained: []
  diagnostics: []
artifacts:
  signal_snapshots:
    - signal_id: apollo-adoption
      path: inputs/apollo-adoption.md
      fingerprint: "sha256:<digest>"
  changes: changes.patch
```

The agent already supplies decision and rationale. Extend those existing inputs
with owner references and applicable repository/PR/commit evidence; supply
before/after revisions when needed to capture a change. Knowledge owners use
the existing source/path identity. Skill/instruction owners use their resolved
package/repository source identity from B4, not a fabricated knowledge kind or
an installed projection. Distinguish a declared candidate/target from one the
tool actually resolved. Required references must have an explicit unavailable
reason when unresolved rather than falsely implying an exhaustive owner search.
Persist the existing decision enum: update, create, delete-retire, keep, skip
or defer. Do not require the agent to repeat its search history in dispositions.

The tool saves exact signal snapshots and captures the declared before/after
patch when the relevant checkout/revisions are safely accessible. Preserve
revision boundaries and report unavailable artifacts explicitly; do not
attribute an entire pre-existing PR diff to this run or fabricate a patch from
the agent's narrative. Publication evidence remains agent-reported unless an
independent check actually runs. Neither receipt writing nor an outcome string
upgrades that assertion into verified publication or merger. Existing
publication eligibility, verification and no-auto-merge rules remain in force.

**Archive before draining:** `compound start` validates and copies each
selected input's complete bytes into its run archive, preserving original
origin/session/evidence data and the original fingerprint. Archive names must
be collision-safe and contained in that run; never use untrusted IDs as raw
paths. Pending-signal inventory must never scan these copies.

Bind drain to a recorded run and its selected snapshots. Before removal,
persist the disposition and drain intent, verify the archive matches the
selected bytes, then repeat the current inbox containment/schema/identity/hash
and disposition/publication checks. Record actual removals, retentions and
errors from the tool operation. Missing/corrupt archives or failed durable
decision writes retain the corresponding inbox signals. Changed, deferred,
foreign, malformed or otherwise ineligible inputs remain pending. No archive
or receipt replaces those safety checks. A partial deletion or interruption
must remain explicit and recoverable; never recreate already removed inputs
or infer success solely from an agent's finish request. A repeated drain must
not silently replace the archived bytes or erase evidence of an earlier attempt.

Update `knowledge-compound` to follow this lifecycle using CLI commands rather
than manual rm/mv/archive steps. The tool performs all copying and logging.
Archived snapshots remain reviewable after successful drainage but are not
canonical knowledge, pending signals or an automatic source of future searches.

**Configuration, storage and export:** setup supplies the following defaults
without adding routine questions about runtime storage:

```yaml
receipts:
  enabled: true
  directory: ./ai/usage
  retention_days: 30
```

Paths resolve relative to the explicit workspace configuration; setup resolves
the durable scaffold location and writes the appropriate path for a consumer
whose config lives elsewhere. Keep usage roots outside canonical knowledge and
signal roots and ignore them in Git. Expose collection readiness through doctor.
Optional diagnostic collection can be disabled, but required archive/disposition
evidence for safe drainage must still be retained; disabling diagnostics never
restores unarchived signal deletion. Explain this distinction in setup/describe.

```text
ai/usage/
  retrieval/2026-09-14.jsonl
  compound/compound-72/
    events.jsonl
    inputs/apollo-adoption.md
    changes.patch
```

Use complete, serialized JSONL appends under concurrent CLI calls, immutable
input snapshots and safe artifact writes. Retrieval logging failures report a
receipt diagnostic without changing a successful retrieval outcome. Mandatory
archive/decision durability failures retain signals as described above.
Recognize incomplete/torn records and preserve evidence rather than treating
them as successful events. Apply retention with normal CLI use or explicit
maintenance, not a new scheduler. Never age out evidence needed by active or
unresolved runs; retention of completed runs starts at completion. The existing
coordination log has a bounded reader: prevent its historical growth from
eventually blocking runs, preserving unresolved state and linked retained
history when archiving completed records. Do not turn it into the analytics log.

Add a structured `usage export` CLI operation, advertised by describe and the
installed guide, for the chosen UTC interval (since inclusive, until exclusive):

```yaml
since: "2026-09-08T00:00:00Z"
until: "2026-09-14T00:00:00Z"
destination: /work/startup/usage-review-september-8-13
```

The export is scoped to the explicitly configured workspace; sharing a usage
directory does not implicitly include other workspaces' records or artifacts.
It produces a portable local directory of selected events, related
run context/artifacts, version/catalog descriptors and a machine-readable
summary/manifest with checksums and coverage diagnostics. Include relevant
run-start context even when it precedes the interval and label such supporting
records. Preserve the source files and reject unsafe/overwriting destinations.
Report missing/expired evidence, partial records, absent session IDs and
unavailable source versions; no records does not prove no activity occurred.
Do not upload automatically, claim full historical corpus replay from hashes,
or include unrequested transcripts. Summaries report counts, durations, errors,
pagination and dispositions, not inferred relevance scores. Quality evaluation
still needs reviewed examples or human assessment; this slice adds neither a
semantic judge nor an automatic optimizer.

## Implementation notes

**Suggested slices:** B1 delivers the topic and guidance renames and removes
the QA-evidence kind. Update domain models/validation, catalog discovery,
search/inspect previews and serialization, signal kind hints, `describe`,
installed template filenames/contents, guide/CLI examples, compounding
instructions, package resource lists and fixtures together. Refresh active
kind/template counts and links so they describe the eight-kind taxonomy.
Reject the old field/kind names; add no aliases, compatibility reader or
automatic migration. Historical plan checkpoints and inherited reference
packages remain history, not consumers to retrofit. Broaden template and
activation wording where it assumes every task has a service, deployed
revision or engineering rule; a field rename alone
does not teach business use. Signals gain no mandatory topic field merely for
symmetry. B2 adds the assisted catalog/bootstrap
flow to setup and proves it in a fresh consumer. A broad port or creation of
marketing skills is separate work; a small illustrative marketing skill may
be used only as a disposable acceptance fixture.

B3 adds incoming inspection, its discoverable CLI contract/examples, source
scan/pagination behavior and the focused compounding guidance above. It reuses
the topic-aware previews from B1; it has no dependency on B2's business
interview behavior. Keep pure request/edge decisions in `domain`, coordination
in `application`, and file scanning/resolution in `infrastructure`. Do not
introduce a graph database or another agent-facing guide.

B4 adds the procedural reflection and skill-owner discovery instructions,
the short shared reminder changes, the explicit catalog-maintenance example,
the single always-on owner/provenance and instruction-maintenance contract,
and business decision-history authoring/compounding guidance with an optional
section in the relevant template/example.
It depends on B1's vocabulary and can proceed independently of B2 onboarding
and B3 incoming inspection. Update the existing guide, compound skill, reminder
resources and discovery instruction together, with fresh installed-resource
proof. It does not add a skill search engine, broaden external package write
authority, port marketing skills or extend publication to arbitrary repos.

B5 is the final usage-evaluation slice after B1-B4. Deliver automatic CLI
receipts, correlation context, richer compounding dispositions, archive-before-
drain, safe retention and date-range export together. Update pure domain
contracts/tests, application coordination, infrastructure receipt/archive/Git
adapters, CLI describe/examples, setup defaults/doctor and the compound skill.
Prove the fresh installed package and archive/export workflow before handing
the scaffold to the user's real-agent evaluation. Keep tool-owned observations
separate from agent assertions throughout. The user authorized this build;
previously paused scheduling experiments remain outside this work.

## Verification

**Proof:** retain existing filter truth tables and add neutral engineering and
marketing guidance examples, including broad discovery and focused exclusion.
Verify that knowledge/search/signal-kind validation accepts `guidance`, rejects
`operating-rule` and `qa-evidence`, and reports exactly the eight supported
kinds. Verify rejection of the old `engineering_concerns` field, preserved
guidance applicability rules and consistent installed templates/guide output.
A compounding fixture must extract a supported durable conclusion from a dated
verification result, retain its evidence citation and conditions, and preserve
the original report without creating a QA-evidence document. Exercise
empty-catalog startup, an existing catalog, contradictory documentation,
duplicate identifiers, repeated setup and preserving user-owned configuration.
The real-harness onboarding scenario starts with a short fictional business
brief and no registered organization; it must propose meaningful values,
obtain the scripted user's confirmation, write valid catalog/configuration,
discover the marketing workflow and use the same signal/compounding contract.
Record semantic proposal quality separately from deterministic schema checks.
For B3, test a limitation-to-feature link discovered from the feature alone,
cross-source and section-target references, repeated links, same-file section
links, cycles, external links, malformed/unsafe paths, missing anchors,
unavailable scan sources and changed snapshots between pages. Preserve the
ability to discover dangling references to a missing old path, with target
creation/removal invalidating continuations, and verify catalog-reference
checks in the rename/retirement workflow. Preserve the
default inspect behavior and absence of authored reciprocal mutations. A
disposable live-agent case must find and read the relevant limitation through
incoming inspection without being given the limitation's path; a compounding
case must repair affected references on a controlled rename/retirement while
leaving unrelated documents and applicability unchanged. This can use the
existing neutral fixture/provider drivers and does not require a real PR.
Provider scheduling and real GitHub publication proof remain their separately
identified follow-ups; this proposal does not restart those tests.

For B4, use disposable skill inventories with a relevant owner absent from the
signal's wording/links but discoverable by its description, plus unrelated
skills that should not have their bodies loaded. Verify that the compounder
discovers that owner and inspects its relevant template/reference, searches
knowledge through the CLI, and records a supported disposition. Cover an
already-covered observation, a same-session duplicate, no useful observation,
and an unavailable originating skill source that remains deferred rather than
being treated as absent or drained. A marketing case must reuse an existing
topic or prepare a justified catalog addition with its document, validate both,
and leave workspace settings unchanged. Check native skill validation and
installed guide/reminder binding; use the existing live Claude driver to
exercise the working-agent reflection flow and manual compounding separately.
Report observed model choices separately from deterministic contract checks;
retain capability-gated provider checks without restarting scheduled jobs.
Also verify one authored always-on instruction for the distributed package and
portable attribution through each supported compiled target. A controlled
instruction amendment/removal must be traceable from compiled text to the
source, survive reinstall/recompile without stale or duplicate owned text,
and leave unrelated hand-authored instructions and file-specific applicability
unchanged. An unavailable external instruction source must remain an explicit
deferred disposition. Do not use inherited organization-specific projections as proof of the
new package's ownership or import them into fresh-consumer fixtures.
Exercise successive business-choice signals against an existing guidance
owner: preserve evidenced prior rationale, distinguish a trial from adoption,
update the current choice and linked procedure after confirmed adoption, and
avoid creating a parallel guidance file for each change. A retrieval example
must distinguish "run a campaign using the current approach" from "why did we
leave Pipedrive?", selecting current instructions for the former and historical
rationale for the latter without treating obsolete steps as current guidance.

For B5, test the installed CLI rather than only direct Python calls. Cover
nonempty/empty/invalid retrieval, pagination, incoming inspection, preserved
response metadata, known/unknown invocation context and correlated compound
search/validation calls. Check measured units, unavailable destinations,
concurrent appends, corrupt/partial records and honest logging-failure behaviour.
No receipt may claim ordinary file reads or semantic completeness.

Exercise start -> snapshot -> decision -> drain -> finish -> export in a fresh
consumer, asserting exact original signal bytes remain accessible after the
inbox is cleared and archives never appear in pending inventory. Cover missing
or corrupt archives, edited/replaced inputs, duplicate IDs from different paths,
unavailable source revisions, partial drainage, interrupted/retried writes,
forged finish counts, foreign-run context, symlink/path escapes and retention
around active/unresolved/completed runs. Verify no eligible inbox deletion can
occur without its durable input/disposition evidence, and published versus
agent-reported outcomes stay distinct. Include coordination-log rollover without
losing active state or blocking future runs at the current read-size limit.

Use a controlled multi-day fixture for export boundaries, missing/expired
artifacts, shared usage directories and a run that crosses the interval. The
export must let a reviewer trace an original signal to its searches, disposition,
available patch and actual drain result without opening the original inbox.
Use the existing live Claude driver for a manual agent scenario proving it
calls the skills/CLI and the tool creates receipts/archives automatically;
reuse capability-gated Codex/Copilot checks and report their evidence limits.
Do not restart native scheduling or real GitHub publication experiments for
this proof. Deterministic collection tests and observed model behaviour are
separate evidence; production retrieval/compounding quality remains the next
user evaluation against populated usage and reviewed examples.


## B3-B5 build evidence (2026-09-14)

B3 implements explicit `inspect view: incoming` with safe missing targets,
per-reference previews, target anchor diagnostics, truthful scan scope and
snapshot-bound pagination. The existing direct navigation remains the default.
Focused proof: 123 tests; incoming measurement scans 400 files/3.29 MB across two
sources, finds 40 references and returns a first page of 10 (~13.3 KB). Three
runs averaged 5.50 seconds under concurrent local work. See
`.cache/b3-incoming-measurement.json`; this is an on-demand scan measurement,
not a semantic retrieval-quality score or enterprise-scale benchmark.

B4 updates the installed guide, one shared reflection reminder, compound skill
and its owner-discovery/business-decisions references, portable source
attribution and illustrative history. Forty focused tests, skill validation and
an isolated source amendment/reinstall/recompile across Codex, Claude and Copilot
passed. `.cache/b4-instruction-ownership.json` verifies no stale/duplicate owned
text, preserved independent consumer instructions and file-scoped applicability.
This is APM projection proof; the separate live model results appear below.

B5 replaces the optional Python-only receipt API with automatic terminal CLI
collection, global invocation context, mandatory archived compound inputs and
drain intents, tool-derived removal counts, daily conservative retention and a
workspace-isolated local export. Configuration defaults are surfaced by setup,
context, describe and doctor. No legacy receipt API or manual archive workflow
is retained. Write drainage requires concrete agent-reported publication evidence
in addition to the existing explicit verification assertion and owner references;
missing/unresolved evidence retains the input. Native scheduler and GitHub
publication experiments remain paused.

Integration review found and repaired body-supplied run provenance bypass and
uncollected argument errors after recognized commands/configuration. Regression
tests exercise both. Final test counts and real-harness evidence are recorded
below. The implementation was left uncommitted for review; the user subsequently
authorized committing it and integrating it onto `main`.


### Final deterministic and installed verification

- `uv run pytest -q`: **1,192 passed** (160.99 seconds). Subsequent live-driver
  assertion/resume fixes passed **23 focused driver tests**, including 11 new
  tests after that full run. No runtime behavior changed afterward.
- `uv run ruff check .`, `uv run ruff format --check src tests`, `uv run mypy`
  (49 source files), `git diff --check`, wheel/sdist build and all **33 skills**
  pass validation.
- `.cache/final-pass-fresh-consumer.json`: **ok**. Fresh wheel/APM install,
  all three projections/hooks, runtime reuse/recovery, exact session signal
  capture, start/archive/drain/finish and local usage export pass. CLI startup
  checks passed for Codex 0.154.0, Claude Code 2.1.236 and Copilot CLI 1.0.83.
  Provider payload fixtures are deterministic; CLI startup is not authenticated
  model execution.
- The installed smoke driver now resolves macOS temporary paths before using a
  safe export destination and matches the new reminder's quoted guide section.
  These repaired fixture assertions preserve the production safety checks.

### Final live Claude verification

All three scenarios passed with Claude Opus 5 / Claude Code 2.1.236:

- `.cache/final-pass-claude-hooks.json`: live startup/resume discovery and prompt
  reflection used the provider-supported context channel. The model copied the
  exact hook session ID into a signal, listed/inspected it on resume and left it
  unchanged without recording a duplicate. An intentionally failing hook remained
  advisory and the model completed its task. Consumer settings were preserved.
- `.cache/final-pass-onboarding-resumed.json`: business proposal, confirmed setup,
  repeated setup, marketing compounding and conflicting context passed. The
  proposal used one business scope, testing/lead-generation topics, two evidenced
  entities and empty technology/environment registries. Reviewing the fictional
  brief against the authored workflow confirmed its fit-check, evidence and
  exclusion behavior. User-owned vocabulary/comments survived repeat setup.
  The workflow was validated and retrieved, the original compound run was closed,
  and its unpublished signal retained byte-for-byte. Conflicting draft sharing
  instructions led to clarification and a retained signal, with no scope/config
  expansion. Additional observations were preserved for compounding.
- `.cache/final-pass-acceptance-resumed.json`: the model discovered a limitation
  from the feature's incoming references, read it, renamed the feature and repaired
  both the Markdown reference and catalog entity path. It discovered the relevant
  skill by description and updated its authoritative export-checklist reference.
  An unavailable external owner stayed deferred; an already-covered observation
  drained with its exact archive intact. Pipedrive remained current during the
  Solution X trial. Confirmed Apollo adoption updated the existing guidance and
  linked procedure, preserved prior rationale and invented no effective dates.
  The final read-only answer correctly separated current campaign steps from
  historical rationale and recorded no duplicate/new signal.

The business-history export contains **31 events**: 18 retrieval receipts and 13
compound/validation events, including two completed runs and one actual removal.
All five selected signal inputs remained available as exact archives; manifest
checksums and context descriptors verified. No event lacked its session ID.
Ordinary body reads stayed `unknown`; unavailable source Git revisions produced
explicit coverage diagnostics. The model called the CLI; it did not author the
receipts or archives. No remote publication was claimed.

The initial live attempts exposed test-driver constraints: valid relative
launcher/config paths rejected by absolute-spelling assertions, an overly literal
reference-word assertion, and onboarding's initial $2 per-turn budget cap.
Driver corrections have focused regression tests. Hooks were rerun in a fresh
consumer; the other scenarios resumed their existing sessions with prior logs,
signal bytes and completed phases preserved. The original failed reports and
budget-exhausted provider turn remain failed evidence in the resume history;
they are not relabelled as successful turns. Continuations used a bounded $4 cap.

These are observed model choices in controlled fictional consumers, reviewed
separately from deterministic schema/storage checks. They do not establish
retrieval or compounding quality for a populated organization. Codex/Copilot have
APM, provider-event and CLI-startup proof here, not authenticated model proof for
this final pass. Native scheduling and real GitHub publication tests remain
paused. Reproducible commands are in
[`docs/r8-harness-proof.md`](../../docs/r8-harness-proof.md#final-pass-harness-checks).

### Clean-slate packaging follow-up (2026-09-14)

After B1-B5, the user requested a clean reusable scaffold before separately
selecting skills to port. The three inherited package trees and their 32 extra
skill definitions (including the repository-local smoke skill) have been removed.
Only `knowledge-setup` and `knowledge-compound` remain. Their runtime, resources,
templates and provider-hook behavior are unchanged.

Removed the old marketplace/release tooling, obsolete setup guides and diagnostic
plans, and stale generated projections. Preserved the core plans' applicable
lessons with neutral terminology and current source references. Repository
instructions now have one neutral source, and APM regenerated its lock and
Codex/Claude/Copilot projections from the current package. Prior ignored build
caches and review evidence were preserved outside this checkout. No other
repository or global harness installation was changed.

The replacement CI runs the current core gates and isolated fresh-consumer
proof, with no marketplace publication step. A package inventory regression
check and fresh-install assertion require only the current package/skills;
environment-isolation fixtures use neutral names.

Verification: **1,204 tests passed**; Ruff lint/format, Mypy (49 source files),
wheel/sdist builds, workflow validation with actionlint 1.7.7 and
`git diff --check` passed. `.cache/neutral-cleanup-fresh-consumer.json` reports
successful fresh wheel/APM installation, setup/recovery and provider fixtures.
Source, documentation, filenames and generated local projections were scanned
for the removed organization and industry terminology with no remaining matches.
Git history and third-party runtime dependencies are not rewritten by this
source cleanup. Authenticated model and native scheduling tests were not rerun.
