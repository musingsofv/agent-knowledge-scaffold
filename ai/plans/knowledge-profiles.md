# Named Knowledge Profiles

**Date:** 2026-09-15
**Status:** P1-P4 implemented and verified.
**Repo Scope:** agent-knowledge-scaffold
**Primary PR Repo:** agent-knowledge-scaffold
**Working plan:** This file owns the named-profile follow-up. Earlier core,
hook and final-pass plans retain their existing implementation and proof history.

## Table Of Contents

1. [Plan Brief](#1-plan-brief)
   - [Outcome](#11-outcome)
   - [Feature Shape](#12-feature-shape)
   - [Capabilities Delivered](#13-capabilities-delivered)
2. [Build Contract](#2-build-contract)
   - [Delivery Slices](#21-delivery-slices)
   - [Implementation](#22-implementation)
   - [Deployment](#23-deployment)
3. [Appendix](#3-appendix)
   - [Context Used](#31-context-used)
   - [Additional Notes](#32-additional-notes)

## 1. Plan Brief

### 1.1 Outcome

A developer can use a named knowledge profile, such as `personal`, `example-project`
or `work`, with a configurable default, validated overrides and an optional
external credential-environment declaration. Concurrent agent sessions keep
their own knowledge selections. A credential environment is activated once at
the harness-session boundary and never switched by an ordinary CLI selection.

### 1.2 Feature Shape

#### Today

The installed CLI requires an explicit workspace YAML path for configured
operations. `describe` is installation discovery and works without a workspace.
Each workspace declares its identity, sources, registered scopes, signal storage,
usage policy and optional setup preferences. The CLI does not select an
organization from the current directory or shell variables.

The APM package supplies neutral discovery/reflection instructions and hooks.
Hooks expose the provider session ID but do not select a workspace. Agents can
follow a session-specific instruction naming an absolute configuration path;
there is no persisted session-to-workspace binding or global active-workspace
switch. Setup currently verifies one explicitly supplied workspace and records
absolute runtime/configuration paths in native automation prompts.

Several application operations, freshness checks and receipt writers reload a
workspace from its path. Adding profile flags only at argument parsing would
lose overrides in those downstream reads and could record evidence for a
different configuration from the one used by the operation.

#### Planned Delta

Add one user-owned YAML profile registry. Each named profile points to one
ordinary `knowledge-workspace.v1` file and may override documented workspace
settings. An optional `default_profile` serves invocations without a selector.
An explicit profile or direct workspace path takes precedence over that default.
The CLI exposes profile discovery and explains the effective configuration.

An agent instructed to use `work` passes `--profile work` on every configured
operation. On first using the default, it reads `context` and thereafter passes
the returned profile explicitly. Project instructions can recommend a profile;
the runtime does not infer one from a directory. Session selection does not
rewrite the registry. A user changing the default affects subsequent unqualified
calls, not calls already carrying an explicit profile.

Resolution produces one immutable effective workspace and selection provenance
per invocation. All operations, signals, receipts and freshness checks use that
same selection. Setup and the installed guide teach the workflow; hooks remain
generic and advisory. This change adds convenient names and overrides, not a
workspace-selection session database or a security boundary between files
accessible to the harness. Claude credential activation has one narrow,
value-free provider cache described below so resume and compaction cannot adopt
a different declaration.

#### Must Preserve

- The agent chooses queries and body reads; retrieval semantics and taxonomy do
  not change.
- Direct `--config` remains a supported first-class selector, not a compatibility
  shim. It does not consult user profile settings.
- Profile names do not establish scope membership or replace workspace IDs.
  Personal/work separation requires deliberately separate sources and storage.
- Domain parsing, selection and merge rules stay pure, immutable and testable
  without filesystem, environment, clock, Git or harness access.
- Signals retain exact provider session provenance; the CLI still owns receipts,
  input archives and guarded drainage.
- One compounding automation owner per signal store; aliases do not create new
  owners or bypass coordination.
- Hooks do not read registries, resolve profiles, search knowledge, or write
  signals. They keep their existing supported events and non-blocking behavior.
- One source-owned instruction/guide contract; no duplicate procedures in
  generated `AGENTS.md`, `CLAUDE.md` or hook output.
- This is a fresh implementation. No old configuration migrations, deprecated
  aliases, organization-specific environment fallbacks or inherited corpus ports.

### 1.3 Capabilities Delivered

| Status | ID | Capability | Expected Behavior | Important Conditions | Proof Signal |
| --- | --- | --- | --- | --- | --- |
| - [x] | C1 | Discover and select profiles | List configured names; select an explicit name or the declared default; retain direct paths | Unknown/missing selections fail; explicit paths bypass the registry | Domain and CLI selection matrix |
| - [x] | C2 | Apply explainable overrides | Merge supported fields and resolve paths from their authoring files; validate the result | Identity is fixed; lists replace; invalid base files cannot be repaired silently by an overlay | Pure merge tests and filesystem provenance fixtures |
| - [x] | C3 | Use one configuration throughout an operation | All configured CLI commands honor the same effective workspace | No downstream reload of only the base path; no temporary merged config files | CLI tests across retrieval, signals, compounding and usage |
| - [x] | C4 | Diagnose and audit the selection | Context/doctor show effective values and override origins; tool evidence records profile and configuration | Unresolved selection does not emit a receipt into another profile's storage | Receipt, descriptor and diagnostic assertions |
| - [x] | C5 | Preserve session and run boundaries | Concurrent explicit selections do not interfere; in-flight compound runs reject changes to routing/storage | Ordinary knowledge/catalog changes remain possible; aliases share existing store coordination | Multi-process CLI fixtures and compound-run mismatch tests |
| - [x] | C6 | Set up and use profiles from a harness | Setup registers a chosen label, respects defaults, binds runtime checks and automation prompts to the selected profile | No shell startup edits, default changes without direction, duplicate hook registrations or duplicate automation owners | Repeat-setup fixtures and isolated installed-consumer proof |
| - [x] | C7 | Follow a documented session workflow | Agent can discover profiles, honor a project default or session override, and retain selection during reflection | Same generic hooks; explicit disclosure that selection is agent-followed rather than persisted by session ID | Installed-guide checks and live Claude acceptance |
| - [x] | C8 | Declare and diagnose profile environments safely | A profile may name one external dotenv file and explicit source-to-target mappings; context and doctor expose metadata/readiness without values | Strict data parsing, private regular file, no interpolation/evaluation, no receipt or fingerprint coupling | Domain, adapter, CLI and leakage tests |
| - [x] | C9 | Activate one credential profile per harness session | Setup produces a value-free provider launcher and provider-specific activation guidance; Claude uses its native session environment channel | Knowledge `--profile` never mutates an active environment; new profile means a new session; desktop limits remain explicit | Setup/provider fixtures, installed proof and live Claude proof |

## 2. Build Contract

### 2.1 Delivery Slices

Implement sequentially with repository-native checks. The user requested this
implementation of the full plan, with real-harness tests only after all slices
are built. Publication and host-wide setup are not part of this change. Each slice must leave the repository green. If stacked
branches are used, merge in this order; do not import a build orchestrator.

| Slice | Capabilities Covered | Repo(s) | Base / Stack Parent | Existing Surface / Likely Touchpoints | Notes |
| --- | --- | --- | --- | --- | --- |
| P1 | Internal model/resolution portions of C1-C2 | agent-knowledge-scaffold | Latest main | `domain/configuration.py`, a focused `domain/profiles.py`, `infrastructure/configuration.py`, profile file adapter; mirrored tests | Pure selection/override rules, path provenance and effective snapshot. No public profile flags until every operation can honor them. C1-C2 remain unchecked. |
| P2 | C1-C5 | agent-knowledge-scaffold | P1 | CLI main/contracts, application operations/doctor/invocation, configuration freshness checks, receipts/descriptors, compound evidence; CLI guide/examples and tests | Wire every command together; add discovery, diagnostics and run checks in the same slice as public selection. |
| P3 | C6-C7; installed proof of C1-C5 | agent-knowledge-scaffold | P2 | Setup/compound skills and helper, source discovery instruction, shared reminder/guide, setup docs and `tests/e2e/` | Make onboarding and session selection repeatable. Run real-harness tests after all slices; native scheduler testing remains paused. |
| P4 | C8-C9 | agent-knowledge-scaffold | Latest main after P1-P3 | `domain/profiles.py`, a focused environment adapter, context/doctor/contracts, setup provider bindings, source instructions/docs and mirrored tests | Add only secret-free metadata and session activation. No per-command wrapper, shell-startup edit, provider-global secret copy or backwards compatibility. Run real-harness proof after the complete slice. |

### 2.2 Implementation

#### Data Model

The registry is user configuration, separate from the knowledge corpus and
workspace catalogs. The proposed format is:

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
  example-project:
    config: /work/example-project/knowledge-workspace.yaml
  work:
    config: /work/company/knowledge-workspace.yaml
    overrides:
      receipts:
        retention_days: 60
```

- Required root fields: `schema_version`, `profiles`. Optional:
  `default_profile`. An empty registry with no default is valid for onboarding.
- Profile keys are exact lowercase slugs matching `[a-z][a-z0-9-]{0,63}`.
  `example-project` is the usable name for the label "Example Project"; no alias expansion,
  case folding, fuzzy lookup or implicit normalization at runtime.
- Each profile requires `config` and optionally `overrides`. Reject unknown
  fields. A configured default must name an existing profile.
- Reuse the existing strict YAML loader and its byte/depth/node limits,
  duplicate-key rejection, bounded aliases and prohibition of YAML merges and
  constructors. Do not introduce a second YAML library or interpolation language.
- Profile names can point to the same workspace. They are local selectors, not
  new workspace identities or new knowledge sources.
- `environment` is optional profile metadata, not a workspace override. It
  requires one literal local `file` and a nonempty `variables` mapping. Variable
  labels use the same lowercase-slug rule as profiles. Each mapping requires
  `from_env`, `expose_as` and a bounded nonblank `description`; environment
  names use exact POSIX identifier syntax and source/target names are unique.
  Tool-facing targets cannot use shell-control names or the setup-owned `_ak_`
  namespace. The complete value-free Claude declaration must fit its 16 KiB
  session-pin bound during schema and setup validation.
- The registry stores only the path, names, mapping and description. Inline
  values, defaults, secret references with embedded values and unknown fields
  are rejected. A relative file path resolves from the registry directory.
- Resolved environment metadata travels separately from `WorkspaceDefinition`.
  It does not change workspace or continuation fingerprints, receipts, usage
  descriptors, compounding evidence/routes, signal schemas or publication.

Represent the authored profile, selection and effective workspace with typed
immutable values. Preserve the resolved registry path, selected name, base
workspace path and field origins alongside the effective definition. Do not
write a flattened workspace file or persist an active selection.

#### API Contract

Add global `--profile NAME` and `--settings PATH` options to `agent-knowledge`.
`--settings` locates the registry; it never names a workspace. Like existing
global options, these precede the command.

| Invocation | Resolution |
| --- | --- |
| `--config PATH <operation>` | Load that workspace directly; do not read a registry or apply profile overrides |
| `--profile NAME <operation>` | Load NAME from the standard registry |
| `--settings PATH --profile NAME <operation>` | Load NAME from that explicit registry |
| `<operation>` with no selector | Use the standard registry's `default_profile` |
| `--settings PATH <operation>` | Use that registry's `default_profile` |
| `profiles list` | List registry metadata without loading workspace files or catalogs |
| `describe` | Describe the installed contract, including profile schemas, without loading user configuration |

`--config` cannot accompany `--profile` or `--settings`. `profiles list` accepts
`--settings` and output formatting, but not `--profile` or `--config`. Keep
`describe` configuration-independent; selection flags on it are an argument
error with guidance to use `context` or `doctor` instead. No `profiles use`,
global activation command or per-call arbitrary `--set` facility is added.

`profiles list` returns the resolved registry path, optional default and a
stable name-sorted list of names, resolved base configuration paths, default
markers, overridden field paths and declared environment metadata. It does not
open env files or require every workspace to be mounted/readable.
`--profile NAME doctor` is the selected profile readiness check. `context`
returns the selected environment path, labels, source/target names,
descriptions, availability booleans and the one-profile-per-session policy;
direct `--config` returns `environment: null`. Neither command returns values.

All configured operations are covered: `doctor`, `context`, `catalog`, `search`,
`inspect` (including incoming links), `validate`, `signal list`, `signal record`,
`compound` and `usage export`. Existing request schemas and request-file path
bases stay unchanged. Signal input files remain relative to the base workspace
configuration where that is the current command contract, not to the registry.

Examples after implementation:

```bash
# Discover configured names without opening knowledge files.
agent-knowledge profiles list

# Inspect the default once; use the returned name explicitly afterward.
agent-knowledge context
agent-knowledge --profile personal doctor

# A separate work session uses its own explicit selector.
agent-knowledge --profile work context
agent-knowledge --profile work search --request-file - <<'YAML'
kind: [guidance, runbook]
text:
  any: ["secondary index", "index rollout"]
YAML

# Reflection uses the same selected profile and the actual hook session ID.
agent-knowledge --profile personal signal list --request-file - <<'YAML'
include_shared: true
session_id: "opaque-id-copied-from-the-provider-hook"
limit: 50
YAML

# Deterministic harness/automation use includes the absolute registry location.
agent-knowledge --settings /work/local/knowledge-profiles.yaml --profile work \
  compound --request-file - <<'YAML'
action: status
YAML

# Direct paths remain valid and bypass all profile settings.
agent-knowledge --config /work/personal/knowledge-workspace.yaml context
```

Schema descriptions in `describe`, installed documentation and executable
fictional examples must agree. Do not claim these commands exist before P2.

#### Business Rules

**Selection and defaults.** Look only at an explicitly supplied registry or
the one documented standard location. Do not scan parent directories, combine
multiple registries, infer profiles from repository names or consult an
organization environment variable. A missing registry/default, unknown name,
invalid YAML or inaccessible selected workspace produces an explicit diagnostic;
never fall back to another profile. A valid explicit `--config` works even when
the registry is missing or malformed. Explicit profile selection needs no
default but still requires a structurally valid registry. Profile listing
validates registry structure; it does not open unselected workspace files.

**Override surface.** Support these existing workspace fields only:

| Field | Override behavior |
| --- | --- |
| `applicable_scopes` | Replace the entire list; verify every ID against effective source catalogs |
| `sources` | Replace the entire list of complete source records, including any publication blocks |
| `signal_storage` | Merge specified `scaffold_root` / `code_root` fields |
| `receipts` | Merge specified `enabled`, `directory` / `retention_days` fields |
| `setup` | Merge specified `venv`, `harnesses` / `automation`; `harnesses` replaces the list and automation merges its known fields |

`schema_version` and `workspace_id` cannot be overridden. To create a different
workspace identity, author a different workspace file. Reject null values and
unknown fields; there is no deletion sentinel. Optional publication settings
can be removed by replacing `sources` with complete records omitting publication.
`receipts.enabled: false` still leaves mandatory compounding evidence enabled.
Preferences such as cadence are configuration, not instructions to register or
reschedule tasks during ordinary CLI calls.

Parse the base workspace independently before applying overrides. Then validate
the effective workspace and its selected catalogs/paths using existing domain
and adapter checks. An override can deliberately replace an unavailable source;
only effective source catalogs require filesystem access. It cannot disguise a
schema-invalid base workspace. Empty collections retain each field's existing
rules, including at least one source and permission for an empty scope list.

**Merge and path rules.** Scalars replace, known mapping fields merge, lists
replace completely. There is one overlay only. Paths authored in the base
workspace, including its implicit defaults, resolve from that workspace's
directory. Paths authored in the profile, including `config`, resolve from the
registry's directory. Track this provenance while merging; moving a field into
an overlay must not accidentally rebase an inherited sibling path. Existing
literal local path rules apply: no shell expansion, URLs or environment
interpolation inside YAML. Home resolution for finding the standard registry
does not add `~` expansion to authored paths.

**One effective invocation.** Resolve once at the CLI boundary and pass the
effective workspace to application operations. Replace base-path-only reloads
with a shared freshness check that re-resolves the same selected profile/path.
After resolving a default, pin that name for the rest of this invocation;
freshness checks must not reselect a newly edited default. Doctor must retain
its staged diagnostics for partially configured workspaces instead of failing
before it can explain which stage is broken.

Bind continuations to the effective workspace, resolved paths and selected
catalog content. Record the selection separately: switching from an implicit
default to that same explicit name must not invalidate a page. Editing an
unselected profile or the default name must not invalidate an explicitly
selected profile's unchanged effective snapshot. Relevant source/scope/catalog
changes do invalidate existing continuations. Missing or changed selected input
during a mandatory evidence/write check fails safely; there is no reload using
only the base file. Reuse existing checks for corpus mutation and incomplete
scans rather than inventing a second consistency system.

**Diagnostics and receipts.** All configured responses include a compact
`selection` summary: mode (`config`, `profile` or `default`), nullable profile
name, nullable settings path, base config path and effective fingerprint.
Context/doctor additionally expose effective configuration and overridden field
origins. Keep existing `config_path` meaning the base workspace path.

Extend tool-written retrieval/compound events and usage descriptors with this
selection and effective configuration evidence. Descriptors must include the
settings that determine sources, applicability, signal/evidence storage and
publication, plus field origins; base-file contents alone are insufficient.
Capture only the selected profile, never unrelated profiles or arbitrary file
contents. If resolution fails, report the attempted selection in the response
but do not choose another destination for receipts. Optional diagnostic failures
remain non-blocking; mandatory archive/drain evidence remains required. Usage
export must retain the new fields and source descriptors.

**Environment inspection.** Treat the external file as strict dotenv data,
never as shell source. Accept blank/comment lines, optional `export ` and exact
`NAME=value` assignments; reject invalid UTF-8, NUL, malformed or duplicate
assignments and files over the documented bound. Open a regular file through a
no-follow path, require current-user ownership and no group/world permissions,
and report only paths, labels, names and availability. Missing configured keys
make environment readiness fail without changing independent knowledge-read,
signal-write or receipt readiness. Secret bytes are transient and must never
enter exceptions, activation-command stdout/stderr, logs, hooks, generated setup
reports, receipts or exported evidence. Provider processes receive mapped values
through the provider-specific session or tool environment and remain able to use
those credentials.

**Credential session boundary.** One harness session activates at most one
credential profile. A later `agent-knowledge --profile other` changes knowledge
routing for that invocation only; it does not and cannot mutate credentials
already loaded into the parent harness. Rerun setup for the intended profile and
start a new session to activate it. Scheduled tasks pin one profile. Token rotation within the
same external file may be observed when a provider starts, while mapping/profile
changes apply only to a new session. This is routing convenience, not an access
control boundary; provider keychains and credential helpers remain provider
owned.

Claude is the only provider that persists a credential-session binding. Its
hook writes one value-free declaration pin per opaque session ID beneath
`~/.cache/agent-knowledge/claude-environments/<consumer-hash>/`. A pin contains
only the external file path and source/target names, is current-user-owned and
private, and never contains values or workspace knowledge selection. It is
created on first `SessionStart` and reused on resume/compaction so later setup
cannot retarget an existing session. Pins intentionally have no automatic expiry
because Claude sessions may be resumed later; removing that cache directory is
the explicit reset/cleanup operation and causes the next start/resume to bind the
then-configured declaration.

**Compounding continuity.** Record a run's resolved configuration route at start:
base workspace path/ID, scopes, source IDs/roots/catalog paths/publication,
signal storage and evidence directory. Before later run-associated mutation or
validation, verify that route still matches. Reject a mismatch and retain inputs;
do not quietly adopt a new publication repository, source set or archive path.
Normal document edits and catalog vocabulary maintenance are expected during
compounding: compare routing/configuration fields, not catalog contents, for
this run check. The general discovery snapshot still reflects catalog changes.
Equivalent aliases can reach the same run if the effective route agrees.
Activity locks remain keyed to the existing signal store, not to profile names.
Diagnostic retention/output preference changes alone do not create a new route.

**Failure behavior.** Preserve the existing exit categories: invalid selectors,
schema, missing default/name and invalid overrides use exit 2; filesystem and
incomplete external-state failures retain the existing adapter classifications.
Profile discovery/configuration does not create missing sources, delete signals,
fix invalid YAML, contact a provider or authenticate to GitHub. Interrupted setup
leaves existing configuration intact and reports incomplete installation stages.

#### Config

The standard registry path is `~/.config/agent-knowledge/config.yaml`, located
through the current process user's home directory. `--settings PATH` overrides
that location entirely; a relative command-line path resolves from process cwd.
Use an absolute override for scheduled jobs, isolated tests or a harness with a
different home. This standard location is a new explicit user-config convention,
not an inferred knowledge root. Do not add shell startup exports, project config
crawling, profile inheritance or an XDG/environment precedence chain in this slice.

Setup may create or edit the registry when the developer invokes setup. Preserve
existing entries/defaults and show the proposed changes. Suggest a label from
the supplied business/project name; when there is no meaningful name, ask once.
For the first profile, propose making it the default in the same confirmation as
the workspace choices. Adding later profiles does not silently change the
default. Reusing an unchanged mapping is idempotent; an existing name pointing
elsewhere requires a deliberate choice to replace it or use another name.
Use an atomic same-directory write and check that the file has not changed
since inspection before replacement; preserve unrelated entries and comments.
Do not introduce a YAML round-trip dependency just to preserve formatting.

The runtime setup helper can retain explicit base-workspace/venv bootstrap
arguments before the CLI is installed. Extend its installed verification phase
to accept the chosen registry/name, verify that it resolves to the bootstrap
workspace, and use its effective settings for readiness checks. Keep profile
merge/validation in the installed core; do not duplicate it in the standalone
setup script. Explicit bootstrap paths let the agent install the runtime before
asking the installed tool to validate any profile-selected runtime preferences.
Reconcile the chosen venv with effective `setup.venv` before binding hooks; report
a mismatch rather than installing a second environment silently.

Native automation prompts name the absolute CLI launcher, absolute registry path
and explicit profile; direct-path setups remain supported. They must not depend
on the global default. Preserve one owner per physical signal store and the
existing workspace marker; two aliases must not register duplicate jobs.
If two mappings would operate the same store with incompatible routes, setup
reports the conflict instead of creating a competing automation. Profile edits
affect future explicit calls; changes to native task cadence/launcher or provider
registration require setup to update that task, not an invisible runtime action.

Teach the installed guide, setup and compound skills this session procedure:

1. Use the profile supplied by the user; otherwise follow an explicit project
   instruction, or discover the declared default through `context`.
2. Confirm the resolved profile/workspace using `context` and readiness using
   `doctor`; do not read every profile's knowledge.
3. Pass the selected `--profile` (and `--settings` if nonstandard) on every
   retrieval, signal and compounding call. Copy the exact hook session ID as
   before. A user-requested change affects subsequent calls, not previous signals.
4. Do not rewrite `default_profile` to implement a session override. After resume
   or compaction, recover the explicit selection from retained instructions; if
   it is unavailable, ask rather than silently adopting a potentially different
   global default for a resumed session.

Document the project instruction as a suggested default that an explicit user
session choice can override. The hook can briefly refer to the selected profile
and shared guide, but must not inspect the registry or persist the selection.
No profile-specific hook installations, new events or scheduler work are needed.
Existing unrelated global harness instructions are not disabled by this selector.

P4 setup creates one immutable, value-free provider launcher for the selected
registry, profile, env-file path and mappings under the managed virtual
environment. The launcher delegates parsing to the installed guarded adapter,
then replaces itself with Codex or supervises Copilot while passing only the
minimum provider environment. It never prints shell exports or
credential values. Its content-addressed path prevents setup for another profile
from retargeting an already-started CLI session. Setup validates the selected
environment with `doctor` before binding or reporting activation and never edits
shell startup files or `launchctl`.

Provider behavior is explicit:

- Claude local CLI/Desktop: only the selected `SessionStart` hook reads the
  external file through the guarded parser and appends shell-quoted declared
  exports to Claude's private provider-owned `CLAUDE_ENV_FILE`, as required by
  Claude's native contract. The hook output, prompt and setup evidence contain
  no values. A private value-free session pin preserves the first declaration
  across resume/compaction even when setup later selects another profile. Pins
  live under `~/.cache/agent-knowledge/claude-environments/<consumer-hash>/`
  until explicitly removed; they contain paths and mappings only.
  Prompt hooks remain reminder-only and the hook reads no registry.
- Copilot CLI: setup reports the generated one-session launcher without
  provider flags. The adapter injects setup-owned `--secret-env-vars` and
  `--bash-env=on`, rejects caller overrides, and gives Copilot protected
  internal aliases for native output redaction while leaving existing parent
  values under declared targets, including provider-auth names such as
  `GH_TOKEN`, unchanged. A private mode-`0600` `BASH_ENV` file restores the declared
  targets in each Bash tool and unsets `BASH_ENV` there. The wrapper removes
  that file on ordinary exit; abrupt termination can leave it for operating-system
  temporary-file cleanup. Copilot persists its global Bash-support preference,
  which contains no profile path or value. Its lifecycle hook remains
  reminder-only because a child hook cannot mutate the parent agent process.
- Codex CLI: setup reports a one-session launcher that replaces itself with
  `codex` after loading the selected mapping. Codex app and Copilot app expose no documented
  generic per-task env-file injection, so setup reports that limitation and the
  agent uses profile metadata plus provider-native stores or explicit
  credentialed-command sourcing. It must not claim isolation it cannot provide.
- Scheduled work pins the profile and uses the provider's native environment or
  secret surface where available. A Claude task prompt pins knowledge only; one
  local consumer hook binds one credential profile for all new sessions. Use a
  separate consumer/project configuration or provider-native cloud environment
  for concurrent Claude tasks requiring different profiles. P4 does not create
  or retest native schedules.

Setup owns this provider matrix. The developer supplies the profile label,
external file and intended mappings once; the setup skill detects installed
harnesses, applies automatic bindings and presents only the complete generated
command when a new CLI process is required. It never asks the developer to
choose an injection mechanism, reproduce flags or edit generated hook files.
Across providers the user-facing switching workflow is: rerun setup for the
intended credential profile, then start a new session. Starting a new Claude
session without setup rebinding retains the last consumer binding.

Discovery/reflection hook decisions, retrieval and compounding remain
authoritative in their existing owners. Environment activation is a setup-owned
provider adapter; it does not plan searches, read knowledge or judge signals.

#### Automated Tests

Use existing pytest fixtures and strict YAML/parser patterns. Pure semantics
must run in memory; filesystem and subprocess behavior belongs in integration
or E2E tests. Tests prove selection and isolation, not simply dataclass shapes.

| Capability | Test Level | Existing Test Pattern / File | What The Test Proves |
| --- | --- | --- | --- |
| C1-C2 | Unit | `tests/unit/domain/test_configuration.py`; new matching profile tests | Exact names, duplicate/unknown fields, defaults, immutable identity, typed overrides, map merge/list replacement, invalid base, empty scopes/sources, no input mutation |
| C1-C2 | Integration | `tests/integration/infrastructure/test_configuration.py` | Standard vs explicit registry, selected-only workspace IO, relative origins across separate directories, inherited defaults, overlap checks, unavailable replaced sources and malformed files |
| C1-C3 | CLI integration | `tests/integration/entrypoints/cli/test_main.py` | Complete selector matrix and all configured operations; direct config bypasses even a malformed registry; describe works without configuration; list works with offline workspace paths |
| C3-C4 | Integration | `tests/integration/entrypoints/cli/test_usage_receipts.py`; infrastructure usage tests | Query and receipt use the same effective values, new descriptor fields survive export, failed resolution never writes into another inbox/store, optional receipt failures keep existing behavior |
| C3-C5 | Integration | Retrieval/incoming pagination and signal tests | Change registry/default/catalog between pages and during write checks; relevant changes fail, unrelated changes do not; no silent fallback to base settings |
| C4-C5 | Integration | `tests/integration/infrastructure/test_compounding.py`, `test_compound_evidence.py` | Profile-selected start/validate/drain/finish, required archives, changed route rejected, ordinary catalog maintenance permitted, aliases cannot bypass active-store coordination |
| C5 | Multi-process integration | Existing subprocess CLI fixtures | Interleave personal/work calls with separate sources/inboxes/usage; each can use the same exact session-id string without cross-store matches; no registry writes; explicit profiles survive a changed default |
| C6 | Setup integration | Existing setup-runtime and instruction ownership fixtures | First registration, repeated registration, name conflicts, concurrent registry edit, partial runtime, profile overrides in installed doctor, selected venv, one hook entry/automation owner per intended store |
| C6-C7 | Installed E2E | `tests/e2e/fresh_consumer_smoke.py`, provider-hook fixtures | Wheel/sdist contain new modules/schema/guide; explicit temporary HOME and registry; actual installed launcher honors profiles; existing Codex/Claude/Copilot payload/session contracts remain intact |
| C7 | Live harness at end | Extend existing Claude acceptance under `tests/e2e/` | Two isolated fresh Claude sessions use different names, retrieve distinct seeded knowledge and record/list only their own profile's session signals through existing reminders |
| C8 | Unit/integration | Profile domain tests plus a focused environment adapter suite | Closed schema; exact names; strict dotenv grammar; private/no-follow file access; registry-relative resolution; no value survives inspection |
| C8 | CLI/leak regression | Profile/context/doctor/receipt/usage tests with unique sentinels | Safe list/context/doctor metadata; direct-config null behavior; missing/malformed/key failures; sentinels absent from every serialized or persisted surface |
| C9 | Setup/provider integration | `tests/integration/apm/test_setup_runtime.py` and hook runtime tests | Value-free content-addressed launchers; exact provider/event commands; unrelated hooks preserved; profile switch requires a new session; capability report is honest |
| C9 | Installed/live proof | Fresh-consumer profile scenario and live Claude at the end | Separate profile launchers expose only their mapped target in new sessions; Claude native hook works; Codex/Copilot unsupported app behavior remains capability-gated rather than simulated |

Also cover bounded/invalid UTF-8 YAML, permissions/read errors, missing source
catalogs, unknown effective scopes, unsupported/null override values, malformed
requests after successful selection, profile deletion between invocations,
missing default after restart, alias-equivalent configurations, and provider
unavailability. Every failure must retain inputs and avoid a substitute profile.
No network service, database, daemon or provider credentials are required for
the deterministic tests. Native scheduling tests remain paused; automation
prompt/selection assertions are separate from proving a provider scheduled run.

Run targeted tests during each slice, then the repository gates:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run mypy
uv build
```

After P3, run installed-consumer/APM checks documented in `docs/r8-harness-proof.md`
and the profile-specific live Claude scenario. Codex/Copilot get deterministic
provider and installed-launcher checks; report live-model proof only when actually
run and available. Do not convert fixture evidence into a claim of native
scheduler or real-model success. No fixed test-count target replaces these
behavioral checks.

After P4, repeat the installed consumer check with two disposable external env
files and distinct canary values. Scan command output, setup JSON, generated
hook files/launchers, receipts and usage exports for both canaries. The one narrow
exception is Claude's private provider-owned environment file, which must hold
the declared export for Claude to activate it and is removed after the proof. Include a
positive child-process control proving each selected launcher gives its provider
only the declared target. Run the live Claude test only after all deterministic gates;
Codex/Copilot app behavior is documented/capability-tested unless a supported
native activation surface is available. Native scheduler proof remains paused.

### 2.3 Deployment

This is a CLI/library/APM package change in one repository. P1 adds internal
resolution, P2 exposes the complete runtime contract, and P3 updates the consumer
workflow. P4 adds profile environment metadata and setup-owned provider
activation. Rebuild the distribution and reinstall the consumer runtime/package
to use profiles. Users can retain direct configuration paths without creating a
registry. There is no corpus migration, taxonomy backfill or change to existing
signal body schemas.

Synchronize `README.md`, `docs/agent-contract.md`, `docs/fresh-consumer.md`, CLI
examples, `describe`, setup/compound references and source-owned discovery
instructions. Update the repository's explicit-config instruction to describe
the new selector contract, then regenerate its harness projections through APM.
Retain the earlier plans as completed history; this file owns the new contract.

Plan creation does not change the user's real registry, shell, hooks, installed
packages or scheduled tasks. Implementation tests must use temporary homes and
fictional personal/work fixtures. Existing native automations remain untouched
unless the developer subsequently invokes setup for them. No push/release or
native scheduler retest is part of this planning request.

## 3. Appendix

### 3.1 Context Used

- User accepted named profiles, one optional default, explicit per-session
  selection, profile overrides, predictable path/list semantics and generic hooks.
- `.apm/instructions/scaffold-local.instructions.md`: neutral ownership, pure
  domain, mirrored tests, no old compatibility paths, and paused scheduler proof.
- `ai/plans/organization-neutral-knowledge-core.md` and
  `ai/plans/knowledge-final-pass.md`: architecture and completed feature ownership;
  no reopening of the earlier slices.
- `docs/agent-contract.md` and `docs/fresh-consumer.md`: explicit selection,
  installed resources, signals and native setup boundaries to update.
- `src/agent_knowledge/domain/configuration.py` and
  `infrastructure/configuration.py`: current workspace fields, path validation,
  catalog loading, storage overlap checks and fingerprints.
- `src/agent_knowledge/entrypoints/cli/main.py`, application operations and
  `infrastructure/receipts.py`: repeated workspace loads and evidence freshness
  checks that must use the effective selection.
- `src/agent_knowledge/infrastructure/compounding.py` and
  `compound_evidence.py`: store coordination, start evidence and guarded drainage.
- Package setup/compound skills, setup runtime helper and source discovery
  instruction: bootstrap/runtime split and single instruction owner.
- `src/agent_knowledge/resources/hook_messages.py` and provider entrypoints:
  neutral reminder/session provenance boundary.

Planning is grounded in this repository's own source and neutral contracts.
Inherited workflow defaults requiring an external organizational corpus do not
apply under the local instructions. The user-approved profile feature deliberately
extends the current explicit-path-only selection rule; it does not introduce
ambient organization inference. Python dataclasses, argparse and the existing
strict YAML loader are sufficient; no new framework or dependency is proposed.

### 3.2 Additional Notes

The important limitation is visible in the user workflow: saying "use work for
this session" instructs the agent to pass `--profile work`. The CLI does not
persist a binding to the provider session ID or prevent the agent from making
an explicitly different selection later. Defaults therefore provide convenience,
not enforced session isolation. Separate project instructions and explicit
selectors are the supported mechanism in this change. The Claude credential
pin is a deliberate exception for environment activation only; it does not pin
knowledge selection.

Credential activation is stricter than knowledge selection: a running harness
keeps the environment it started with. Selecting another knowledge profile in
that session never switches, clears or merges credentials. Rerun setup and start
a new session for another credential profile. The generated launcher reduces accidental mixing
but does not override provider keychains, desktop account state or other ambient
credential helpers, so profiles remain a convenience boundary rather than a
security sandbox.

Profile-only overrides are local policy. If an agent proposes an update to the
base workspace or catalog while compounding, it must consider the reported field
origins: a local override is not evidence for changing shared workspace settings.
This selector layer does not modify unrelated global instructions or skills.

## Implementation and verification record

P1-P4 were implemented after approval, with real-model acceptance reserved until
the complete profile-environment feature was built.

- P1: `domain/profiles.py` owns strict names, selection and immutable overlays.
  `infrastructure/profiles.py` resolves one registry, records authoring origins
  and supports checked registry publication. Base schema validation precedes
  overlay application; unavailable replaced sources do not require access.
- P2: CLI operations receive one effective `Workspace`. Context/doctor explain
  selection and origins. Freshness retains the selected name; compounding checks
  routing independently of normal catalog maintenance. Receipts and descriptors
  retain selection and effective configuration. Usage export follows and verifies
  each receipt's descriptor reference, including different profile descriptors
  with the same effective workspace fingerprint.
- P3: setup registers reviewed YAML bytes through the installed core, verifies
  profile/base/venv agreement before hook binding and retains one automation
  owner per physical store. The shared guide owns session selection; setup and
  compound references teach the relevant use. Generated APM instructions were
  regenerated from their owners. Hooks remain unchanged.
- P4: profiles may declare one external private dotenv file and exact
  source-to-target mappings. The core reports only safe metadata/readiness;
  values remain outside workspace fingerprints, receipts, usage exports and
  compounding routes. Setup creates content-addressed value-free provider launchers,
  reports Codex/Copilot launch forms and binds Claude's native SessionStart
  channel. Claude session pins contain paths/mappings only and preserve the
  original declaration across resume/compaction. Shell-control targets,
  oversized pins, unsafe sources/destinations and blocking special files are
  rejected before they can expose or hang a harness.
- Final review replaced the callable shell-export renderer with an exec-style
  provider launcher, keyed Claude pins to the stable consumer across registry
  changes, and expanded target validation to provider/runtime control names.
- The final provider-boundary review made a missing Claude native environment
  channel visible in hook context, moved required Copilot protection flags into
  the launcher itself, rejected caller overrides and preserved `doctor`'s exact
  safe diagnostic and remediation through setup failures.
- Live Copilot proof exposed that `--secret-env-vars` removes protected values
  from its Bash tools as well as redacting output. The generated launcher now
  uses Copilot's supported `BASH_ENV` channel to restore declared tool targets
  after filtering without persisting values in the launcher. Protected internal
  aliases provide native output redaction without letting the mapped value for
  a tool target such as `GH_TOKEN` override Copilot's own authentication.

Deterministic evidence:

- Full repository suite: **1,334 passed**. Ruff lint/format and strict mypy pass.
  Wheel and sdist builds pass. Both setup and compound skills pass validation.
- Integration covers all configured CLI operations, exact session propagation,
  separate profile processes, per-field path origins, replaced offline sources,
  invalid registries, pinned continuations, active-run routing checks, equivalent
  aliases, checked registry writes and exported configuration descriptors.
- `tests/e2e/fresh_consumer_smoke.py --keep --live-cli`: passed in an isolated
  consumer. Profile-selected setup preserves overrides, repeat setup/reinstall
  keeps one managed hook, and source resources match the installed distribution.
  Codex 0.154.0, Claude Code 2.1.236 and Copilot CLI startup checks passed.
  All three installed hook fixture contracts passed, including exact session
  context. A later 1.0.86 update added live-proven Copilot
  `userPromptTransformed` reflection alongside `sessionStart`.
- The complete workflow test exposed and fixed an export lookup that still
  assumed workspace fingerprints were descriptor filenames. Descriptor content
  now determines its filename; event references are validated before export.
- The profile-specific harness fixture initially omitted required `topics` on
  a runbook. Preflight rejected it before any model call; the fixture was fixed.

Final profile-environment evidence is under
`.cache/profile-environment-fresh-consumer-final-v3.json`,
`.cache/profile-environment-claude-live-summary.json` and the
`.cache/profile-environment-live-v3-{codex,copilot}.{stdout,stderr,message}`
artifacts. Earlier profile workflow reports remain under
`.cache/profiles-fresh-consumer.json` and `.cache/profiles-claude.json`.
Reproducible commands are in `docs/r8-harness-proof.md`. The original profile
proof did not include scheduling. Later evidence separately proves Codex
Scheduled compounding and records Copilot CLI scheduling as session-scoped,
not durable unattended automation.

The P4 isolated consumer used two mode-`0600` env files and two profiles. Their
launchers passed only their declared targets, a resumed Claude session retained
the first declaration after setup rebound the consumer from a different registry,
and a new session received the second declaration. Both disposable canaries
were absent from logs, setup/hook JSON, launchers, pins, receipts and usage
evidence. A final live Claude Code 2.1.236 / Claude Opus 5 turn made exactly one
Bash presence check and returned `ENVIRONMENT_PRESENT`; the canary was absent
from the complete JSONL transcript. The first live attempt exposed that Claude
passes a missing `CLAUDE_ENV_FILE` path; the adapter now creates that
provider-owned file privately and the regression test mirrors the real contract.

Live Codex CLI 0.154.0 and Copilot CLI 1.0.86 runs then used the exact
setup-reported launchers from a newly built consumer. Each agent made one Bash
presence check, returned `ENVIRONMENT_PRESENT`, and left the disposable canary
absent from stdout, stderr and its saved transcript. Copilot used
`--model auto --auto-tier efficiency`; the account exposed and selected
`mai-code-1.1-flash`. The first pre-fix Copilot run returned
`ENVIRONMENT_MISSING`, directly proving that native secret filtering removed
the mapped target; the post-fix run proves the private process-lifetime
`BASH_ENV` activation path.

Live acceptance completed successfully with Claude Code 2.1.236 / Claude Opus 5:

| Session profile | Knowledge result | Signal/session proof | Resume/default-change proof |
| --- | --- | --- | --- |
| `personal` | Retrieved `blue-window-17` through catalog, search, inspect and a bounded body read | One recorded signal with exact hook ID; four retrieval receipts identify only `personal` | Inspected the pending body and retained exactly one signal after the default switched to `work` |
| `work` | Retrieved `amber-window-29` through the same progressive flow | One recorded signal with exact hook ID; four retrieval receipts identify only `work` | Inspected the pending body and retained exactly one signal after the default switched to `personal` |

Both other-profile session lookups returned zero matches. These were separate
fresh provider sessions, each followed by a native resume turn. The acceptance
used one generic hook installation and an explicit registry. The first model's
initial absolute `origin.project_path` draft was rejected by validation; it
corrected that field to the configured relative project path before recording.
This is successful validation-and-repair behavior, not a claim that the model
never makes an invalid request.

The repository's APM installation was rebuilt to remove four stale generated
bytecode entries. Its final audit reports **no drift and no issues** across 33
files. Native schedules remain outside this proof. The live test restored the
Copilot Bash-support preference to neutral `{}` with mode `0600`; no real user
registry or existing automation was changed. The changes are ready for review;
publication is not part of this implementation request.
