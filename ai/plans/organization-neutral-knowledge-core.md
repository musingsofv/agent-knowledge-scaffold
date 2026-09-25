# Organization-Neutral Knowledge Core

**Date:** 2026-09-09 (updated 2026-09-11)
**Status:** R1-R8 implementation slices and the package/test folder refactor are complete on `main`. R1-R5 and the refactor were accepted through `02e9a27`; R6-R8 were then integrated, followed by the provider-hook follow-up H1-H4 and the installed-launcher correction in `290373d`, which is pushed to `origin/main`. The core plan deliberately leaves broader skill ports and retrieval-quality evaluation against a real organizational corpus as follow-up work. Later cross-harness verification live-proved semantic retrieval in all three CLIs and one Codex Scheduled compounding run. Copilot CLI scheduling is session-scoped and therefore does not satisfy the durable unattended automation requirement; see `docs/harness-support.md`. R4 domain timings and the latest full-suite evidence remain recorded below.
**Repo Scope:** agent-knowledge-scaffold
**Primary PR Repo:** agent-knowledge-scaffold
**Current follow-up:** [Knowledge Scaffold Final Pass](knowledge-final-pass.md) owns B1-B5; use it for current work.

## Table Of Contents

1. [Plan Brief](#1-plan-brief)
   1. [Outcome](#11-outcome)
   2. [Feature Shape](#12-feature-shape)
   3. [Capabilities Delivered](#13-capabilities-delivered)
2. [Build Contract](#2-build-contract)
   1. [Delivery Slices](#21-delivery-slices)
   2. [Implementation](#22-implementation)
   3. [Deployment](#23-deployment)
3. [Appendix](#3-appendix)
   1. [Context Used](#31-context-used)
   2. [Additional Notes](#32-additional-notes)

## 1. Plan Brief

### 1.1 Outcome

Within a repository that shares both APM skills/packages and organizational knowledge, a new organization-neutral core lets agents discover relevant context through explicit searches and provides the same predictable, independently tested contract for compounding and skill integrations.

### 1.2 Feature Shape

#### Today

The new scaffold contains copied APM tooling and skills but deliberately contains no organizational knowledge corpus. At inspection, main's implementation was the initial scaffold commit `955b171`; completed stabilization work remained on separate worker branches. The lookup implementation combines query interpretation, route selection, scoring, file access, fact extraction and receipt side effects. Its preview helper accepts Markdown and standalone YAML and falls back to a second permissive parser after parsing errors. Many existing lookup tests launch subprocesses and construct temporary files even when the behavior of interest is matching.

The prior diagnostic identified excessive body consumption, brittle broad queries, duplicated instructions, weakly scoped signals and publication friction. Stabilization workers have addressed several independent defects. Their branches and tests are reference material, not a foundation the new runtime must inherit. Stabilization S8 (advisory activity log) and S9 (accumulating user knowledge PR) have not been completed in the inspected branch set; this plan does not report them as complete or automatically resume them.

The user clarified during planning that the existing implementation was an experiment and explicitly allowed starting anew. Build a fresh Python retrieval package instead of extending the existing route/scoring implementation. This is not a rewrite of the whole APM repository: retain useful knowledge-template structure and proven safety behavior. Organizational sources, scope membership and approved technology choices are data, not organization-specific logic. The latest scope includes usable fresh retrieval, first-run setup and on-demand compounding; selective ports of other existing skills are a separate story.

#### Planned Delta

The agent receives a compact schema and its configured workspace context, discovers unfamiliar names through text/catalog lookup, and sends explicit filters. Independent searches can run in parallel through the harness. The tool matches those predicates and returns descriptions, applicability and navigation information. The agent selects files, reads complete files or ordinary line ranges, and follows useful links progressively. There is no fixed search count, compulsory pass matrix or tool-generated search plan.

Canonical knowledge and individual signals use Markdown with YAML frontmatter. They share one strict format reader/writer, with separate document schemas because their meanings differ. Catalog and workspace configuration remain YAML using the same YAML loader; activity logs and receipts remain runtime records, not authored knowledge. No standalone YAML knowledge/signal compatibility reader or migration utility is required for this new repository.

The first-run path is a separate `knowledge-setup` APM skill. It asks only for the absolute workspace configuration path and registered applicable scope IDs; derives or scaffolds the remaining local paths and identity; creates or reuses the scaffold-local virtual environment; installs the CLI and its dependencies; runs `describe`/`doctor`; compiles all three supported APM targets; and registers or updates one native scheduled automation per available provider and signal store. The automation invokes the `knowledge-compound` skill on its cadence. Setup may write a local, ignored environment/bootstrap file for the harness, but every CLI operation still receives an explicit `--config` path and the core never relies on ambient variables.

A separate Python module named `domain` inside the new `agent_knowledge` package owns the deterministic rules. It accepts values and returns values without reading files, consulting environment variables, running Git, writing receipts or invoking an agent. Thin adapters handle serialization, filesystem boundaries and CLI output. Most semantic tests run directly against the domain in memory. Reuse a proven old helper only when its responsibility fits this boundary; do not import the old package's routing, globals or initialization behavior.

The repository remains an APM catalogue and distribution source for shared skills/packages as well as a knowledge store. The Python core is one component of that repository. Root APM manifests, repository-local `.apm/` primitives, distributable `packages/` and catalogue/release tooling remain first-class surfaces. They are not temporary directories to remove once the CLI works.

This plan owns the fresh core, file/catalog contracts, adapted knowledge-authoring templates, signal capture, validation, an agent-facing guide, a first-run `knowledge-setup` skill, and the `knowledge-compound` skill needed to use it from a new installation. On-demand compounding includes the agreed advisory activity log, current-user knowledge PR reuse and verified disposition before draining. The setup skill provisions the local runtime and registers a visible native harness automation; the repository does not implement a scheduler. Broader existing-skill ports and optional harness hooks remain separate work. Completed worker changes have been consolidated on a separate reference branch, without making that legacy runtime a dependency of the new Python package.

#### Must Preserve

- The scaffold is empty of organizational knowledge. Use neutral examples and temporary fixtures; do not copy the organization-specific corpus into it.
- Agent judgment owns query planning, relevance assessment and stopping. No embeddings, retrieval-side model, automatic coverage-completeness engine or mandatory compaction replay.
- All knowledge kinds use one matching contract. Operating rules do not get a second retrieval system.
- Preview is not a body read, and neither search nor reading proves semantic completeness.
- Ordinary files and harness grep/read tools remain the reading interface. No chunk database, persistent section identifiers or per-section applicability schema.
- Scope describes applicability; source describes storage; entities describe the named things discussed. Origin is provenance, not automatic applicability.
- Preserve the useful safety behavior demonstrated by stabilization: durable inbox placement, unique signal files, canonical-path protection, symlink safety and preservation of changed/unpublished inputs. Reimplement or reuse the smallest correct mechanism in the new package.
- Preserve the APM package/distribution structure alongside the new core. Keep one concise usage-contract owner, slim bootstrap, short skill descriptions and single-channel hook behavior when existing skills/hooks are adapted.
- The new scaffold has no legacy compatibility requirement. Earlier compatibility, pointer migration, organization-specific publishing destinations and automatic retrieval-pass proposals are superseded by this plan and the user's decisions.
- Full organizational onboarding automation, broader existing-skill/package ports, optional harness hooks, remote source synchronization and a dedicated runtime-topology query engine are outside this plan. The first-run runtime/harness setup, native scheduled-job registration and on-demand knowledge PR publication/draining are included. Scheduling remains a harness responsibility: there is no repository daemon, scheduler service or autonomous PR merging.

### 1.3 Capabilities Delivered

| Status | ID | Capability | Expected Behavior | Important Conditions | Proof Signal |
| --- | --- | --- | --- | --- | --- |
| - [x] | C1 | Independently testable domain | Validation, normalization, identifier resolution and matching run as pure functions over typed values. | No filesystem, environment, network, subprocess, clock or receipt side effects in `domain`. | Direct unit tests, import-boundary check and measured fast-suite runtime; R1 evidence below. |
| - [x] | C2 | Discoverable vocabulary and context | The agent obtains its configured scopes/sources and searches catalogs for canonical IDs and technology families. | Unknown IDs are errors; ambiguous names remain candidates; no invented organizational membership. | Neutral multi-source catalog/context fixtures, conflict and ambiguity cases; R2 CLI and isolated-wheel proof below. |
| - [x] | C3 | Selective deterministic search | Explicit facet and text predicates produce matching previews or a valid empty result. | Same-field OR, cross-field AND, explicit `any`, explicit families; no weak-result padding or hidden filter broadening. | Truth tables, algebraic properties, alias cases and CLI contracts. |
| - [x] | C4 | Progressive file and link navigation | Results provide source/path, description, size, fingerprint and physical line/section locations; selected files expose outlines and links. | No automatic body loading or recursive graph expansion; stale and unresolved references are visible. | Large-runbook section tests, Markdown edge cases, direct-file preview and linked-file walkthrough. |
| - [ ] | C5 | Consistent knowledge authoring | A writer resolves originating context, searches existing owners and uses adapted knowledge templates validated against shared catalogs and applicability rules. | No automatic promotion from origin to broader scope/family; useful existing body structure is preserved and organization-specific assumptions removed. | Populated template fixtures and validation using the same domain as search. |
| - [ ] | C6 | One authored file format | Knowledge and one-signal-per-file inbox entries use Markdown with YAML frontmatter through a shared codec. | Different schemas, strict parsing, original line positions and signal byte fingerprints; no silent legacy YAML acceptance. | Codec tests, signal capture/discovery/consolidation tests and canonical-tree rejection. |
| - [x] | C7 | Honest core trace | Optional receipts distinguish search/inspect events and retain navigation provenance. | The standalone core does not observe ordinary harness reads and records that as unknown; no inferred coverage. | Receipt-adapter tests, including unwritable logs and absence of body-read claims. |
| - [x] | C8 | Usable fresh installation | One core guide and minimal neutral APM instructions teach setup, discovery, filtering, partial reads, graph exploration and template use. | Examples are executable contract fixtures; installed resources resolve without private source paths. Broader skill ports are separate. | Standalone CLI smoke plus fresh APM consumption/compiled-harness invocation proof. |
| - [ ] | C9 | Evidence of useful retrieval | Neutral acceptance cases and selected real-corpus walkthroughs assess evidence discovery and context consumption. | No unsupported claim of tribe-scale performance or superiority; source annotations for evaluation are not runtime migration. | Expected-evidence cases, comparative consumption report and isolated package gates. |
| - [x] | C10 | Quick readiness diagnosis | The agent can check the running CLI/runtime, explicit configuration, catalogs, source access and signal-storage setup from its actual harness process. | Quick read-only default; no launchctl dependency, environment mutation or automatic repair. Optional write mode probes only validated signal storage. | Healthy/misconfigured/minimal-environment cases and installed-CLI doctor smoke; no full corpus scan in the default check. |
| - [x] | C11 | On-demand compounding | A minimal neutral skill processes pending signals, updates existing knowledge owners, validates changes and reuses or creates the current user's eligible knowledge PR. | Advisory activity log; normal main merge; no force push or automatic PR merge. Drain only selected unchanged inputs after verified publication or explicit no-update disposition. | R7 unit/integration tests and fresh-consumer workflow proof cover PR eligibility, advisory lifecycle, disposition gates, publication uncertainty and guarded cleanup. Authenticated provider publication remains an R8 proof concern. |
| - [x] | C12 | First-run setup and harness automation | A neutral setup skill asks for the absolute workspace configuration path and registered applicable scopes; it derives or scaffolds the workspace identity and local paths, creates or reuses the scaffold-local virtual environment, compiles all three supported APM targets, validates explicit configuration and registers or updates a native automation for each available provider that invokes `knowledge-compound`. | No secrets captured, no shell-startup mutation, no implicit cwd/environment configuration, no duplicate automation for one signal store, and no repository scheduler. Setup is repeatable and leaves a visible pause/remove path. | R7 package/skill contracts, setup-helper repeatability and three-provider startup/projection proof establish the implementation. Authenticated native registration/run-now/pause/remove remains an R8 proof concern. |

## 2. Build Contract

### 2.1 Delivery Slices

**Execution agreement:** the user authorized building directly without an additional build-orchestration skill, one slice at a time, stopping for their review between slices. R1-R4 were accepted and published through `6d25fba`, the package/test folder refactor was accepted before R5, and R5 was accepted and published at `02e9a27`. R6, R7 and R8 are now integrated on `main`; the subsequent H1-H4 hook follow-up and installed-launcher correction are also on `main` at `290373d`. The remote `main` ref was verified after the latest push. Historical worker and stabilization branches remain reference material and are not missing implementation from the current plan.

**Legacy reference work, not a prerequisite:** completed stabilization changes can be consolidated in a separate worktree/branch while this plan is reviewed. Preserve the main checkout's existing brainstorm modification. Keep the legacy source/projection consistency checks within that branch; do not import a corpus or copy the old runtime wholesale into the new core. This is preservation of useful work for later selective porting, not construction of the new retrieval runtime.

| Existing slice | Inspected tip | Integration note |
| --- | --- | --- |
| S1 baseline | `30f4f3e6b7ba12a9fbb7bedaa39228cad5e64157` | Already in the ancestry of S4. Preserve isolated baseline/evidence behavior. |
| S2 instructions | `84ebad69c9fc771553a9cf8cad0f4abb0bc7dbef` | Already in S4 ancestry. Owns the slim bootstrap and shared discovery reference. |
| S3 hook delivery | `852c759acc5ed90284dba2d63cb14ad074b30007` | Includes installed-consumer smoke. |
| S4 skill contracts | `a93a329b3fe9749ee4ddb19a608ac9e19656a324` | Includes S1/S2; description edits overlap S7's skill edits. |
| S5 signal safety | `05c0a8ef5b207fbd9d4b776d2fa9edf00ca6b7bf` | Final validator fix also exists as equivalent cherry-pick `e5d1e74` in S7; compare patches instead of double-applying. |
| S6 limitations | `3c9983ca70a5ce7f59f3db92c7e1f693ffe7e07f` | Canonical limitations only; no issue aliases or migration. Reconcile S7's older write-contract prose. |
| S7 durable inbox | `d8a7b955c6113cbb3dcc93e76755e0c1d4668ed9` | Safety/provenance behavior and tests inform R4. Its old YAML serializer and package coupling are not carried into the new core. |

Reference consolidation is now complete locally on `stabilization/integrated-reference`, commit `74c282113b77f7ba07c4547fe7341d5764dd26b1`, in a separate worktree. It integrated S4, S3, S7 and S6, accounting for ancestry and S5's equivalent patch. See the [integration report](/Users/nikv/code/.worktrees/agent-knowledge-scaffold/legacy-integration/ai/evidence/legacy-integration/integration-report.md) for checks and remaining corpus/APM-version proof limits. It was not merged into main or pushed. These branches remain useful for selective template/instruction reuse and safety/test evidence; there is no wholesale integration prerequisite for the fresh runtime.

S8/S9's behavior is delivered by this plan's new on-demand compounding workflow, rather than building a second legacy implementation to satisfy the obsolete sequence. No separate YAML migration or compatibility work is needed.

#### Stabilization Lessons Carried Into This Plan

The reference branches are evidence for requirements, not merely links to old code. The following obligations belong to the named delivery slices even when the implementation is rewritten. S1-S7 have consolidated implementation evidence; S8/S9 are previously agreed workflow requirements, not completed branch fixes. A builder must demonstrate the relevant behavior in the new installation before marking its capability complete.

| Earlier work / failure mode | Requirement carried forward | New owner and acceptance evidence |
| --- | --- | --- |
| S1: context consumption and improvement claims without a comparable baseline | Measure always-loaded instructions, skill descriptions and delivered messages as well as search previews/body reads. Record revision, workload and units; bytes/words are not exact tokens without a pinned tokenizer. | R6/R8, C8/C9: fresh-consumer measurements and the same expected-evidence cases before/after. Legacy synthetic passes do not prove new retrieval quality. |
| S2: duplicated global/workspace instructions and stale projections | One source-owned bootstrap delegates detail to the installed guide. Verify normal global/workspace composition does not deliver the same discovery contract twice. Preserve hand-authored files; a different build ID alone is not proof of drift. | R6, C8: isolated consumer compilation/composition fixtures, source/resource parity and ownership-aware diagnostics. Do not add a broad instruction cleaner or silently delete unrelated configuration. |
| S3: one reminder sent through multiple channels | Initial fresh installation introduces no legacy hook registrations. If hooks are added in their later story, each invocation delivers through one supported agent-context channel and preserves the chosen remind/allow behavior. | R6 proves the initial package has no accidental legacy hooks; later hook work must carry installed-consumer and single-delivery tests. This does not reintroduce old receipt suppression or a hook framework into this plan. |
| S4: descriptions grew into always-loaded manuals | New minimal skills and later retained skill ports keep descriptions within 40 whitespace-delimited words and retain useful invocation boundaries. Long instructions/templates belong in their on-demand owners. | R6/R7, C8/C11: description boundary validation plus positive/near-miss invocation examples for the new package. Word-count validation alone does not prove routing quality. |
| S4: duplicate reference prose contradicted its policy/setup owner | Keep the common guide as the mechanical-contract owner and check source, installed examples and templates for contradictory instructions. Use the installed launcher; setup failures must not route through private package paths. Do not convert organization-specific factory/test policy into a default for every organization. | R5/R6, C5/C8/C10: semantic review of adapted content, executable examples and launcher-failure smoke. Organization-specific policy remains configurable authored knowledge or a later selected skill port. |
| S5: permissive schema checks and signals leaking into canonical knowledge | Reject malformed/foreign schemas and invalid IDs/links; a signal in a canonical root is an error. Capture remains brief, uses safe evidence references and never triggers full compounding. | R1/R2/R4/R5, C2/C5/C6: positive/negative codec and content fixtures, foreign-signal rejection, canonical-tree protection and isolated test roots. |
| S5/S7: signal loss, unsafe paths and temporary-worktree inboxes | Unique Markdown signal files use durable origin, not the publishing worktree; protect canonical roots even when absent, and reject unsafe traversal/symlink aliases. Preserve malformed, unreadable, edited and newly added inputs. | R4/R7, C6/C11: nested projects, equal basenames, linked worktrees, missing roots, outside-code-root origin, collision and replacement-race cases. An unresolved project association is reported rather than guessed. |
| S5/S12: compounding was not reliably triggered after a task ended | A first-run setup skill provisions one visible native harness automation per signal store. Signals carry safe originating harness/session handles when available so the scheduled agent can attempt a handoff; a self-contained signal remains sufficient when the session is unavailable. | R7, C11/C12: setup is repeatable, the automation is discoverable/pausable, run-now invokes the compounding skill, and session-aware handoff falls back safely. No repository scheduler, callback dependency or transcript copy. |
| S6: inconsistent issues/limitations naming across readers, writers and templates | Use `limitation` consistently across schema, authoring, lookup, package instructions and examples. | R1/R3/R5/R6, C3/C5/C8: populated limitation fixture, discovery/validation example and source/installed prose checks. Legacy issue aliases and migration machinery are deliberately retired. |
| S8: apparent activity mistaken for a reliable lock, or failed rounds draining inputs | Read the advisory activity log before each run. Unmatched/malformed activity requires inspection; age alone never authorizes takeover. Failed or uncertain rounds drain no selected signals. | R7, C11: interruption, malformed log, failure and retry scenarios; actual start/end outcomes and unchanged input snapshots. No mutex, TTL takeover or queue database. |
| S9: unrelated/new-per-run PRs and uncertain publication | Honor an explicit eligible user target, otherwise reuse the current user's most recently updated eligible knowledge PR. Create a PR only when validated central changes exist. Merge current main normally; verify remote publication before any successful-round drain. | R7, C11: explicit/automatic selection, other-user/unrelated PR, no-update/no-empty-PR, main advancement/conflict, uncertain push/create and cleanup-failure retry cases. No force push or automatic PR merge/close. |
| Integration: source checks passed while installed resources/version proof differed | Ship source, template/reference bindings, manifests, generated instructions and consumer tests together. Verify the declared supported APM runtime, installed resource visibility and native automation invocation. | R6-R8, C8/C10-C12: isolated install/compile/resource checks with exact tool versions plus opt-in real-harness runs. The reference branch's APM 0.29.0 result does not certify 0.25.0; missing-corpus/skipped cases remain explicit. |

The old route planner, permissive YAML fallback, standalone YAML signal format, pointer migration, organization-specific environment/entrypoint compatibility and receipt-based coverage assumptions are deliberately replaced or retired. Preserve the regression scenario and intended safety behavior, not the obsolete implementation shape. This table does not authorize broader existing-skill ports or import the original corpus.

After plan approval, use the following stack. Each slice has its own meaningful tests and leaves the new package coherent. It does not depend on green tests in the unrelated inherited package. The earlier requirement to finish/integrate that package before search construction is superseded by the user's clean-start decision.

| Slice | Capabilities Covered | Repo(s) | Base / Stack Parent | Existing Surface / Likely Touchpoints | Notes |
| --- | --- | --- | --- | --- | --- |
| R1: New package, domain and schema | C1; schema portion of C2/C3/C6 | agent-knowledge-scaffold | Reviewed plan commit | Root `pyproject.toml`, `src/agent_knowledge/domain/`, `tests/unit/domain/` | Encode matching tables and strict typed models first. No dependency on the legacy tools. |
| R2: Documents and catalog/context adapters | C2, C10; codec portion of C6 | agent-knowledge-scaffold | R1 | New shared document codec, filesystem/config adapters, context/describe/catalog/doctor commands | All consumers share the codec. Test physical line offsets, configuration containment and quick readiness diagnosis. |
| R3: Search and navigation | C3, C4 | agent-knowledge-scaffold | R2 | New CLI/application functions, section/reference extraction | Explicit matching and navigation only; no route inference, fact extraction or legacy aliases. |
| R4: Markdown signal capture | C6; origin/schema portion of C5 | agent-knowledge-scaffold | R2 | New inbox adapter and signal CLI, using S7 safety cases as evidence | Can run alongside R3 after R2 is fixed. Capture/list only in this slice; compounding follows in R7. |
| R5: Authoring templates, validation, trace and guide | C5, C7; core portion of C8 | agent-knowledge-scaffold | R3 + R4 | Shared knowledge/signal templates, validation/receipt adapters, `docs/agent-contract.md`, neutral examples | Adapt useful existing knowledge-template bodies and metadata. Complete standalone CLI installation proof. |
| R6: Fresh APM consumption | C8; harness portion of C10 | agent-knowledge-scaffold | R5 | Minimal neutral package/manifest, source-owned discovery instruction, installed guide/template binding and setup docs | Prove fresh compiled-harness launcher/config visibility. No broad existing-skill port or optional hook framework. |
| R7: Setup and on-demand compounding | C11-C12 | agent-knowledge-scaffold | R6 | Neutral `knowledge-setup` and `knowledge-compound` skills, setup/automation references, activity/disposition templates, narrowly needed Git/publication/drain safety helper and tests | Ask for the configuration path and registered scopes, derive safe local defaults, provision the local runtime, register/update native harness automation, then deliver the agreed current-user PR/log/drain behavior through ordinary tools and the new core. No repository scheduler or automatic merge. |
| R8: End-to-end proof and final gates | C9; cross-capability verification | agent-knowledge-scaffold | R7 | Root acceptance cases, reusable S1 measurement ideas, fresh neutral consumer fixtures and harness drivers | Complete retrieval/authoring/compounding proof, exercise the registered automation in Codex/Claude/Copilot and run corpus walkthroughs plus consumption/latency measurements. |

R3 and R4 were delivered in the agreed one-slice review sequence. Catalog/schema ownership stays in R1/R2; final integration and proof are sequential. Split an oversized slice only around a coherent contract boundary and update every dependent reference. Tests and documentation ship with their behavior. Leave capability checkboxes unchecked until the complete behavior, including any later slice portion, is proven.

### 2.2 Implementation

#### Folder Structure

The repository has three permanent responsibilities: APM skill/package distribution, canonical organizational knowledge, and the Python tooling that supports knowledge use. The core is a normal Python package at the repository root; its implementation module `domain` is separate from the organization's domain-concept documents. Root APM manifests coexist with Python packaging.

```text
agent-knowledge-scaffold/
  README.md                     # Repository, APM package and core entrypoints
  apm.yml                       # Root APM catalogue/composition manifest
  apm.lock.yaml
  .apm/
    instructions/               # Instructions for working in this repository
    skills/                     # Repository-local maintenance skills, if needed
  pyproject.toml                 # New neutral package and console entrypoint
  uv.lock
  src/
    agent_knowledge/
      __init__.py
      py.typed
      domain/                   # Pure values, validation and retrieval rules
        __init__.py
        models.py
        validation.py
        schema.py
        catalog.py
        configuration.py
        discovery.py
        inspection.py
        matching.py
        navigation.py
        signals.py
      application/              # Coordinate explicit operations
        __init__.py
        discovery.py            # Context/catalog orchestration
        retrieval.py            # Search/inspect orchestration
        signals.py              # Signal capture/list orchestration
        doctor.py               # Readiness checks and runtime/write probes
        pagination.py           # Shared request/snapshot-bound cursors
        diagnostics.py          # Shared operation diagnostics
      entrypoints/
        __init__.py
        cli/
          __init__.py
          main.py               # Arguments, dispatch, rendering and exit codes
          contracts.py          # CLI schema descriptions
      infrastructure/           # Concrete format, filesystem and Git adapters
        __init__.py
        documents.py            # One Markdown/YAML-frontmatter codec
        configuration.py        # Workspace and catalog file loading
        errors.py               # Adapter error values
        filesystem.py           # Containment and guarded byte access
        corpus.py               # Selected-source inventory and document loading
        links.py                # Outgoing path resolution without linked body reads
        origin.py               # Durable checkout and project identity
        signals.py              # Durable, unique signal-file writes/listing
        receipts.py             # Optional append-only runtime trace
      resources/                # Installed guide and authoring templates
        templates/
          knowledge/            # Adapted canonical templates, shipped with CLI
          signals/              # Markdown capture template, same format codec
  tests/
    factories.py                # Shared neutral test values
    test_domain_boundary.py     # Cross-cutting architecture/import guard
    unit/
      domain/                   # No filesystem, Git, network or subprocesses
      infrastructure/           # Codec behavior over in-memory strings
      entrypoints/cli/           # Schema-description contracts
    integration/                # Temporary files/configuration/Git; few CLI runs
      application/              # Discovery, retrieval, signals and doctor
      infrastructure/           # Concrete filesystem/configuration/Git behavior
      entrypoints/cli/           # Command behavior
    acceptance/                 # Planned: complete neutral task/authoring scenarios
    fixtures/                   # Planned: synthetic data, not organizational policy
  docs/
    agent-contract.md           # One guide for agents; later skills reference it
  examples/
    knowledge-workspace.yaml
    catalog.yaml
    knowledge/                  # Clearly labelled fictional knowledge examples
    signals/                    # Markdown signal examples
  packages/                     # Permanent distributable APM packages
    knowledge-agent-pack/       # Minimal fresh retrieval/compounding package
      apm.yml
      README.md
      .apm/
        instructions/           # Instructions supplied to consumers
        skills/
          knowledge-setup/
            SKILL.md             # First-run runtime/config/harness setup
            references/          # Harness automation and setup guidance
          knowledge-compound/
            SKILL.md
            references/         # Optional skill-specific guidance
            scripts/            # Optional skill-specific implementation
            templates/          # Optional skill-authored artifact templates
  knowledge/                    # Optional empty canonical root for a fork
  ai/
    plans/
    signals/                    # Ignored durable runtime inbox
    evidence/                   # Ignored measurements and local verification
```

These module files are orientation, not a requirement for one class per concept. `domain` owns pure models, validation and matching; `application` coordinates explicit operations using the domain and concrete `infrastructure` adapters. For example, retrieval loads the configured sources/catalog, validates the query, reads candidates, applies domain matching, and assembles previews and pagination. The agent still chooses the searches. `entrypoints/cli` parses requests, invokes application operations, renders outcomes and selects exit codes; it holds no independent matching rules. Shared diagnostics belong in `application` so operations do not depend on CLI code. The domain imports none of these other layers.

The doctor module still directly implements its runtime and optional write probes. Moving it into `application` does not establish a strict no-I/O application boundary or authorize a broader probe rewrite. Combine trivial adapters or split a large responsibility when justified, without interface/factory boilerplate around the single local filesystem implementation. Tests mirror the implementation responsibility within separate unit/integration groups; shared factories and the cross-cutting domain import guard remain at the test root.

The root `knowledge/` starts empty, optionally represented by a non-Markdown placeholder. Its eventual content can use `concepts/`, `product/features/`, `product/workflows/`, `systems/`, `operating-rules/`, `runbooks/`, `limitations/`, `incidents/` and `qa-evidence/`. Do not put setup READMEs or sample policies inside the active canonical search root. `examples/knowledge/` is loaded only when explicitly selected by an example configuration or test.

Catalogs and workspace files can live outside this repository; the example locations do not force a deployment layout. A source contains its own knowledge root/catalog, and a consumer workspace can select several such sources. Named scopes live in metadata/configuration rather than a prescribed staff hierarchy in the folder tree.

`packages/` is the maintained APM distribution surface, not a legacy archive. R6/R7 add a minimal neutral knowledge package with separate `knowledge-setup` and `knowledge-compound` skills. Broader current organization-specific skills can be selectively adapted afterward. Root `.apm/` primitives govern work on this repository; each package's `.apm/` primitives are what consumers install. Retain a single owner for distributed instructions to avoid duplicating root and package guidance in a consumer. Selected future skill ports include their templates, references, scripts and manifest/resource bindings as a unit; review them for organization-specific assumptions rather than porting only `SKILL.md`. Not every existing skill will be retained.

APM and Python packaging have different responsibilities. APM delivers skills, instructions and their local references/scripts/templates; the Python package delivers the shared `agent-knowledge` runtime and common knowledge-authoring templates. `knowledge-setup` uses the installed runtime and native harness automation interface to prepare a consumer; `knowledge-compound` uses the runtime for retrieval/validation and ordinary Git/GitHub tooling for publication. Skills must not copy matching/parsing logic or import private source-tree modules. Other APM skills need not depend on the knowledge runtime. Canonical organizational documents remain in configured knowledge sources rather than being copied into every skill package. R6 verifies the minimal package's dependency/setup binding and installed guide/template locations exposed by `describe`; R7/R8 verify setup and automation invocation. An installed skill must not depend on an unavailable repository-relative `src/` or `docs/` path.

The fresh consumer installs the new knowledge package without pulling inherited organization-specific packages into its default setup. Ship the source-owned core guide as an installed resource alongside the templates, verifying parity if packaging copies it from `docs/agent-contract.md`; do not maintain two independently edited guide bodies.

**Knowledge-template port.** Inventory existing knowledge templates and canonical family guidance before writing replacements. Preserve useful purpose, behavior, preconditions, procedure, verification, recovery, provenance and related-knowledge sections where they fit. Adapt frontmatter to `knowledge.v1`, registered `scope`, `entities`, `engineering_concerns` and explicit applicability; remove old task/review routing metadata, organization-specific names and old YAML-system-map assumptions. Convert backticked path lists into resolvable Markdown links where navigation is intended. Rename issues to limitations. This is a content/metadata adaptation, not a byte-for-byte copy or a corpus import.

Start from the existing shared product-feature, product-workflow, service-runbook and procedure-runbook templates. Supply an appropriate neutral template for each of the nine new knowledge kinds, with distinct service/procedure runbook variants where their body structure warrants it. System pages describe actual components/relationships in Markdown; hyperlinks alone do not define runtime edges. Do not assume that changing frontmatter is sufficient if a template's body contains old assumptions. Templates stay outside active canonical roots, use visible placeholders without invented default policy, and pass validation once populated with registered fixture values.

Keep independent test scopes: the fast domain/core suites import only the new Python package, while APM manifest/skill/install checks cover the distribution surface when it changes. Retaining APM packages does not require loading them into domain unit tests. The APM manifests, `.apm/` and `packages/` remain the active distribution surfaces. Retired packages and their marketplace release tooling were removed in the later clean-slate pass.

#### Data Model

**Taxonomy.** One schema supports these knowledge kinds; folders are conventional organization, while validated `kind` controls filtering. The configured root is not a hard-coded `.knowledge` directory.

| `kind` | Conventional folder | Content boundary |
| --- | --- | --- |
| `concept` | `concepts/` | Domain terminology and conceptual relationships. |
| `feature` | `product/features/` | Capability purpose, boundaries and links to behavior. |
| `workflow` | `product/workflows/` | User/business behavior, outcomes and acceptance criteria. |
| `system` | `systems/` | Components, ownership, environment facts and explicit runtime relationships. |
| `operating-rule` | `operating-rules/` | Engineering guidance, including architecture, approved stack and provisioning. |
| `runbook` | `runbooks/` | Coherent procedures with prerequisites, validation and recovery. |
| `limitation` | `limitations/` | Known constraints, unsupported behavior and workarounds; not a duplicate ticket tracker. |
| `incident` | `incidents/` | Historical events, causes and lessons. |
| `qa-evidence` | `qa-evidence/` | What was verified, with conditions and evidence. |

Do not add organization/tribe/squad folders as new knowledge kinds. Do not introduce a generic notes family. System documents are Markdown too; runtime relationships can be documented in their body with evidence. A document hyperlink is not itself a runtime edge. This plan does not add a graph database or automatically translate diagrams into dependencies.

**Canonical frontmatter.** Use `schema_version: knowledge.v1`. Required fields are `kind`, `title`, `description`, `scope` and `engineering_concerns`. Their scalar/list types are strict; lists contain nonempty, unique registered IDs. `entities` is an optional list of registered named entities. `languages`, `technologies` and `environments` are optional for other kinds but mandatory for operating rules, using `[any]` where intentionally unrestricted. Optional `aliases` and `terms` contain text discovery phrases, not exact-filter identifiers. Body links and evidence remain ordinary Markdown rather than duplicated metadata lists. `strength`, `subjects`, `concerns`, `activity`, legacy `scopes` and implicit missing-field defaults are not accepted schema aliases.

Missing optional applicability is unclassified, not `any`: it does not satisfy a supplied filter, including an explicit `[any]` filter. Omitting that dimension from the query leaves it unrestricted. On a document, `any` must be the only value in that applicability field. On a query, `[any, typescript]` is deliberately valid. `any` is not a scope, entity or knowledge kind.

Descriptions must explain when the document is useful; the initial schema caps them at 600 characters so previews remain bounded. Documents should contain independently useful subjects/procedures, not arbitrary equal-sized chunks. Keep warnings and prerequisites near procedures or explicitly linked. A partial read never proves that every caveat has been seen.

Representative authored document, not content to ship as organizational policy:

````markdown
---
schema_version: knowledge.v1
kind: operating-rule
title: Evaluate index benefits and maintenance costs
description: >
  Before adding an index, identify target queries and assess read benefits,
  write overhead and storage costs.
scope: [group:commerce]
engineering_concerns: [performance, data-design]
technologies: [family:relational-database]
languages: [any]
environments: [any]
---

# Evaluate index benefits and maintenance costs

Identify the queries the index should improve and evaluate the expected
read benefit against write and storage costs. Record the evidence used.

## Related Knowledge

- [PostgreSQL index procedure](../runbooks/postgresql-index.md)
````

**Signals.** Use `schema_version: knowledge-signal.v1` and one `.md` file per signal. Frontmatter contains a stable `id`, `created_at`, advisory `kind_hint`, originating workspace/project identity, configured scope/source IDs known at capture, optional originating `harness`, opaque `session_id` and opaque `automation_id`, optional registered entity/technology hints, and safe evidence references. The Markdown body holds the claim and explanatory context; do not duplicate the full claim in frontmatter. Discovery and compounding reject an empty claim. Preserve stable origin information even if the producer's temporary worktree disappears.

````markdown
---
schema_version: knowledge-signal.v1
id: example-index-observation
created_at: "2026-09-09T12:00:00Z"
kind_hint: operating-rule
origin:
  workspace_id: repo:orders-api
  project_path: products/orders-api
  applicable_scopes: [org:example, group:commerce, repo:orders-api]
  source_ids: [commerce-knowledge]
  harness: codex
  session_id: opaque-session-id
  automation_id: opaque-automation-id
entities: [service:orders]
technologies: [postgresql]
evidence:
  - type: file
    reference: repo:orders-api/docs/index-measurements.md
---

# Index maintenance cost was missing from the implementation guidance

The referenced measurements support a PostgreSQL-specific observation.
They do not by themselves justify organization-wide or family-wide policy.
````

The neutral example IDs/references are illustrative; production writes must resolve them against configured catalogs and evidence. Unknown hints can remain prose in the signal body; they must not silently become canonical registered metadata. `harness`, `session_id` and `automation_id` are provenance/routing hints only: store safe opaque values, never credentials, tokens, transcript text or prompt bodies. When a harness supports session handoff, compounding may try the recorded session and must fall back to self-contained processing when it is absent or unavailable. Canonical knowledge documents do not inherit these transient producer fields; the activity record and signal retain them. An unavailable originating configuration must be reported and the signal retained for any decision that depends on it; the compounding checkout is never substituted as the origin.

Use the durable layout established during the discussion, with Markdown signals:

```text
<durable-scaffold>/ai/signals/
  projects/<durable-checkout-path-relative-to-code-root>/<timestamp>-<unique-id>.md
  shared/<timestamp>-<unique-id>.md
  compound-activity.jsonl
```

Here `shared/` is an origin bucket for a deliberately non-project signal; it is not a canonical applicability scope. Linked worktrees resolve through Git common-dir before placement. Signal files remain ignored and outside every configured canonical root, including roots that do not exist yet. Fingerprints cover the complete signal bytes, including body and provenance, so R7's compounding workflow can detect edits before deletion. S7's file-identity and symlink cases are safety evidence for the new adapter, not a mandate to copy its implementation. Core retrieval/capture/list operations never automatically drain signals; R7 owns confirmed disposition and guarded removal.

**Catalogs.** Each configured source supplies one YAML catalog with `schema_version: knowledge-catalog.v1` and mappings of registered scopes, entities, engineering concerns, languages, technologies, technology families and environments. Entity records carry a label, short description, aliases and optional canonical document references; documents refer to IDs rather than maintaining independent definitions. Catalogs are searchable and pageable; do not inject an entire enterprise catalog into every prompt. Conflicting definitions of the same ID across active sources are configuration errors; identical definitions can be coalesced with source provenance.

Scope records may declare `parents: [<registered-scope-id>, ...]`. This configurable relationship expresses hierarchy without assuming an organization/tribe/squad model. Validate missing parents, self-references and cycles across the combined catalogs. R1 supplies the explicit pure `Catalog.scope_ancestors()` helper; queries still match only supplied IDs. Neither a parent relationship nor its ordering grants access, infers workspace membership, assigns local-over-global precedence or broadens an authored claim. Context presentation belongs to R2; callers remain responsible for including the applicable scopes in each request.

The following is a catalog fragment, not a complete standalone file:

```yaml
technologies:
  postgresql:
    label: PostgreSQL
    aliases: [Postgres]
    technology_families: [relational-database]
  mysql:
    label: MySQL
    technology_families: [relational-database]
technology_families:
  relational-database:
    description: Relational database engines.
```

`technology_families` is catalog membership. Document/query applicability uses the existing `technologies` field with `family:<id>` values. No separate family filter with accidental AND semantics. Membership is explicit and one level; do not infer ancestry from names or transitively expand nested families. Families can overlap. Adding a member broadens the discoverability of family rules and must be reviewed accordingly. The technology catalog is not the approved-stack list; that guidance lives in operating rules.

#### API Contract

Provide one new neutral console entrypoint, `agent-knowledge`, with `describe`, `doctor`, `context`, `catalog`, `search`, `inspect`, `validate` and `signal` operations. The [CLI examples](knowledge-cli-examples.md) provide concrete syntax, complete example inputs and expected behavior for every operation. These are contracts for the planned implementation, not claims that the commands exist today. Python APIs and the CLI must use the same domain functions. Do not add an HTTP/MCP service or a second semantics implementation in this slice.

| Operation | Input | Output and boundary |
| --- | --- | --- |
| `describe` | Optional `schema` and `field` selector; `field` requires `schema` | Compact field/type/OR-AND documentation, kinds, examples and installed guide/template paths. No full knowledge corpus. |
| `doctor` | Optional mode (`read` default, or `write`) and expected workspace ID; explicit configuration when available | Running package/interpreter/launcher identity, configuration/catalog/source checks, per-check status and targeted remediation. No full knowledge-body scan. |
| `context` | Explicit workspace configuration | Workspace ID, configured sources and applicable scope IDs; catalog handles. No organizational inference from directory names. |
| `catalog` | Required `dimension`; optional `text`, `ids`, `sources`, `limit`, `continuation` | Canonical IDs, labels, short descriptions, source provenance and declared technology families. Ambiguous aliases return candidates; text and IDs combine with AND when both are supplied. |
| `search` | Explicit query object and optional source selection | Matching file previews, locations and truncation information. No document bodies or extracted facts. |
| `inspect` | `document: {source, path}`; optional `expected_fingerprint`, `limit`, `continuation` | The same preview plus heading outline and labelled references/locations for that selected file. No automatic linked-file reads; navigation entries page in physical-line order. |
| `validate` | Exactly one of `sources`, `documents` (source/path objects), `signal_files` (paths), plus configuration | Schema/catalog/reference diagnostics using the same domain as retrieval. Does not assert semantic truth or publish changes. |
| `signal record` | `file`: authored Markdown signal path; explicit originating configuration | Validate and check durable origin, then capture a unique file and return path/fingerprint. Retain authoring input; no overwrite or publication. |
| `signal list` | Optional `include_shared` (false), `limit`, `continuation`; explicit originating configuration | Validated inventory for the configured workspace, optionally including non-project signals, with metadata/body locations and fingerprints. No mutation or automatic deletion. |

Use `agent-knowledge [--config FILE] [--output json|text] <command> [<subcommand>] [--request-file FILE|-]`. Global options precede the command; command request fields live in the structured request, not a competing collection of filter flags. `--request-file -` explicitly reads stdin, so a default `doctor`, `context` or `describe` call cannot hang waiting for input. JSON and YAML requests use the same typed model. `describe` works without configuration; `doctor` reports missing configuration alongside available runtime checks; other operations require it. Relative paths inside requests resolve against the configuration directory (source-relative document references remain relative to their named source); the request-file path itself resolves against process cwd. No arbitrary cwd-dependent query semantics.

The CLI does not interpret an unstructured task description as a query plan. Machine output defaults to JSON with operation-specific fields, `status: ok|error` and `diagnostics`; text is an alternate renderer. Diagnostics contain a code/message and targeted remediation when available. A successful empty search exits 0 with `results: []`. Invalid requests/configuration/validation exit 2; runtime I/O failures exit 3. Both return structured diagnostics, not an empty successful result. Document these exit codes and test them consistently across methods. Configuration/schema errors such as `configuration-required`, `workspace-mismatch`, `unknown-identifier` and stale fingerprint/snapshot errors have stable codes.

**Doctor.** The quick default runs inside the same process/environment used by the calling harness. Report package version, interpreter and executable location, selected configuration/workspace identity, catalog validity, source-root existence/readability, and signal-storage containment/configuration if present. Do not dump environment variables or credentials. Do not enumerate/read every knowledge document; `validate` is the explicit deeper content check. Return readiness separately for reading and writing (`ready`, `not-ready`, `unverified`, `not-configured`); default read mode leaves write readiness unverified. Optional `mode: write` performs a unique temporary create/delete probe only after signal-root/canonical-root containment checks pass, and reports actual cleanup failures. It does not create directory trees, write a signal, alter canonical knowledge, install software, modify shell files, mutate launchctl or repair configuration. Missing optional signal storage does not prevent read readiness; it fails an explicitly requested write check. Missing setup and actual I/O failures retain their distinct exit categories.

The new runtime has no required launchctl integration and does not depend on organization-specific environment variables. A terminal success does not prove a GUI/compiled harness sees the same installation or config: run the same doctor command from that harness. If the executable/interpreter cannot start, or an import dependency fails before startup, it cannot diagnose itself; R6's APM bootstrap first checks executable availability and reports launch failures with the configured installation/invocation path, then calls doctor with the explicit config. Simulate minimal/non-login environments in core smoke tests; verify actual compiled-harness invocation in R6. Do not claim that a standalone doctor check already proves harness integration.

Search request:

```yaml
kind: [operating-rule]
scope: [org:example, group:commerce, repo:orders-api]
engineering_concerns: [performance, data-design]
languages: [any, typescript]
technologies: [any, postgresql, family:relational-database]
environments: [any, prod]
limit: 10
```

All exact filters are optional. Supported filters are `kind`, `scope`, `engineering_concerns`, `entities`, `languages`, `technologies` and `environments`; `sources` selects configured source IDs. No supplied filter means enumerate within the explicitly configured sources, subject to limits. No implicit local scope, environment, family or `any` injection occurs. Explicit empty lists, unknown fields, unknown IDs and invalid scalar/list types are validation errors. Duplicate requested values are normalized without changing semantics.

Optional text predicates have `text.any` and `text.all` lists. A document must satisfy at least one `any` phrase when present, every `all` phrase when present, and both groups when both are supplied. Each phrase uses documented Unicode/case/whitespace normalization and literal token-sequence matching; no regex, stemming or fuzzy semantic interpretation. Registered aliases are alternatives within their phrase group, not new mandatory AND terms. An ambiguous alias keeps its possible matches distinguishable; it does not silently select an entity ID or add metadata filters. Unregistered wording is searched literally and may match nothing.

Searchable text consists of title, description, aliases/terms and the Markdown body. Metadata facets filter first; bodies can be scanned locally without being returned. Ignore formatting syntax when appropriate but retain original physical line locations. Unrelated catalog text and linked document bodies are not part of a file's match surface.

Keep ordering simple and documented: a matching title/description/alias precedes a body-only text match, followed by source ID and relative path for stable ties; metadata-only enumeration sorts by source ID/path. Sorting never admits a failing candidate. Defaults: 10 files per page, maximum 100; report `total_matches`, `returned`, `truncated` and continuation information. Metadata pages use a source/catalog/document fingerprint snapshot; a continuation against a changed snapshot returns a stale-snapshot error rather than silently skipping/duplicating entries. No persistent search index is required to compute this fingerprint.

Every preview provides:

- Source ID, source-relative path and resolved local path, so ordinary harness tools can read it.
- Title, description, kind and authored applicability/entity metadata.
- UTF-8 byte count, total physical line count, frontmatter/body ranges and content fingerprint.
- Match field and line locations; matching body headings and enclosing section start/end lines where present.
- An explicit indication when matching occurred only in metadata, and a link count without automatically expanding all references.

Lines are one-based and inclusive, count frontmatter, and refer to the exact bytes fingerprinted. Preserve positions across CRLF, Unicode, fenced code, duplicate headings, unheaded introductions and files without a final newline. Section ends occur before the next heading of equal or higher level; smaller subheadings remain inside their parent. A metadata-only hit must not invent a body match. A heading/fence-aware line scanner may support a documented Markdown subset; unsupported syntax must not yield fabricated section boundaries.

`inspect` exposes a bounded outline and ordinary Markdown link labels, targets, anchors and source lines. Return explicit unresolved/missing/external status rather than silently deleting references. Resolve knowledge links relative to their source file and across explicitly configured sources; do not follow symlinks or references out of allowed roots. HTTP/code references are labelled external evidence, not fetched. Inspecting a linked knowledge file uses the same preview contract. No automatic recursion, backlinks computation or runtime-dependency inference.

Ordinary file reads remain outside this tool. The agent can read the whole file or use grep and line ranges. A stale fingerprint tells it to refresh the preview; the tool does not promise that arbitrary external reads occur atomically with a previous search. Large link/outline/match lists are bounded with explicit counts/continuation, not silently omitted.

#### Business Rules

The `domain` module is the executable owner of these rules:

| Rule | Required result |
| --- | --- |
| Multiple values in one exact filter | OR: a nonempty intersection with the document's values is sufficient. |
| Different supplied filters | AND: every supplied dimension must pass. |
| Omitted query dimension | No restriction for that dimension. |
| Explicit `any` | Matches intentionally unrestricted document applicability only; never an implicit wildcard expansion. |
| Missing document facet | Fails a supplied filter; does not become `any`. |
| Family membership | Catalog discovery returns it; the query must explicitly contain `family:<id>` to match a family-only document. |
| Organizational membership | Use configured scope IDs; no ancestor inference or local-over-global precedence. |
| Known entity | Exact canonical ID matching across knowledge kinds. |
| Unknown identifier vs no result | Invalid query and valid empty result are different outcomes. |
| Additional AND filter | Cannot add matching documents. |
| Additional OR value | Cannot remove matching documents before pagination. |
| Reordering/deduplicating values | Cannot change the matching set. |

Use typed Python values and small pure functions. Likely domain areas are models/validation, catalogs/normalization, matching and navigation metadata construction. Keep the number of files driven by these responsibilities; do not introduce repository interfaces, dependency-injection containers, event buses or generic rule engines. Parsing raw YAML and reading bytes are adapter responsibilities; schema and semantic validation of parsed values belong in `domain`. Plain strings/parsed heading records can be inputs to pure navigation functions. A separate `domain` module for implementation is unrelated to the `concept` knowledge kind. Adopt standard `src/` packaging and a root console-script declaration; package installation must not pull in retired APM package trees.

The experiment already uses Python 3.11+, PyYAML, pytest and Ruff; those remain suitable choices for the new root package. Build one strict safe YAML loader that rejects duplicate keys, malformed frontmatter, wrong root types and unsupported schemas. Do not reproduce the old preview helper's permissive fallback. Parsing errors must not become empty metadata. The shared Markdown codec preserves the body and source locations; knowledge/signal validators apply after that format step. Reject YAML alias cycles and bound document/request sizes without executing YAML constructors. No model, database, web framework or parser framework is justified by this plan.

**First-run setup instruction contract.** R7 supplies a separate neutral `knowledge-setup` skill for the developer who clones a scaffold or adds it to an existing workspace. It owns setup questions and native automation registration, not taxonomy judgment or a scheduler implementation:

1. Ask for the absolute workspace configuration path and registered applicable scope IDs. Preserve an existing workspace ID; for a new file derive and persist `workspace:<directory-slug>` from the durable configuration parent. Preserve configured sources/catalogs; for a new file scaffold `<scaffold>/knowledge` and `<scaffold>/catalog.yaml`. Derive the producer code root, use `<scaffold>/ai/signals`, create/reuse `<scaffold>/.agent-knowledge-venv`, ensure both local paths are ignored by the scaffold, compile all three supported APM targets and use a daily local-time cadence. Publication is disabled by default; ask for repository/branch/prefix only when the developer opts in. Never infer organization membership, scopes or a repository from a directory name.
2. Check the selected harnesses' native automation capability and existing task marker. Reuse or update the matching task instead of creating a duplicate. Keep one automation owner per signal store; explain how to pause or remove it.
3. Check Python/`uv`/Git/GitHub authentication and the configured runtime path. Create or reuse a scaffold-local or user-selected virtual environment, install the package and required dependencies, and verify `agent-knowledge describe` and `doctor` from the same harness process that will run the automation. Do not print credentials or tokens, edit shell startup files, mutate launchctl or rely on an ambient organization variable.
4. Run APM installation/compile for `codex`, `claude` and `copilot` by default, then register a native daily automation for each available supported provider whose prompt invokes `knowledge-compound` with the absolute configuration path. Report unavailable or unauthenticated providers individually without asking the developer to choose a subset. The prompt must preserve the configured working directory, runtime path, harness name and an opaque automation/session handle where the harness exposes one.
5. Trigger a run-now/one-shot execution and show the user the result, activity record and pause/remove control. A setup success requires the automation to reach the installed compounding skill and a configured `doctor`; it does not require a production PR or signal drain during setup.

The setup skill may write an ignored local bootstrap/environment file for values a harness cannot persist otherwise. The file contains paths and non-secret identifiers only, such as `AGENT_KNOWLEDGE_CONFIG`, `AGENT_KNOWLEDGE_VENV`, `AGENT_KNOWLEDGE_WORKSPACE_ID`, `AGENT_KNOWLEDGE_HARNESS` and `AGENT_KNOWLEDGE_AUTOMATION_ID`; it never contains tokens or credentials. The automation still passes `--config` explicitly. Provider-specific task IDs and credentials remain native harness/account state rather than canonical knowledge. `apm compile` is an installation-time projection step; the recurring automation runs `knowledge-compound` (compounding), not APM compilation.

The setup interaction ends with a concrete summary the developer can inspect:

```text
Workspace: /work/commerce/knowledge-workspace.yaml (workspace:commerce)
Runtime:   /work/commerce/.venv/bin/agent-knowledge
Sources:   commerce-knowledge; scopes org:example, group:commerce, repo:orders-api
Harness:   codex (native Scheduled task, daily at 09:00 Europe/London)
Automation: agent-knowledge compound / workspace:commerce
Publication: example/commerce-knowledge, base main, branch prefix knowledge/

The setup is ready to run once now. Future runs invoke knowledge-compound;
they do not merge PRs or drain signals unless publication/disposition is verified.
```

The native task prompt is short and stable; the target adapter supplies the
harness's explicit skill syntax (for example, Codex Scheduled can name
`$knowledge-compound`):

```text
Run the installed knowledge-compound skill for
/work/commerce/knowledge-workspace.yaml. Process pending signals for this
workspace, follow its publication and drain policy, and report the run,
dispositions and retained/drained inputs. Do not merge PRs or force-push.
```

**Compounding instruction contract.** The new core guide owns mechanical matching and these authoring instructions. R7 supplies a small neutral `knowledge-compound` skill that can be invoked manually or by a native harness automation, selecting useful existing instructions/templates without porting the whole legacy package. Agent judgment plans the work; no deterministic compounding task planner is added:

1. Load the originating workspace's configured context. Preserve origin independently from applicability; do not infer an organization's membership from a folder or copy the compounding checkout's scopes.
2. Resolve scopes, entities, engineering concerns, languages, technologies and families through the catalog. Reuse IDs; propose necessary catalog additions with the related knowledge update.
3. Search existing owners using text discovery followed by canonical filters. Include relevant configured shared scopes and inspect linked owners. Do not limit a potential owner to the signal's advisory kind.
4. Search the effective publication state, including the current user's pending knowledge PR and current main. Broaden explicit searches when a potential owner might exist in another plausible kind; there is no deterministic exhaustive-search planner or proof of semantic completeness.
5. Assign scope supported by the evidence. A repository-origin signal does not establish an organization-wide policy.
6. Use `any`, a specific technology, an explicit list, or `family:<id>` according to supported applicability. Technology-family membership alone is not evidence of family-wide truth. Adding family membership is a meaningful catalog change.
7. Separate general principles and vendor-specific procedures when independently useful. Otherwise keep narrower applicability and explain the limitation. Preserve supporting evidence and nearby/referenced prerequisites.
8. Validate identifiers, required metadata, references and publication state. Explain any broadening of an existing document's scope/family applicability.
9. Use the agreed advisory activity log and one eligible current-user knowledge PR. Merge current main normally, validate and push without force; humans merge/close the PR. Drain only selected, unchanged signals after verified publication or a confirmed no-write disposition. Failures and uncertain outcomes retain inputs. If a signal carries a safe originating harness/session handle, the automation may attempt to resume or hand off to that session; normal self-contained compounding is the fallback. The coordination and guarded-drain behavior is implemented in R7; authenticated provider execution is proven separately in R8.

**On-demand workflow and publication.** The minimal skill uses the normal harness plus Git/GitHub tooling and the new context/catalog/search/inspect/validate/signal operations. Keep the following sequence explicit in one skill/reference owner:

1. Read `<scaffold>/ai/signals/compound-activity.jsonl` before starting. Append a run ID, UTC start timestamp, `active: true`, workspace ID, harness, automation ID and session ID when available; append end timestamp, `active: false` and outcome when finishing. If an earlier run remains active, inspect its state rather than blindly starting another drain. This is an advisory log, not a lock, lease manager or exactly-once queue. A crash may leave an active record; do not manufacture a successful end.
2. Select signals for an available originating workspace, resolve its configured sources, and retain a snapshot of selected identities and complete-byte fingerprints. Preserve each signal's optional opaque originating harness/session handle without copying conversation content. Use the same process explicitly for each additional origin. Preserve unselected/new signals. Compounding must not substitute the knowledge repository's workspace context for a producer's.
3. Resolve the target knowledge repository from that source's explicit publication configuration. Verify authenticated GitHub identity, remote and base branch before writing. Honor an explicitly selected eligible current-user knowledge PR; otherwise select the current user's most recently updated eligible PR, with PR number as a stable tie-breaker, and report the selection. Eligibility excludes another author's work and unrelated code PRs. The neutral package identifies its knowledge PRs through a configured branch prefix. If none exists, prepare an isolated branch from the current base; defer PR creation until validated central changes exist. Do not create one PR per run or an empty PR for a no-update round.
4. Work in an isolated checkout of the selected publication branch. Fetch the current configured base, merge it normally into that branch, and search this effective state before updating owners. Retain unrelated local changes and resolve ordinary merge conflicts without force pushing. Agent-planned searches can broaden across plausible kinds; there is no claimed exhaustive semantic-search certificate.
5. Apply the authoring rules and templates; validate changed knowledge/catalogs and required repository/APM surfaces. Record each selected signal's proposed update or explicit no-update disposition with evidence. No-update requires a stated reason and supporting owner/evidence, not merely an empty narrow query.
6. Commit and push intended updates, creating a knowledge PR only when needed and when validated central changes exist, then verify the remote commit and PR head contain them. A timeout/uncertain response is not verified publication; inspect existing remote state before retrying a push or PR creation. Publication here means the changes are available in the user's open knowledge PR; a human still merges or closes it. For no-update dispositions, retain a durable local disposition record before considering the input handled, without creating an empty PR.
7. Failed or uncertain rounds drain no selected signals. After a successful round, drain only selected signal files whose identity and complete bytes still match the captured snapshot and whose publication/no-update disposition is confirmed. Recheck path containment and symlink/file replacement protections immediately before removal. If safe removal cannot be established, retain the signal and report it. Preserve edited and subsequently added inputs, and finish the activity log with the actual outcome. If some cleanup succeeded before a later cleanup failure, report that partial cleanup honestly; retry by inspecting confirmed dispositions/publication rather than recreating updates or claiming removed inputs still exist.

Reuse narrow tested filesystem guards from stabilization where suitable; keep them outside pure domain, with pure disposition/eligibility predicates independently testable. Do not introduce a general GitHub SDK/service, batch database or repository scheduler. The setup skill may use each harness's native automation registration surface, but must not replace it with a cron/daemon or hidden background loop. Any package-local safety helper exposed for the agent must ship with a realistic invocation example and installed smoke proof in R7; the nine core CLI methods above are not a hidden compounding orchestrator. Reads and capture work without publication configuration or GitHub access. Test publication through temporary Git remotes and simulated GitHub responses; test native automation invocation through disposable harness tasks; do not create real PRs or remove real signals as test setup.

Signal capture must be lightweight: record the durable observation and evidence, then continue the user's task. Capture can carry existing IDs as hints; it must not run a full compounding search or invent new organization-wide policy. The context/catalog contract is shared by capture, retrieval and compounding.

**Teaching and receipts.** Create one organization-neutral `docs/agent-contract.md` for the new core and ship it with the CLI's help/discovery surface. It is the owner that adapted skills will reference later; do not update 31 legacy skills during this build. Keep long examples out of any eventual always-loaded descriptions. Explain that task stage affects which questions the agent asks: a planning agent can need a runbook without an `activity: planning` tag, and a hosting decision should search technology-choice guidance before narrowing to the user's proposed provider. The setup skill owns first-run questions, runtime/bootstrap guidance and harness automation registration; the compounding skill owns the recurring signal workflow.

Optional core receipts record query, configured sources, returned file identities/fingerprints and whether the event was search or inspect. The standalone CLI does not observe ordinary harness reads: body-read status is unknown. A later harness integration may record a read only when it actually observes the path/range. Do not force a custom reader to manufacture receipts. A failed optional receipt write produces a diagnostic without pretending the successful search failed or that a receipt exists. No coverage checklist, compulsory replay after compaction, keyword-driven pass validator or automatic stopping policy. Compaction can retain navigation references; the agent uses ordinary rediscovery if it needs evidence again. Native scheduled automation is configured once by `knowledge-setup`, remains visible in the harness, and invokes `knowledge-compound`; it is not a core receipt or scheduler implementation.

#### Config

Use an explicit `knowledge-workspace.yaml` configuration selected through `--config` or R6's consumer bootstrap. Relative paths resolve against that file, not arbitrary process cwd. It declares a stable workspace ID, applicable scope IDs, configured local source roots/catalogs, and an optional durable signal destination/code-root mapping. Each source can optionally declare `publication: {repository, base_branch, branch_prefix}` for on-demand compounding; these are configuration data, not embedded organization constants. An optional `setup` section records non-secret bootstrap preferences such as the virtual-environment path, target harnesses, automation name, cadence and timezone; provider task IDs and credentials remain native harness state. `signal_storage` is required only for signal operations; read-only retrieval does not require a writable inbox. No fallback to the original `KNOWLEDGE_ROOT` is permitted. The standalone CLI works without any organization-specific environment or APM installation; the minimal APM package adds consumer instructions rather than a runtime dependency. The setup skill may generate a local ignored environment file and set the automation's process environment, but it never mutates user shell startup files or makes CLI behavior depend on ambient variables.

```yaml
schema_version: knowledge-workspace.v1
workspace_id: repo:orders-api
applicable_scopes: [org:example, group:commerce, repo:orders-api]
sources:
  - id: commerce-knowledge
    root: ../commerce-knowledge/knowledge
    catalog: ../commerce-knowledge/catalog.yaml
    publication:                 # Optional; needed only for PR compounding
      repository: example/commerce-knowledge
      base_branch: main
      branch_prefix: knowledge/
signal_storage:
  scaffold_root: ../commerce-knowledge
  code_root: ..
setup:
  venv: .venv
  harnesses: [codex]
  automation:
    name: knowledge-compound
    cadence: daily
    timezone: Europe/London
```

This example is a neutral template, not a default organization. Source roots, catalog IDs, scopes, runtime location, harness targets and cadence are configurable; no organization/squad model is built into matching. Supply a small starter engineering-concern vocabulary with descriptions, including behavior, architecture, technology-choice, provisioning, implementation, testing, security, compliance, deployment, reliability, performance, data-design and ownership. Keep structural field names and the initial nine knowledge kinds closed; make vocabulary values extendable through catalog updates. Catalog discovery supplies valid identifiers and does not require a full enterprise inventory during onboarding.

Validate all active source/catalog configurations before interpreting absence. Missing or unreadable selected sources, conflicting IDs, invalid files or interrupted scans yield an error/incomplete diagnostic rather than `results: []` with a false implication of a complete search. Access is limited to configured local roots; no network access or credentials are needed for retrieval. A valid empty configured corpus is supported.

#### Automated Tests

Most tests belong in `tests/unit/domain/` and call domain functions directly with small in-memory values. They must not create temporary files, launch a CLI, invoke Git, load a real catalog or depend on installed APM output. Generate truth-table combinations with pytest parametrization and standard-library iteration rather than introducing a property-testing dependency solely for this work. Test behavior and algebraic invariants, not class layout or private function names.

Target the domain suite at under two seconds of pytest execution on the recorded development machine, excluding environment installation. Record three warm-run timings; treat regressions as profiling work rather than adding flaky per-test wall-clock assertions. R1 measurements are recorded below. One import-boundary check ensures domain does not acquire adapter/environment dependencies. A larger number of cheap semantic cases should not turn into hundreds of subprocess tests.

| Capability | Test Level | Existing Test Pattern / File | What The Test Proves |
| --- | --- | --- | --- |
| C1 | Pure unit/static | New `tests/unit/domain/`; pytest | Typed validation, deterministic results, no side effects, isolated fast execution. |
| C2 | Unit + small adapter integration | Catalog values in memory; temporary multi-source workspace | Identifier discovery, aliases/ambiguity, ID collisions, explicit memberships, missing configs and empty catalogs. |
| C3 | Pure unit + few CLI cases | New parameterized tests; old lookup cases are reference scenarios only | OR/AND, missing vs any, family inclusion, text phrase groups, zero matches, no fallback padding, stable ordering and pagination. |
| C4 | Unit + codec/filesystem integration | New navigation tests; selected old preview cases as reference | Correct original line positions, long-runbook partial reads, metadata-only hits, nested/duplicate/fenced headings, links, stale fingerprints and allowed roots. |
| C5 | Authoring fixtures + CLI validation | Adapted knowledge-template inventory and new neutral examples | All nine kinds/needed variants populate valid metadata; useful body sections, links and evidence survive; origin differs from applicability and no automated semantic judgment is claimed. |
| C6 | In-memory codec + focused filesystem tests | New inbox tests using S7's failure cases | One Markdown format, separate schemas, strict YAML, unique writes, missing-canonical-root/symlink safety and complete-byte fingerprinting. |
| C7 | Unit + receipt-adapter integration | New core receipt tests | Search/inspect is not read/coverage; an ordinary harness read remains unknown; optional trace failure is reported honestly. |
| C8 | Contract + neutral CLI/APM installation | New root package/example tests and minimal package consumer proof | Examples match real schemas; standalone CLI works without APM; fresh APM instructions resolve the installed launcher, guide and templates without organization-specific variables or old package imports. |
| C9 | Acceptance cases + walkthrough | Reuse suitable S1 measurement functions/case structure without legacy imports | Expected evidence is available with selective reads; measure returned preview bytes, actual body bytes/lines read, misses, irrelevant reads and elapsed time. |
| C10 | Adapter integration + installed CLI smoke | New doctor cases over temporary config/source/inbox paths and minimal environments | Quick healthy path, missing/wrong workspace, bad catalog, unavailable dependency/source, unwritable probe/cleanup failure, no secret dump or launchctl mutation; valid empty corpus is healthy. |
| C11 | Pure predicate + filesystem/Git integration + skill walkthrough | Temporary sources/remotes, simulated GitHub responses and on-demand skill evidence | Existing current-user PR reused; none creates one; other-user/unrelated PR untouched; main merged normally; active/incomplete activity visible; failed/uncertain publication or edited/new signals retained; optional originating-session handoff falls back to self-contained processing. |
| C12 | Setup-skill contract + provider adapters + real-harness E2E | Temporary fresh consumers plus opt-in disposable Codex/Claude/Copilot automation runs | Setup asks only for the absolute config path, registered scopes and any opted-in publication details; derives the remaining paths/defaults, creates/reuses the scaffold-local VENV, installs dependencies, compiles all three supported APM targets, registers/updates one visible automation per available provider, invokes `knowledge-compound` on run-now, records harness/session/automation provenance, and leaves pause/remove controls. Missing tools/auth, invalid scopes/config, duplicate task markers and unavailable session callbacks stop or fall back without secrets, duplicate runs or data loss. |

Required semantic/behavior cases include:

| Scenario | Required observable behavior |
| --- | --- |
| General testing + TypeScript + CDK vs React-only rule | `[any, typescript]` and `[any, aws-cdk]` retain general/TS/CDK applicability and reject React-only applicability. |
| PostgreSQL, MySQL and relational family | PostgreSQL query explicitly including the family finds generic/family/PostgreSQL/shared-engine rules and rejects MySQL-only rules. |
| Family-only document with concrete-only query | Does not match; catalog membership does not secretly expand the request. |
| Unregistered entity or misspelled engineering concern | Structured validation error, not an empty successful search. |
| Ambiguous feature alias | Separate labelled candidates; no silently selected feature ID. |
| Feature extension discovers infrastructure work | Initial feature/workflow search leads to system context, relevant provisioning/testing rules, procedures and limitations. No fixed pass count. |
| Static-site technology choice | Search the capability/guidance before applying a provider filter; the suggested provider does not hide the approved alternative. |
| Large runbook with remote prerequisites | Return procedure location and reference/outline information; agent reads the necessary prerequisite/constraint sections without receiving the full file by default. |
| First setup with no virtual environment or installed launcher | Ask for/confirm only the absolute config path and registered scopes, derive/create the scaffold-local VENV, install the package/dependencies, and prove `describe`/`doctor` from the same harness process; do not edit shell startup files or expose credentials. |
| Missing Python/`uv`/Git/GitHub authentication or invalid source/scope/publication input | Report the exact missing prerequisite and remediation, leave the workspace/signals unchanged, and do not register an automation that cannot run safely. |
| Setup repeated for an existing automation | Find the stable task marker, update the existing native automation or report an ambiguity, and never create a duplicate for the same signal store. |
| Native daily automation run-now in Codex, Claude or Copilot | The harness starts the installed `knowledge-compound` skill with the explicit config and runtime path; the run writes activity/session provenance and produces the same safe publication/disposition behavior as a manual invocation. |
| Originating session available, absent or belonging to another harness | Attempt handoff only with the safe opaque handle and supported native callback; otherwise compound from the self-contained signal, without copying conversation content or blocking the run. |
| Multiple automations target one signal store | Surface the ownership conflict and avoid concurrent draining; a single owner is required unless the user explicitly separates signal stores/configurations. |
| User pauses/removes or disables an automation | The native harness exposes the task as paused/removed and future runs do not drain signals; existing activity and signals remain inspectable. |
| No matching document | Success with zero results and truthful scan status. |
| Invalid frontmatter, duplicate YAML keys, alias cycle or invalid schema | Explicit validation failure; no permissive parser fallback. |
| Missing/unreadable source, file changed during scan, interruption | Error/incomplete status; no unqualified absence claim or destructive action. |
| Result/link/outline overflow or corpus changed between pages | Explicit truncation/continuation; stale snapshot detected. |
| Broken/external/cyclic document links | Visible target status; no recursive expansion or automatic external fetch. |
| Canonical path absent, outside-root reference, symlink alias or replacement race | Boundary validation holds; do not read or delete outside the intended location. |
| Source signal edited/new signal added between listings | Complete-byte fingerprints change; listing does not mutate or remove any entry. |
| Capture in a linked worktree | Durable project identity and configured scopes remain intact; the worktree does not relocate the inbox. |
| Simultaneous captures or output already exists | Unique writes or explicit collision error; no overwrite, shared-file lost update or partial completed file. |
| Missing origin configuration | Explicit context error; do not substitute the knowledge checkout's scopes. |
| Doctor in a harness with different executable/config visibility | Report the actual running locations and mismatch/missing setup with targeted remediation; do not infer another process's state. |
| Doctor read mode over a large corpus | Validate setup/catalogs without scanning knowledge bodies or writing probe files. |
| Doctor write probe outside allowed storage or cleanup failure | Refuse unsafe probe, or report failed cleanup explicitly; never claim full readiness. |
| Fresh APM consumer with no old package or environment | Installed instruction discovers the new launcher/config and guide; retrieval and on-demand compounding are usable without porting unrelated skills. |
| Compounding succeeds, publication fails or inputs change | Only verified selected unchanged inputs drain; failure/ambiguity retains inputs and the activity record reports the actual outcome. |

Use fictional fixtures for representative walkthroughs: reusable infrastructure constructs and tests, event dispatch behavior, and integration onboarding. Establish expected evidence before measuring results. Evaluation against a populated business corpus belongs to its adopter and must not add organization-specific interpretation to the runtime.

Do not claim a percentage accuracy or token improvement before running the comparison. Record both positive and negative cases, preview bytes separately from body bytes, and any relevant constraints missed by partial reading. S1's synthetic baseline is measurement infrastructure, not proof of the new retrieval design. Initial scale proof is the bounded fixture/corpus workload; 400-engineer adoption remains unproven.

Planned commands, from the repository root, use the new package environment:

```bash
uv run pytest -q tests/unit/domain
uv run pytest -q tests/integration tests/acceptance
uv run pytest -q tests
uv run ruff check .
uv run ruff format --check <changed-python-paths>
```

Configure root pytest discovery to `tests/` and root Ruff to the new source/test tree, excluding untouched legacy packages. The core's full suite must pass without an organizational corpus, old environment variables, APM install, global config or network. Separate R6/R7's APM/install/workflow proof so it does not slow or couple the pure domain suite. Run manifest, resource, compile/install and prose-consistency checks for the new neutral APM package and any changed distribution surfaces; prove the declared supported APM version rather than borrowing a different version's result. R7/R8 also run the setup skill and a disposable real-harness automation smoke for each supported target, using run-now/one-shot invocation rather than waiting for a wall-clock schedule. Do not inherit old corpus-dependent failures and then deselect them. Keep opt-in external-corpus measurement and authenticated harness runs explicit. New paths in these commands are delivery targets, not existing folders.

### 2.3 Deployment

This adds a new local Python package and CLI to the continuing APM skills/knowledge repository, with no cloud deployment or database migration. The user reviewed the plan and authorized R1, with a review stop before each subsequent slice. Preserve the APM manifests, package sources and their distribution role throughout. A separate consolidation of completed worker changes may preserve useful prior work in the meantime; it is neither a dependency nor permission to port the experimental runtime into the new core.

Use fresh neutral example configurations and temporary inboxes throughout development. R4 introduces the Markdown signal contract coherently across its new writer/reader/validator. R5 proves installed standalone CLI/templates; R6 proves fresh APM consumption; R7 proves the setup skill, native automation registration and on-demand compounding against isolated fixtures; R8 proves the same automation path in supported real harnesses and completes the end-to-end retrieval/consumption evidence. Do not switch the user's existing harness, globally replace entrypoints, migrate old knowledge or mutate existing signal inboxes. If unexpected real user files are found, retain and report them; absence of a migration requirement is never permission to discard data.

Keep the new package's README/help, schema descriptions, templates, examples and guide synchronized with its behavior. Verify installation in an isolated neutral environment, not the user's installed copies. Update the minimum manifests/projections/resource bindings needed for the new knowledge package in R6/R7. Broader existing-skill ports, including every retained skill's templates/references/scripts, remain a separate story after this contract is proven. Do not publish a release, re-enable copied GitHub Actions or refresh unrelated APM lock inventory. Existing lock/runtime-version drift must not silently become a dependency of the new runtime.

The included on-demand compounding workflow retains the simple current-user eligible-PR policy, ordinary merging of main, advisory JSONL activity log and verified-publication-before-drain behavior. It consumes the new configuration, Markdown codec, catalogs, search and validation. The setup skill registers a native harness automation that invokes this workflow, but the plan supplies no repository scheduler, bespoke GitHub service, optional hook framework or automatic compounding loop.

Rollback is a source-revision revert before package release; runtime inbox contents are preserved independently. No legacy compatibility layer, source-corpus migration or backwards-format guarantee is part of rollback. Report each slice's actual branch/commit and proof. Completion means a usable fresh retrieval/compounding installation; it does not claim that the broader existing skills or full engineering harness have been ported.

## 3. Appendix

### 3.1 Context Used

- User discussion on 2026-09-09: accepted agent-planned searches, explicit filters, progressive whole/partial reads, links, `engineering_concerns`, catalog IDs, named scopes, technology families, common compounding rules, Markdown frontmatter and a pure `domain` module. Subsequent steering permits a fresh neutral runtime, requests a folder structure, realistic CLI examples, a quick health check and adapted knowledge templates, and reaffirms the permanent APM role. Latest scope is usable fresh retrieval, first-run setup and compounding; broader selected skill ports, including their templates/references/scripts, are a separate story.
- User decision on 2026-09-10: restore the brainstorm's harness-native scheduled compounding direction. Add a separate first-run `knowledge-setup` skill that gathers configuration, provisions the runtime and registers/updates a visible native automation for Codex, Claude and Copilot; the automation invokes `knowledge-compound`. Record safe harness/session/automation provenance in signals and activity records, support run-now real-harness proof, and keep scheduler implementation outside the repository. Here “compiling” means recurring compounding; APM `compile` remains the setup-time projection step.
- [Local instruction source](../../.apm/instructions/scaffold-local.instructions.md): empty scaffold, original-repository isolation, synthetic tests and package synchronization. User direction supersedes its stale requirement to preserve organization-specific entrypoints.
- Worker branches/commits listed above: S2 shared `knowledge-discovery-contract.md`, S3 output transport, S4 description budget, S5/S7 signal safeguards and S6 limitations naming are reference inputs for selective reuse/porting, not dependencies of the new package.
- [CLI contract examples](knowledge-cli-examples.md) and [fictional fixtures](cli-examples/README.md): nine core CLI methods, health-check failure boundaries, explicit family/general filters, negative searches, ordinary partial reads, and capture/compounding flow. They are planning inputs, not implemented runtime tests or a copied organizational corpus.

### 3.2 Additional Notes

Planning validation on 2026-09-09 checked ten neutral knowledge documents, one Markdown signal, catalog identifiers, workspace paths, ordinary links, expected general/family/engine rule selection, and the runbook's exact bytes, physical lines and fingerprint. The CLI companion contains 26 shell examples and 18 parsed structured requests covering all nine core methods. Shell syntax, document links/anchors, eleven capability rows, eight delivery slices and Git whitespace checks passed. These are static checks of review material; the new CLI, templates and skills have not been implemented or executed. Broader corpus/latency/installed-harness proof remains assigned to delivery slices.

Knowledge lookup for these plan updates: previewed/read `operating-rules/update-existing-documentation-before-creating-new-structure.md` and `operating-rules/keep-apm-package-surfaces-synchronized.md` through receipt `6c5a5e6b24f7`; directly reread the selected documentation rule. Facts used are their existing-owner and package-consistency requirements, cited at line 29 in the source links above. No missing-knowledge conclusion was drawn. The main checkout's pre-existing brainstorm modification was verified byte-for-byte unchanged.

The user's explicit request to create this plan satisfied the planning skill's preference/analysis checkpoints after the preceding design discussion. The user subsequently authorized building one slice at a time without an additional build-orchestration skill, stopping for review between slices. Choosing a fresh package over extending the legacy tools follows the latest user steering; existing work remains preserved for later selective adaptation.

Markdown with YAML frontmatter unifies the authored-file envelope, not every data representation. Signal and knowledge schemas remain different; catalogs/configuration use the same YAML dependency, and append-only activity/receipt records remain runtime JSONL. There must be one implementation of each relevant parser and matching rule, not competing fallback semantics.

Knowledge signals for this planning task: none. The observations above are already-known refactor inputs or explicit new-design requirements, and the plan records them without mutating the original organization's knowledge/inbox.

#### R1 Implementation and Review Checkpoint

Implemented on `build/r1-domain`, based on approved-plan commit `4f57728`, on 2026-09-09. R1 is ready for user review. R2-R8 remain unstarted; no new CLI or file adapter is claimed. The root README now describes the actual package state and includes an executed Python usage example.

- Added an installable Python >=3.11 package with no runtime dependencies, pinned development tools and isolated root quality gates. APM packages remain a separate permanent surface.
- Added immutable models and strict parsers for combined catalogs, knowledge metadata, search requests and signal metadata/body. Unknown IDs, conflicting source definitions, malformed input and unsupported schema keys return structured validation errors. Authored text is preserved; query duplicates are normalized after validating their original positions.
- Implemented same-field OR/cross-field AND, missing-versus-`any`, explicit scope/family/source filters and direct literal label/alias alternatives. Reusable prepared queries resolve relevant aliases once per query. They do not infer task intent, broaden facets, order/page results or touch files.
- Scope catalogs accept explicit parents, validate references/cycles and expose an explicit ancestor helper. Signal origin remains separate from any future canonical applicability. File existence, YAML parsing and live workspace identity checks remain adapter responsibilities.

Verification: all 243 new tests passed, comprising 235 in-memory domain cases and 8 architecture/import-guard cases. Three final warm domain runs reported **0.62s, 0.39s and 0.54s** on Darwin 25.5.0 arm64, Python 3.11.8, pytest 9.0.3. These are pytest-reported durations excluding environment installation; there are no timing assertions. Ruff lint/format checks, strict mypy, Git whitespace checks, sdist/wheel construction and an isolated installed-package smoke from `/tmp` with an empty environment passed. The wheel imported from its isolated site-packages without the legacy package or runtime dependencies.

The ten fictional knowledge fixtures, catalog and Markdown signal also passed the R1 parsers after temporary YAML decoding. The explicit general/family/PostgreSQL request selected exactly the general testing, relational-index and PostgreSQL-index rules. This is schema/matching proof, not implementation of R2's strict file codec or R3's retrieval commands. Existing APM runtime tests and real-corpus consumption benchmarks are outside this slice's changed surfaces and remain assigned to later proof.

Independent worker review covered catalog/matching/schema behavior and packaging/boundary correctness. It led to fixes for original input error indices and repeated per-document alias preparation; the final bounded review reported no material findings. A narrow development measurement over 100 tiny documents and 5,001 catalog records improved from approximately 1.310s to 0.0074s with prepared queries, including preparation. This is not a corpus retrieval benchmark or an accuracy claim.

The pre-existing brainstorm modification was verified unchanged (SHA256 `307eafdd967f6c7916e81d076999022a6e6bdd31fac3c57f250da4ff44db7f37`). An unrelated deletion of `.claude-plugin/marketplace.json` appeared during the turn; it was preserved outside the R1 commit, without inferring its origin or restoring it. No original organizational knowledge, installed harness, existing inbox or legacy package was changed by R1. Knowledge signals: none, because the work implements requirements and verification already recorded in this plan.

#### R2 Implementation and Review Checkpoint

The user accepted R1 commit `b676893` and authorized R2 only. R2 is implemented on `build/r2-adapters`, based on that commit, and stops for review before R3. C2 is complete. C6 has its codec but not signal capture; C10 has standalone doctor proof but its compiled-harness portion remains with R6. No later capability is marked complete on partial evidence.

**Delivered:**

- One strict UTF-8 YAML/JSON mapping reader and Markdown-frontmatter serializer/parser, using pinned PyYAML 6.0.2. They reject duplicate/nonstring/merge keys, malformed input, unsupported tags and alias cycles without a fallback parser. The same numeric/string/boolean rules apply when writing and reading. Signal timestamps stay strings; only true/false resolve as booleans. The codec preserves exact bodies and physical LF/CRLF/CR line ranges, byte counts and SHA256 fingerprints.
- Limits of 1 MiB for structured config/catalog/request inputs and 8 MiB for Markdown files, plus 64 YAML collection levels and 20,000 parsed/expanded nodes. These are format-resource limits, not retrieval-quality heuristics.
- Pure workspace schema validation and explicit config-relative adapters with combined catalogs, registered scopes, conflict diagnostics and source identity snapshots. Empty scopes/catalog registries and an empty source directory are supported; at least one source must be configured. Config/source/request aliases resolve before guarded access, while source-relative document paths reject internal symlinks. Source roots may not overlap. Optional signal storage is checked separately so doctor can distinguish valid read access from invalid write setup.
- Bounded regular-file reads, no-follow descriptor traversal, changed-file checks, missing-root containment checks and safe directory handles. No environment fallback or knowledge corpus scan is introduced. Paths use local POSIX semantics; shell variables, home expansion and remote URL roots are unsupported.
- An installed `agent-knowledge` launcher providing `describe`, `context`, `catalog` and `doctor`, JSON/text output and exit categories 0/2/3. Catalog selection reuses R1's text and facet semantics; results retain all ambiguous candidates and provenance. Paging uses stable ID order, truthful totals and a request/config/catalog-bound cursor. Invalid/stale cursors fail explicitly.
- Doctor reports this invocation's runtime, config/catalog/source checks and separate read/write readiness. Its default creates nothing and reads no knowledge bodies. Explicit write mode probes only existing validated signal storage, preserves replacements and reports write/close/cleanup failures. It does not create directories or repair setup. Installed guide/templates are reported as pending R5, not nonexistent paths.

**Verification:** all **503 tests passed in 9.38s** in the final combined run: 324 pure domain cases, 81 codec cases, 7 schema-description cases, 83 integration cases and 8 architecture guards. Root Ruff lint and check-only formatting, strict mypy (19 source files), Git whitespace checks and sdist/wheel construction passed. Independent reviews of configuration/filesystem and public CLI/pagination found no remaining material findings after fixes for explicit request aliases and deeply nested cursor JSON; both failures were reproduced and covered by regression tests. Other tests cover malformed YAML, scalar round trips, ambiguous catalog aliases, changed snapshots, missing/unreadable paths, symlink redirection, changed file identities and failed probe cleanup.

The built wheel was installed into `.cache/r2-install`. Thirteen actual launcher invocations passed from `/tmp` with an empty environment: schema/field discovery, explicit context, entity alias and technology-family discovery, catalog pagination, healthy read/write checks, workspace mismatch, absent config and an empty source. Imports came from the wheel's isolated site-packages. The strict codec/domain also validated all ten fictional knowledge files and the signal; the runbook remains 1,402 bytes/41 lines with frontmatter 1-11 and body 12-41. The local ignored smoke driver is `.cache/r2-installed-smoke.py`. No real organizational corpus, remote or installed harness was used.

**Timing caveat:** three recorded warm domain runs took **3.18s, 3.29s and 2.11s** on Darwin 25.5.0 arm64 / Python 3.11.8. A profiling run took 2.77s; its slowest two calls were the existing large-catalog and deep-hierarchy stress cases at 0.19s and 0.13s. Session timings varied considerably (an earlier full run took 150.32s); this does not establish the cause or prove a regression. The proposed under-two-second domain target is not demonstrated for R2 on these runs. No flaky timing assertion or unsupported speed claim was added.

**Remaining boundaries:** R3 owns actual knowledge search and heading/link navigation, R4 owns signal capture, R5 owns authoring resources/full validation/receipts, and R6 owns fresh compiled-harness integration. CLI examples and the root README now distinguish implemented commands from those future methods. No APM distribution surface changed in R2; its existing skill/manifest/compile gates were not used as substitutes for the new package proof.

The inherited brainstorm modification remains byte-for-byte unchanged at the R1 hash above, and the unrelated marketplace manifest deletion remains outside this slice. Knowledge lookup previewed and then read the existing typed-boundary and package-synchronization rules; the implementation uses validated specific types and keeps documentation aligned with actual availability. The user's fresh-core plan continues to override inherited compatibility/API-service defaults. Knowledge signals: none, because these findings and new contract decisions are already recorded in this plan without changing the original organization's knowledge.


#### R3 Implementation and Review Checkpoint

The user accepted R2 commit `9af1d75` and authorized R3 only. R3 is implemented on `build/r3-retrieval`, based on R2, and stops for review before R4. C3 and C4 are complete for the documented local contract. Broader retrieval quality/consumption measurements remain with R8; this checkpoint makes no enterprise-scale claim.

**Delivered behavior:**

- `search` applies the existing explicit OR/AND, `any`, family and direct-alias semantics over selected configured Markdown sources. All selected documents are validated before a successful result, including documents excluded by facets. Invalid content, missing selected roots and changed scans remain errors; a valid empty result certifies only the supplied predicates. An unrelated unavailable corpus does not block an explicitly selected healthy source, provided the configured catalogs are available and valid.
- Results contain authored metadata, absolute/source-relative paths, bytes/physical lines, frontmatter/body ranges, fingerprints and contributing match locations. Bodies and snippets are not returned. Metadata locations use exact authored field ranges from the shared codec, including folded scalars and YAML alias-use positions. Body locations use exact physical line spans and the smallest section enclosing the entire match, including phrases crossing sibling headings.
- A complete scan retains lightweight candidate identities/fingerprints and metadata-hit ordering. Detailed previews are built only for the selected page. Each file returns at most 20 detailed locations; the existing continuation input also accepts that file's opaque `match_continuation` to page more. File-page and match-page outputs name their channel, report truthful counts and use request/snapshot-bound cursors. Cursor target hashes keep tokens bounded for long identifiers/paths. Each continuation rescans; no index, semantic engine or result-padding heuristic was introduced.
- `inspect` loads one selected document and returns its preview plus pageable physical-order outline/outgoing links. The pure Markdown scanner supports ATX headings, nested/duplicate Unicode anchors, fenced/indented code shielding and common inline/reference links. Standalone HTML comments and recognizable raw HTML blocks do not invent navigation. Unsupported Setext/container syntax is documented rather than assigned guessed section boundaries.
- Links expose path status separately from anchor status. Configured relative/absolute and cross-source links can resolve without reading linked bodies; external, missing, unresolved and unsafe links retain reasons. Same-file anchors are checked, other-file anchors remain unverified. Lowercase `.md` and non-Git-metadata eligibility agree with corpus reads. Cycles never trigger recursive body loading.
- The guarded corpus adapter includes hidden Markdown, ignores ignore-file exclusions, skips real `.git` directories and rejects internal symlinks/nonregular documents. Selected-source inventory/configuration checks and selected-file rereads detect changes during retrieval. They do not provide an atomic filesystem snapshot, remote freshness or a lock on subsequent ordinary harness reads.
- Catalog/search/inspect share the opaque cursor helper. `describe`, CLI dispatch, README, fixture notes and realistic CLI examples now advertise six available methods and explain line precision, location paging, syntax limits and progressive links. Guide/templates/validation, receipts and signal commands remain with their assigned later slices.

**Verification:** `uv run pytest -q` passed **694 tests in 25.80s** after the final source-selection fix (an earlier full pass was 692 in 16.73s). Ruff, check-only formatting and strict mypy pass; mypy covers 25 source files. The domain import boundary remains covered. Three recorded warm domain runs passed **415 tests in 3.48s, 3.95s and 2.96s**. The proposed two-second target remains unproven; timings are evidence, not flaky assertions or a performance claim.

`uv build --out-dir .cache/r3-dist` built an sdist and a wheel from that sdist. The wheel was installed into isolated `.cache/r3-install`. The actual installed launcher passed **34 CLI invocations** from `/tmp` with an empty environment, exercising all six methods, JSON/YAML input, exact general/family/PostgreSQL rule selection, two feature/workflow discoveries, all ten files through pagination, location/outline pagination, stale cursors/fingerprints, valid empty and invalid-ID outcomes, invalid-content failure and an empty corpus. The runbook retains 1402 bytes / 41 lines with procedure lines 21-32; an ordinary file read selected prerequisites plus procedure at lines 15-32 (18 lines). Inspect still succeeds when a linked file's contents are deliberately malformed, confirming that linked content is not validated or recursively fetched. Local reproducibility artifacts are `.cache/r3-installed-smoke.py` and `.cache/r3-installed-smoke.json`; these are disposable evidence, not package resources.

Focused regressions cover multi-line formatted phrases, metadata-only matches, full-span section enclosure, detailed-location work bounded to one selected page, a changing source during preview construction, long-identifier cursor roundtrips and unrelated unavailable sources. Independent reviews led to corrections for HTML shielding, whole-span sections, link/corpus eligibility and selected-source access. The final review found no further issue in the requested query/location/pagination/mutation boundaries.

The fictional source is the only committed knowledge fixture; no organizational corpus, original repository, installed harness or existing signal inbox was modified. Existing APM package distribution remains unchanged; fresh APM consumption is R6. The inherited brainstorm modification remains byte-for-byte unchanged at SHA256 `307eafdd967f6c7916e81d076999022a6e6bdd31fac3c57f250da4ff44db7f37`, and the unrelated marketplace deletion remains outside this slice. Knowledge lookup for this slice previewed and read the typed-boundary and package-synchronization rules already recorded above. Knowledge signals: none, because implementation requirements and verification findings are captured in this plan without changing the original organization's knowledge.


#### R4 Implementation and Review Checkpoint

The user accepted R3 and authorized R4 only. R4 was implemented on `build/r4-signals`, based on `2eb4fd0`, then reviewed, accepted, committed as `6d25fba` and pushed to main. It delivers Markdown signal capture/listing and origin validation. C6's codec/capture/discovery behavior is proven; its later compounding/consolidation proof remains with R7, so the full capability checkbox stays open. C5's authoring templates and complete validation were the next R5 scope; C11's publication/log/draining workflow remains R7. The R5 checkpoint below records the subsequent implementation.

**Delivered behavior:**

- New pure `domain/signals.py` owns strict record/list request parsing, minimal workspace routing and exact origin comparison. `origin.workspace_id` and durable project path must match; scope/source ID sets are order-independent but must equal the explicit configuration. Empty origin scopes are valid only as an explicit list, matching a workspace with no assigned scopes. Canonical knowledge scopes and signal source IDs remain nonempty. Existing signal parsing still validates evidence structure, registered hints and a nonblank Markdown claim.
- `signal record` takes an authored `.md` path relative to the configuration directory and preserves its exact bytes. It rejects signals authored inside canonical roots, bad schema/hints/claims and mismatched origin. It creates a unique timestamp/UUID filename in `projects/<durable-code-root-relative-checkout>/` or deliberately non-project `shared/`, leaving the authoring input untouched. It is not an idempotent upsert and does not search canonical bodies, deduplicate claims, broaden applicability, contact GitHub, create PRs or drain inputs.
- The origin adapter uses the explicit configuration's Git context with inherited Git overrides disabled. It verifies primary checkout/common-dir identities and worktree back-pointers, including relative metadata. A temporary producer outside `code_root` maps back to its durable primary. Nested project paths and equal basenames remain distinct. Bare, separate-Git-directory and submodule associations are unsupported rather than guessed. The durable primary must be below `code_root`; a non-Git context cannot silently become a project bucket.
- Before recording, the scaffold destination is checked independently: an existing directory-only scaffold or primary-checkout subdirectory is valid; a linked-worktree destination is rejected without remapping. Local Git is required for these checks but no Git repository or GitHub account is required for shared capture. The explicit scaffold directory must exist. The adapter may create only needed inbox subdirectories, using descriptor-based no-follow traversal and canonical-overlap checks even when canonical roots are absent. This repository already ignores `ai/signals/`; other configured destinations require ignore setup. Runtime capture does not change or enforce Git ignore policy.
- File publication uses an exclusive temporary file, complete writes, fsync and a no-overwrite hard link before exposing a final `.md`. Pre-publication failures clean only the invocation's identifiable temporary inode; collisions preserve existing files. Same-inode size/mtime changes, replacements and post-publication/sync/cleanup uncertainty are diagnosed. A final complete-byte read verifies the returned fingerprint against the authored snapshot. Uncertain published paths and authoring inputs are retained; rechecks do not promise a lock against later edits or hostile ancestor renames.
- `signal list` is read-only, with an absent inbox/bucket yielding no signals. It scans direct files in the exact project bucket, optionally adding `shared/`; it never recursively claims another nested project's entries. A non-Git originating config must explicitly request shared entries. Foreign-workspace envelopes are counted as `other_workspaces` before catalog-specific validation; they require their own configuration for processing. Selected signals receive complete schema/catalog/origin checks. Invalid metadata names both the file and field. Malformed/unreadable envelopes and legacy YAML in selected buckets remain visible errors and are preserved.
- Listing returns metadata, evidence pointers, file paths, complete-byte fingerprints and physical body/frontmatter ranges, without claim bodies. Deterministic path ordering and request/context/inventory-bound continuation support paging. All listed bytes contribute to the scan fingerprint; new/edited/deleted inputs invalidate an old continuation. Resolved signal-storage/code-root paths now also participate in the shared configuration fingerprint, so retargeting aliases cannot pass an unchanged-context check.
- CLI syntax, `describe` schemas, remediation, README and realistic examples expose the eight methods available at the R4 boundary. R5 adds `validate`, installed authoring resources and optional receipts; fresh APM integration and broader skill/template ports remain unchanged and are assigned to R6 or later.

**Verification:** the full root suite passed **854 tests in 9.35s**. Ruff, check-only formatting and strict mypy pass for 29 source files. Three warm, pure domain runs passed **471 tests in 0.29s, 0.22s and 0.20s**; the recorded two-second target is met for these runs without a wall-clock assertion or an inferred explanation for earlier host variability. The import-boundary check remains green. A later installed CLI check caught invalid storage configuration being categorized as runtime failure; it now uses exit 2 for temporary/bare/unsupported/outside-code-root configuration, while runtime Git/I/O failures remain exit 3. All 80 focused origin/CLI/operation tests passed in 7.47s after this correction; lint, formatting and typing checks passed again.

`uv build --out-dir .cache/r4-dist` built the sdist and its wheel, which was installed into isolated `.cache/r4-install`. The actual installed launcher passed **51 invocations** covering all eight available methods from `/tmp` with an empty environment. This repeated the R3 retrieval/navigation cases, then proved exact-byte capture, input retention, unique repeated records, body-free listings, stale list cursors, explicit shared capture/filtering, foreign-workspace counting, invalid claim/legacy-input preservation and capture independent of canonical body validity. A temporary producer worktree outside code_root recorded into the primary project's durable inbox; removing that test worktree left the records available. A linked-worktree scaffold destination was rejected before creating an inbox. The committed fictional data was copied into isolated temporary repositories; no real inbox was used. Local disposable evidence is `.cache/r4-installed-smoke.py` and `.cache/r4-installed-smoke.json`. The first driver comparison was corrected to compare resolved macOS temporary paths; a subsequent run exposed and verified the exit-category correction described above.

Independent bounded reviews led to explicit filename diagnostics, storage-alias fingerprinting, publication uncertainty preservation and destination-worktree rejection. The relevant regressions failed before their fixes. Final checks confirmed the fixes without extending the slice to compounding or authoring resources.

**Publication of prior slices:** the user explicitly asked to publish R1-R3 during this slice. Main fast-forwarded through their separate commits, including the plan and fictional examples. Push used the requested personal token in process environment only; the private repository and authenticated identity were verified, and GitHub's main ref was confirmed as `2eb4fd0d2472f9f433d7793745571de9d3db7fc3`. A clean temporary publication worktree kept R4 edits out of the push and was removed afterward. No force push, PR, real signal capture or original organizational corpus write was performed.

The pre-existing brainstorm edit retains SHA256 `307eafdd967f6c7916e81d076999022a6e6bdd31fac3c57f250da4ff44db7f37`; the unrelated marketplace deletion remains outside this slice. Knowledge lookup previewed/read native quality-gate and check-only formatter rules, with worker checks for typed boundaries and package synchronization. The accepted fresh-core design continues to override inherited compatibility/API-service defaults. Knowledge signals: none, because implementation requirements and review findings are recorded here without altering the original organization's knowledge.

#### Package and Test Folder Refactor Before R5

On 2026-09-10, after accepting R1-R4, the user approved grouping the core into `domain`, `application`, `entrypoints/cli` and `infrastructure`, then explicitly requested matching test directories. This is a separate refactor before R5. Its scope is moving modules, updating imports and the installed console entrypoint, mirroring the tests, and synchronizing the existing documentation. Public CLI commands, request/response contracts and retrieval/signal behavior stay the same.

The original `application.py` becomes `application/discovery.py`; `retrieval.py`, `doctor.py` and `pagination.py` move into that package; `signal_operations.py` becomes `application/signals.py`; and `responses.py` becomes `application/diagnostics.py`. `cli.py` and `contracts.py` become `entrypoints/cli/main.py` and `entrypoints/cli/contracts.py`. Existing `adapters/` modules retain their filenames under `infrastructure/`. Domain modules remain in place. Tests group the same responsibilities beneath their existing unit/integration separation, with shared factories and the domain boundary guard at the test root.

**Verification:** the full core suite passed **857 tests in 12.79s**, including all existing behavioral cases and three additional prohibited-import examples for the relocated layers. Ruff lint/check-only formatting, strict mypy over 32 source files and whitespace checks passed. Comparing all 29 existing source modules with `6d25fba` confirmed identical non-import ASTs; only imports, package locations and new package initializers changed. The domain code and fast unit test location remain unchanged.

`uv build --out-dir .cache/layout-dist` built an sdist and wheel. A fresh isolated installation passed **51 CLI invocations across all eight available methods** from `/tmp` with an empty environment, including search/navigation, durable signal capture/listing, errors and continuation handling. Wheel inspection confirmed the new package initializers, `py.typed` and `agent_knowledge.entrypoints.cli.main:main` launcher target, with no old adapter package or root CLI/application modules. Disposable proof is stored in `.cache/layout-installed-smoke.py` and `.cache/layout-installed-smoke.json`.

The unrelated brainstorm modification retains its recorded SHA256 and the marketplace deletion is preserved. The legacy preflight, explicitly scoped to this scaffold, cannot load the intentionally excluded `.knowledge` corpus; verification follows the local scaffold instructions using neutral fixtures, without changing the original repository or installed organizational setup. No APM distribution or organizational knowledge surface changed; live-corpus proof remains with a populated consumer in R8. Knowledge signals: none, because the approved structural decision and its proof are recorded here. This refactor is the approved pre-R5 structural change and does not start R5.

#### R5 Authoring, Validation and Trace Checkpoint

R5 was implemented on `build/r5-authoring`, based on the latest main refactor
`3f4902e`, accepted, and pushed to main as `02e9a27`. The slice delivers the
authoring and validation surfaces needed before fresh APM consumption; R6 owns
compiled-harness/APM integration and R7 owns on-demand compounding.

**Delivered behavior:**

- Shipped eleven Markdown resources through the Python package: one
  organization-neutral agent contract, ten knowledge templates covering the
  nine kinds (with a service/procedure pair for `runbook`), and one Markdown
  signal template. The templates use the shared `knowledge.v1` and
  `knowledge-signal.v1` envelopes,
  registered identifiers and visible placeholders; they contain no organization-specific
  corpus or default organization policy.
- Added strict `validate`, which requires exactly one explicit target family:
  all documents in selected configured sources, source-qualified document
  references for a focused edit, or authored Markdown signal files. It reuses
  the same workspace/catalog/codec/schema/link rules as retrieval, reports
  metadata-only file rows and all collected broken local references or missing
  same-file anchors, and returns exit 2 for invalid content. It never judges
  claim truth, fetches evidence, publishes changes or moves files.
- Added optional append-only JSONL receipts to direct `search` and `inspect`
  application calls. Each event records the normalized request, relevant source
  IDs, returned file identities/fingerprints and `body_read: unknown`. A failed
  optional write is reported in the receipt result while the successful
  operation remains successful. The core does not infer ordinary harness reads.
- Added neutral executable examples containing ten knowledge documents, a
  catalog, workspace configuration and one Markdown signal. Updated the README,
  CLI contract examples and package resource discovery to describe the current
  nine-method CLI surface and the R5 validation/resource behavior.

**Verification:** the full root suite passed **873 tests in 9.68s**. Focused
R5 tests cover target parsing, valid/invalid source/document/signal validation,
broken local links and anchors, append-only receipt records, receipt failure
without parent creation, installed resource discovery and CLI exit behavior.
Ruff lint and check-only formatting, strict mypy over 35 source files, and
`git diff --check` passed.

`uv build --out-dir .cache/r5-dist-1` built the source distribution and wheel.
The wheel was installed in `.cache/r5-install-1`, then invoked from `/tmp`
with an empty environment. Installed `describe` reported the guide and all
eleven template paths from site-packages; installed `doctor`, `context`,
`catalog`, `search`, `inspect` and `validate` succeeded against the neutral
fixture. The installed package imported from its isolated site-packages path,
with no repository-relative source import or organization-specific runtime dependency.

The pre-existing brainstorm modification and unrelated marketplace deletion
remain outside this slice. No original organizational corpus, installed
harness, remote branch or existing signal inbox was changed. Knowledge lookup
for this implementation previewed and read the package-synchronization,
documentation-owner and test-factory rules before source edits. Knowledge
signals: none, because the work implements the already accepted contract and
its verification is recorded here without changing central or local
organizational knowledge.

#### R6 Fresh APM Consumption Checkpoint

R6 was implemented on `build/r6-fresh-apm`, based on accepted main commit
`02e9a27`, reviewed, committed as `4c307b4`, and pushed. It proves the minimal fresh APM
installation boundary; it does not start R7 compounding or port the inherited
organization-specific skills.

**Delivered behavior:**

- Added the neutral `packages/knowledge-agent-pack` with one source-owned
  discovery instruction. It teaches a consumer to locate the installed
  `agent-knowledge` launcher, use `describe` for the installed guide/templates,
  pass an explicit workspace configuration, discover catalog IDs, search
  selectively, preview before ordinary file reads, follow links progressively,
  validate authored files and capture durable signals.
- Replaced the root APM manifest's inherited dependency list with the neutral
  package and explicit `codex`, `claude` and `copilot` targets. The lockfile is
  regenerated against APM `0.29.0` and contains only the neutral package; no
  inherited package or organizational corpus is installed by the fresh proof.
- Added `tests/e2e/fresh-consumer-smoke` and its Python runner. It creates a
  temporary consumer, builds and installs an isolated wheel, clears ambient
  organization variables, installs/compiles all three APM targets, runs the
  consumer APM audit, verifies source/installed guide and template parity, and
  exercises installed `describe`, `doctor`, `context`, `search` and missing
  configuration diagnostics.
- Added setup documentation for a new organization/project and clarified that
  the host-native proof is the primary boundary. Docker remains optional future
  package-install coverage because it cannot certify host harness, GUI, hook or
  scheduler behavior. No hooks, scheduler, model invocation or authentication
  are part of this slice.

**Verification:** `tests/e2e/fresh-consumer-smoke --output
.cache/r6-fresh-consumer.json --keep --live-cli` passed. The retained report
records a clean temporary consumer, APM audit success and projections for
`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, the installed
Copilot instruction and the Claude rule. Installed resources resolve inside the
isolated virtual environment and match the source guide/templates byte-for-byte.

The live no-auth checks started all three installed harnesses with both
`--version` and `--help`: Codex `0.144.4`, Claude Code `2.1.170`, and GitHub
Copilot CLI `1.0.83`. Copilot was installed from the official `@github/copilot`
package. The runner preserves the Node interpreter on its minimal PATH because
Copilot's executable is a Node launcher; this catches a real missing-runtime
failure while keeping credentials and model calls out of the gate.

The full root suite passed **875 tests in 9.45s**. Ruff lint, check-only
formatting, strict mypy over 35 source files and `git diff --check` passed.
The neutral package contract test and fresh-consumer audit passed independently.
The only APM warning was the expected unavailable organization policy repository;
policy enforcement is explicitly disabled for the local fixture install and
the audit still passed with no drift.

The fresh consumer is deliberately synthetic and disposable. It proves package,
projection, launcher and explicit-configuration wiring, not model routing,
authentication, hooks, automations, scheduler behavior, Docker parity or
tribe-scale retrieval quality. Those remain later proof stories (R8 and
selected future skill ports). No original organizational corpus, installed
harness configuration or signal inbox was changed. Knowledge lookup previewed
and read the APM package-synchronization and progressive-discovery rules before
the package/runner edits. Knowledge signals: none, because the runner fix and
its evidence are recorded in this plan without changing central organizational
knowledge.

#### R7 Setup and On-demand Compounding Checkpoint

R7 is implemented on `build/r7-setup-compound` from the accepted R6 base. It
delivers the first-run setup contract and the small coordination surface needed
by `knowledge-compound`; R8 remains responsible for authenticated native task
registration and run-now proof in each provider account.

**Delivered behavior:**

- Added pure `domain.compounding` decisions for current-user knowledge-PR
  eligibility/selection, explicit signal dispositions and publication-gated
  drain eligibility. The domain has no filesystem, Git, provider, clock or
  receipt side effects.
- Added an advisory JSONL activity log and guarded signal drainage. Starts
  retain selected complete-byte fingerprints plus workspace, harness, session
  and automation provenance. Malformed/interrupted activity, changed or
  replaced files, symlinks, outside paths and cleanup failures remain visible
  and retain inputs.
- Added CLI `compound status`, `compound start`, `compound drain` and
  `compound finish` requests with strict action-specific validation. The
  `knowledge-compound` skill documents context/catalog/search/validate use,
  current-user PR reuse, ordinary main merging, publication verification and
  safe disposition/drain behavior.
- Added the neutral `knowledge-setup` skill and three provider references. The
  skill asks only for the absolute configuration path and registered scope IDs;
  it derives or scaffolds the workspace identity, source/catalog defaults,
  producer root, signal inbox and virtual environment, ensures the signal and
  runtime paths are ignored, compiles all three APM targets and uses a daily
  local-time cadence. Publication remains opt-in. The
  standard-library setup helper creates/reuses Python 3.11 environments,
  installs the runtime, verifies `describe`/configured `doctor` and compiles
  all supported targets by default.
- Extended the fresh-consumer runner with setup repeatability, signal
  provenance and guarded start/drain/finish cleanup. Its optional `--live-cli`
  mode starts the installed Codex, Claude Code and Copilot CLIs with
  no-auth `--version` and `--help`; it does not create account tasks or invoke
  models.

**Verification:** the full root suite passed **913 tests**. Ruff lint and
check-only formatting, strict mypy, `uv build --out-dir .cache/dist` and
`git diff --check` passed. The fresh-consumer smoke passed with
`tests/e2e/fresh-consumer-smoke --live-cli`, including an isolated wheel/venv,
clean environment, APM install/compile for `codex,claude,copilot`, setup helper
venv reuse, signal provenance, guarded cleanup and missing-config diagnostics.
The live CLI checks reported Codex `0.144.4`, Claude Code `2.1.170` and GitHub
Copilot CLI `1.0.83`.

R7 proves the implementation and provider-neutral contracts without storing
credentials or mutating a user's harness. R8 will create/update disposable
authenticated native automations in Codex, Claude and Copilot, run each once,
verify activity/session/automation provenance and pause/remove controls, and
then complete the retrieval/consumption measurements. No original
organizational corpus, installed harness configuration or existing signal
inbox was changed. Knowledge lookup receipt `a1aa1062f516` previewed and read
the package-synchronization, documentation-owner and progressive-discovery
rules before the package/skill documentation edit. Knowledge signals: none,
because the R7 implementation and its verification are recorded here without
changing central or local organizational knowledge.

#### R8 End-to-end Harness Proof Checkpoint (complete)

R8 was implemented from the accepted R7 commit and is integrated on `main`.
This checkpoint records the deterministic retrieval/compounding proof and the
provider outcomes without claiming authenticated scheduled-agent success that
the current provider accounts could not supply.

**Delivered behavior:**

- Added six neutral acceptance cases covering feature-to-workflow discovery,
  operating-rule applicability (general, family and technology-specific),
  progressive large-runbook section reads, catalog validation and truthful
  empty/invalid searches.
- Added `tests/e2e/retrieval_measurement.py`, which reports returned preview
  bytes, selected body bytes/lines, source file size, elapsed time, misses and
  irrelevant reads. It does not infer token counts or semantic completeness.
- Added `tests/e2e/harness_agent_smoke.py`. It creates one disposable fresh
  consumer per provider, records a Markdown signal, exposes the installed
  `knowledge-compound` skill and explicit launcher/config paths, and supports a
  preparation run plus an opt-in provider one-shot run. It classifies
  authentication, usage-limit, availability, timeout and execution failures;
  it never mutates real harness state, canonical knowledge or a real PR.
- Tightened `knowledge-setup` so the normal interaction asks only for the
  absolute configuration path and registered applicable scope IDs. It derives
  or scaffolds the workspace identity, source/catalog paths, producer root,
  `ai/signals`, `<scaffold>/.agent-knowledge-venv`, all three APM targets and a
  daily local-time automation. Publication remains disabled unless explicitly
  enabled. The runtime helper now exercises the venv and target defaults when
  those flags are omitted.

**Verification:** the current root suite passes **965 tests**. Ruff lint,
check-only formatting, strict mypy, `uv build` and `git diff --check` pass. The
fresh-consumer smoke passes with the default setup-helper venv and target
arguments omitted; it verifies the derived scaffold-local venv,
`codex,claude,copilot` targets, isolated installation, compiled projections,
installed hook launcher, Copilot lock reconciliation, signal provenance and
guarded cleanup. The acceptance suite and retrieval report are recorded in
`.cache/r8-retrieval-measurement.json`.

The provider preparation report `.cache/r8-harness-ready-all.json` prepared
disposable consumers and one-shot commands for all three providers. That
earlier opt-in report retained its usage/auth blockers. Later 2026-09-21 runs
live-proved one-shot compounding and semantic retrieval across Codex, Claude and
Copilot, plus a real Codex desktop Scheduled compounding run with guarded
archive/drain provenance. Copilot `/every` and `/after` were confirmed as
session-scoped; the free-tier live registration attempt also failed model-based
schedule parsing. The reproducible one-shot driver still does not create
recurring tasks, run a repository scheduler or use Docker.

The installed-launcher correction also has a real Claude Code proof: Claude
Code `2.1.236` resolved `--model opus` to `claude-opus-5`, invoked the absolute
`agent-knowledge-hook` launcher in a fresh consumer, delivered startup and
resume reminders through `hookSpecificOutput.additionalContext`, and completed
with `START_OK`/`RESUME_OK`. Codex and Copilot remain covered by their native
payload fixtures; no common live automation API is claimed.

No original organizational corpus, installed harness configuration or signal
inbox was changed. Knowledge lookup for this checkpoint previewed and read the
package-surface, progressive-discovery, documentation-owner and Python quality
rules before the setup contract edit. Knowledge signals: none, because this
checkpoint records the new scaffold's implementation and provider blockers
without changing central organizational knowledge.

#### Post-review corrections (2026-09-12)

The user authorized the six findings from the core/hooks/session review. Drain
now accepts only valid Markdown signals in the current workspace's exact
project/shared buckets, with matching parsed IDs and origin metadata, before
applying the existing byte-fingerprint and file-identity protections. Public
CLI regressions preserve foreign-workspace signals and runtime activity files;
valid local and shared inputs still drain. The activity log remains advisory.

Fresh-consumer proof now reruns setup after APM reinstall, reuses the managed
CPython 3.11 environment, and checks both ownership records and the runtime
commands that providers execute. It requires the absolute consumer launcher,
preserves unrelated hooks, and verifies Copilot's supported lifecycle events.
The outer wheel-test environment is excluded from PATH; the fixture supplies
only a verified Python 3.11 prerequisite separately. Setup recovery instructions
now describe this rebind step.

The canonical reflection reminder explicitly permits no signal when there is
no useful observation. Compounding's initial inventory spans all authoring
sessions in the selected project/shared buckets. The installed signal template,
`describe` contract, guide and CLI examples now agree on conditional harness
session provenance and exact-session authoring discovery. The reusable Claude
acceptance scenario is recorded in the
[session/reflection plan](signal-reflection-and-session-provenance.md).

Verification: **1,010 tests passed**, strict mypy passed for all 43 source
files, APM compilation validated 16 primitives, and skill validation passed
for 33 skills. The isolated wheel/install and three-provider fresh-consumer
reinstall/rebind proof passed; retained local evidence is
`.cache/review-fixes-fresh-consumer.json`. Final Ruff lint/check-only formatting
passed. Live Claude Opus 5 also passed the session-propagation,
record/list/read/duplicate-decision and failing-hook scenario, recorded in
`.cache/review-fixes-claude.json`. Synthetic fixtures and installed
package surfaces were updated together. Populated-corpus retrieval quality
and authenticated recurring automation execution are outside this fix pass;
no organization corpus or real signal inbox was changed.

#### Follow-up plan moved: final pass (2026-09-14)

The current B1-B5 changes now live in
[Knowledge Scaffold Final Pass](knowledge-final-pass.md). That is the working
plan for taxonomy changes, assisted business onboarding, incoming links,
reflection/compounding and instruction ownership, business decision history,
and tool-written receipts with signal archives and usage exports.

Use the standalone plan for further decisions, implementation status and proof.
The contracts were extracted without dropping their accepted examples, tests
or constraints; they are not duplicated here. This document retains the
original core architecture and implementation history.
