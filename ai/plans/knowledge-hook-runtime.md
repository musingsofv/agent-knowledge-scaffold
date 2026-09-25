# Organization-Neutral Knowledge Hook Runtime

**Date:** 2026-09-11
**Status:** implemented (H1-H4)
**Repo Scope:** agent-knowledge-scaffold
**Primary PR Repo:** agent-knowledge-scaffold

> Historical H1-H4 plan. The current session-aware reflection, signal
> provenance and prompt-reminder contract is defined by
> [signal-reflection-and-session-provenance.md](signal-reflection-and-session-provenance.md).
> Copilot CLI 1.0.86 subsequently added a usable model-visible
> `userPromptTransformed` hook. The installed runtime now binds that event for
> per-prompt reflection; Copilot still has no model-visible post-compaction
> event. Current support evidence lives in `docs/harness-support.md`.

## Table Of Contents

1. [Plan Brief](#1-plan-brief)
   1. [Outcome](#11-outcome)
   2. [Feature Shape](#12-feature-shape)
      1. [Today](#today)
      2. [Planned Delta](#planned-delta)
      3. [Must Preserve](#must-preserve)
   3. [Capabilities Delivered](#13-capabilities-delivered)
2. [Build Contract](#2-build-contract)
   1. [Delivery Slices](#21-delivery-slices)
   2. [Implementation](#22-implementation)
      1. [Data Model](#data-model)
      2. [API Contract](#api-contract)
      3. [Events / Messages](#events--messages)
      4. [Business Rules](#business-rules)
      5. [Config](#config)
      6. [Automated Tests](#automated-tests)
   3. [Deployment](#23-deployment)
3. [Appendix](#3-appendix)
   1. [Context Used](#31-context-used)
   2. [Additional Notes](#32-additional-notes)

## 1. Plan Brief

### 1.1 Outcome

A fresh scaffold installation gives an engineer one concise, provider-native knowledge-discovery reminder at session start and after an exposed context resume, without making the hook a second instruction owner or a participant in retrieval. Completion reflection and signal-writing reminders are outside this change; the provider matrix records them only as future design context.

### 1.2 Feature Shape

#### Today

Before this hook follow-up, the fresh core had a package-owned discovery instruction, a runtime-installed guide, workflow skills and generated harness projections. `AGENTS.md`, `CLAUDE.md` and Copilot instruction files are projections of the APM instruction. The package did not install hooks.

The earlier organization-specific implementation used broad prompt and pre-tool heuristics, source-edit reminders, task/repository receipts and more than one provider output field. That behavior is reference evidence for failure modes, not a runtime dependency for this organization-neutral scaffold. The current core's receipts are optional search/inspect traces and are deliberately separate from hook behavior. Provider-native prompt events may deliver the separate reflection reminder; they do not perform discovery or retrieval.

#### Planned Delta

The same installable APM package will include a minimal hook capability. The normal setup path will register one package-owned discovery hook per available supported provider, idempotently and by default. The hook will respond only to a native session-start event and an exposed resume/compaction event. It will emit a short static reminder through one provider-supported context field and otherwise do nothing. The provider matrix below records completion events for future design only; this change does not register, deliver or test a reflection or signal-writing reminder.

The hook will have no knowledge or configuration intelligence. It will not call the CLI, read files, plan searches, interpret taxonomy, inspect graph links, write coverage state or trigger compounding. Provider adapters will normalize event payloads and render the selected message; a small pure core will decide start, resume or no-op.

The installation and generated-projection checks will make the ownership boundary explicit: one authored instruction owns the mechanical discovery contract, the installed guide owns detail, skills own workflows, and the hook owns only activation text and transport. The package descriptor carries only an `agent-knowledge-hook` marker; setup requires and verifies an installed CPython 3.11.x, installs the distribution into its scaffold-local venv, and rewrites the package-owned provider commands to that absolute launcher. Setup and `doctor` will diagnose registration and path problems; the hook will fail open.

#### Must Preserve

- The scaffold remains organization-neutral and contains no copied organizational knowledge or legacy compatibility layer.
- The APM package/distribution role remains first-class alongside the Python core.
- Generated harness instructions remain projections of one source owner; hand-authored harness configuration is preserved.
- Query planning, relevance, body reads, link traversal and stopping remain agent responsibilities.
- Scheduled compounding invokes `knowledge-compound` directly through the harness automation; the hook is not in that path.
- Domain code remains free of filesystem, environment, network, Git, clock, receipt and provider side effects.
- Receipts remain honest optional operation traces; they never become hook state or semantic coverage claims.
- Hook failures, missing providers and unsupported events never block engineering work.

### 1.3 Capabilities Delivered

| Status | ID | Capability | Expected Behavior | Important Conditions | Proof Signal |
| --- | --- | --- | --- | --- | --- |
| - [x] | C1 | Default hook installation | A standard package/setup installation ships and enables the hook for each available supported provider without a separate opt-in step. | Missing or unauthenticated providers are reported individually; no legacy registration is imported. | Fresh-consumer install and setup fixtures for Codex, Claude and Copilot. |
| - [x] | C2 | Idempotent registration ownership | Re-running setup updates one package-owned registration, preserves unrelated configuration and exposes a package-only disable/remove path. | Global/workspace overlap and conflicting hand-authored entries produce diagnostics; no silent cleanup. | Registration diff/idempotence, preservation and disable tests. |
| - [x] | C3 | Deterministic lifecycle reminders | One start reminder is emitted per provider session and one focused reminder is emitted for each exposed resume/compaction event. All three supported providers have a native session-start event; `first_task` remains a reserved normalization value for a future provider and is never inferred from prompt text. | No prompt keywords, path heuristics, timers or task/repository coverage receipts. | Pure event truth table and provider session/event retry tests. |
| - [x] | C4 | Single-channel provider delivery | A reminder reaches the agent through exactly one provider-supported context field per invocation. | Claude, Codex and Copilot may use different fields; an adapter never sends duplicate copies. | Provider payload fixtures assert one populated context channel. |
| - [x] | C5 | Advisory, portable runtime | Hook execution is bounded, path-independent and fail-open when input, installation or provider state is unavailable. | No current-directory guessing, ambient organization variables, private source paths, network calls or blocking exit. | Missing-env/deep-cwd, malformed-input, timeout and unsupported-event fixtures. |
| - [x] | C6 | Strict hook boundary | The hook only selects a static start/resume message and provider transport. | It never searches, inspects, reads, filters, infers taxonomy, traverses links, invokes a model or triggers compounding. | Mocks/import guards prove no CLI, filesystem, receipt or model calls. |
| - [x] | C7 | Honest receipt separation | Search and inspect may append optional `knowledge-receipt.v1` JSONL traces; hook invocations do not read, write or interpret them. | Receipts record returned identities/fingerprints and `body_read: unknown`; failed trace writes do not fail successful operations. | Existing receipt unit/integration tests plus hook no-receipt assertions. |
| - [x] | C8 | Source/projection/provider proof | The source instruction, generated projections, installed guide, setup skill, package manifest and provider adapters remain synchronized. | Hook text is not a copied instruction manual; real-provider proof is limited to supported exposed events. | Compilation parity, stale/duplicate ownership diagnostics, fresh consumer and live provider smoke, including the required Claude Code Opus 5 run. |

## 2. Build Contract

### 2.1 Delivery Slices

| Slice | Capabilities Covered | Repo(s) | Base / Stack Parent | Existing Surface / Likely Touchpoints | Notes |
| --- | --- | --- | --- | --- | --- |
| H1: Hook and receipt contracts | C3, C4, C6, C7 | agent-knowledge-scaffold | origin/main | Pure hook event/decision values, static reminder resource, existing `infrastructure/receipts.py`, unit tests | Establish the provider-neutral discovery boundary and preserve the current honest receipt contract. No provider registration yet. |
| H2: Provider adapters and package declaration | C1, C3, C4, C5 | agent-knowledge-scaffold | H1 | `packages/knowledge-agent-pack`, provider adapter resources and contract fixtures | Add thin Codex, Claude and Copilot start/resume event/output mappings. Keep provider fields out of the core decision module. The completion matrix remains research-only. |
| H3: Setup and ownership integration | C1, C2, C5, C8 | agent-knowledge-scaffold | H2 | `knowledge-setup`, setup helper/config, APM compile/projection checks, `doctor` diagnostics and setup docs | Register/update discovery start and resume hooks by default, preserve hand-authored configuration and implement explicit disable/remove behavior. When setup rewrites the standalone Copilot file to the verified launcher, reconcile both corresponding APM lock hashes so package-only uninstall remains safe. |
| H4: Fresh and live harness proof | C1-C8 | agent-knowledge-scaffold | H3 | Fresh-consumer e2e fixtures, provider drivers, package README, `docs/fresh-consumer.md`, plan references | Prove the installed path and supported discovery start/resume events. A disposable live Claude Code run with the Opus 5 model is required; Codex/Copilot runs remain capability-gated. No scheduled-compounding or signal-writing test is added to the hook flow. |

#### H1-H4 implementation checkpoint

H1 through H4 are implemented on `main` in separate commits: H1
`fb11cc7`, H2 `46512c1` (with dispatch cleanup in `2ffac0a`), H3 `38022ee`,
and H4 `34a4b3c`. The hook decision and provider rendering are now used by the
installed `agent-knowledge-hook` console script. There is no package-bundled
standalone hook copy. Setup verifies the venv's actual interpreter is Python
3.11.x before registering the absolute launcher command and updates both APM
lock hashes for the rewritten Copilot hook file.

The H4 proof passed the full root suite (**965 tests**), Ruff lint,
check-only formatting, strict mypy, `git diff --check`, the installed
three-provider hook fixture, and the fresh-consumer smoke. The smoke verified
one owned registration per target, one-channel startup/resume output,
unrelated-event no-ops, hand-authored hook preservation, package-only
uninstall and source-path reinstall.

The live Claude Code 2.1.236 provider probe resolved `--model opus` to the
exact `claude-opus-5` model and passed startup/resume delivery for one session
with `START_OK`/`RESUME_OK` markers. The reusable live driver uses a temporary
`CLAUDE_CONFIG_DIR` and reports `auth-required` when the provider credential is
not available in that isolated configuration; it never falls back to another
model or mutates global settings. No deterministic live compaction trigger was
available, so compaction remains covered by the synthetic provider fixtures.

#### Post-review recovery proof (2026-09-12)

The corrected fresh-consumer test reruns setup after source-path reinstall
and verifies both APM ownership sidecars and merged provider settings. Every
runnable package hook must use the exact absolute consumer launcher; a bare
descriptor marker no longer passes after setup. The outer wheel-test venv is
excluded from PATH, unrelated hooks survive, and Copilot retains native
`sessionStart` plus `userPromptTransformed`. This reinstall/rebind proof passed
for Codex, Claude and Copilot. Setup documentation now includes the recovery step.
The later live model authoring/reflection proof belongs to the
[session/reflection plan](signal-reflection-and-session-provenance.md) and
extends the original H4 transport scenario.

### 2.2 Implementation

#### Data Model

Use a small provider-neutral event model containing only:

- `provider`: `codex`, `claude` or `copilot`;
- `event`: `session_start`, `first_task`, `resume`, `compaction` or `other`;
- `source`/`reason` normalized only when the provider supplies one, so the
  decision can distinguish a new session from a context transition without
  reading prompts or transcripts;
- optional opaque provider `session_id` and `event_id` for native lifecycle identity.

The pure decision returns `start`, `resume` or `none`, plus a message
identifier. Completion/reflection events are not part of this implementation's
event model; the matrix below is retained as future design context. The
decision receives no prompt body, file path, workspace configuration or
taxonomy value. Provider adapters own parsing and output serialization.

Hook registration metadata carries a package-owned marker, source/version identity and provider capability. It is installation state, not canonical knowledge and not a receipt.

Receipts remain a separate runtime record. `knowledge-receipt.v1` is append-only JSONL with a UTC timestamp, operation (`search` or `inspect`), normalized structured request, configured source IDs, returned source-relative document identities and complete-byte fingerprints, and `body_read: unknown`. It does not store bodies, conversation transcripts or claims of semantic coverage.

#### API Contract

The internal hook boundary is conceptually:

```text
HookEvent -> HookDecision
```

`HookDecision` is either no-op or one of the two discovery message identifiers.
The provider adapter maps an eligible decision to exactly one of the provider's
supported context fields. Completion/reflection decisions are deliberately
absent from this change; the core never returns provider JSON.

The existing receipt boundary remains an optional operation parameter. A caller supplies a receipt path explicitly; no default receipt file is created by search, inspect or setup. The parent directory must already exist and must be outside canonical knowledge and signal roots.

#### Events / Messages

Start message:

```text
Before engineering work, run `agent-knowledge describe`, then use targeted `search` and `inspect` calls for the task. Follow the installed guide.
```

Resume message:

```text
Context may have been compacted. Run `agent-knowledge describe` again, then rediscover relevant metadata with targeted `search` and `inspect` calls.
```

Future reflection message (outside this change; carried by the workflow skill, not a provider hook):

```text
Before finishing, reflect on whether this work exposed a durable knowledge or skill gap. If so, record it with `agent-knowledge signal record`.
```

#### Provider lifecycle matrix (updated 2026-09-21)

The mappings below use the providers' documented command-hook contracts. The
provider adapters keep raw event names and matcher values at the boundary and
normalize them before the pure decision function runs.

| Provider | Session-start discovery | Resume/compaction rediscovery | Completion/reflection candidates | Selected delivery and registration rule |
| --- | --- | --- | --- | --- |
| **Codex** | `SessionStart` with matcher `source: startup` is the new-session event. `source: clear` resets the conversation and is treated as rediscovery. | `SessionStart` with `source: resume` is the documented resume path. `source: compact` runs after manual or automatic compaction and before the next model request, including an automatic mid-turn continuation. Use this one path; do not also register `PostCompact`. | `Stop` fires after every model turn and `decision: block` creates a continuation prompt. `SessionEnd` runs only when the main thread closes, is archived/deleted or has been idle for 30 minutes; its output is advisory and cannot steer the model. Neither is a safe non-blocking task-completion reminder. | Use JSON `hookSpecificOutput.additionalContext` on `SessionStart` only. `PreCompact` is before compaction and can stop it; it is not a rediscovery channel. Registration may be plugin-bundled or in the documented Codex hook layers, with an absolute package path. |
| **Claude Code** | `SessionStart` with matcher `source: startup` is the new-session event. | `SessionStart` with `source: resume`, `clear`, `compact` or `fork` runs before the next request after the corresponding context transition. `PostCompact` runs after compaction but has no context/decision delivery; `PreCompact` can block compaction. Use `SessionStart` and do not duplicate it with either compact hook. | `TaskCompleted` is the task registry/`TaskUpdate` event (or a teammate finishing with in-progress tasks), has no model-context output and can block completion. `Stop` fires for every main-agent turn; `additionalContext` is delivered only by continuing the conversation, and `decision: block` explicitly prevents stopping. `SessionEnd` cannot deliver context and has a short synchronous budget. None is an advisory main-task reflection channel. | Use JSON `hookSpecificOutput.additionalContext` on `SessionStart` only. A command hook is required at launch because MCP hooks may run before MCP context is available. Register through the package/plugin hook surface without copying the discovery guide. |
| **GitHub Copilot CLI** | Native `sessionStart` with `source: startup` or `new` is the start event. The event has no documented matcher, so one handler branches on `source`; in a cloud-agent job it fires once as a new session. | Native `sessionStart` with `source: resume` is handled by that same source branch. `preCompact` is notification-only and there is no post-compaction model-context event; the next actual prompt receives reflection through `userPromptTransformed`. | Native `userPromptTransformed` is model-visible in interactive and `-p` modes and returns `modifiedTransformedPrompt`. `agentStop` can force another turn and `sessionEnd` cannot inject context, so neither is used. | Use `additionalContext` on `sessionStart` and `modifiedTransformedPrompt` on `userPromptTransformed`, one channel per invocation. Repository prompt-mode hooks require an already trusted folder; `-C` and `--add-dir` do not establish that trust. |

The three providers therefore share a reliable start path and a usable
resume path. Codex and Claude expose compaction through `SessionStart`; Copilot
CLI does not expose an equivalent model-visible post-compaction event. Their
completion events are useful for diagnostics or future provider-specific
features, but none satisfies all of the reflection requirements: main-task
meaning, delivery to the agent, non-blocking behavior and once-only semantics.
The installed workflow skill remains the authoritative place for the
reflection instruction. A future adapter may opt in only after a provider
documents all four properties and its contract tests prove them.

The adapter contract should pin the fields it actually consumes:

- **Codex:** command-hook JSON on `stdin` with `hook_event_name`,
  `session_id`, `transcript_path`, `cwd` and `source`; matchers are evaluated
  against `source`. The adapter emits only the documented
  `hookSpecificOutput.additionalContext` for `SessionStart`.
- **Claude Code:** command-hook JSON on `stdin` with the common
  `session_id`, `transcript_path`, `cwd` and `hook_event_name` fields plus
  `source`; matchers are evaluated against `source`. The adapter emits only
  `hookSpecificOutput.additionalContext` for `SessionStart`.
- **GitHub Copilot CLI:** native camelCase command-hook JSON with
  `sessionId`, `timestamp`, `cwd` and `source` for lifecycle, plus
  `transformedPrompt` for prompt delivery. The adapter branches on `source`
  for `sessionStart`, emits `additionalContext` there, and appends reflection
  through `modifiedTransformedPrompt` for `userPromptTransformed`.

The adapters ignore transcript and filesystem fields. Copilot carries the
opaque `transformedPrompt` only long enough to append the static reflection
trailer; it does not inspect or interpret its text. Adapters may retain opaque
session/event identifiers only for in-process coalescing and must not derive
task meaning from prompt content.

The registration prefers the native session-start event. All currently
supported providers have one, so there is no first-prompt heuristic fallback.
`first_task` remains a reserved normalized value for a future provider only.
If a provider exposes both equivalent start events, the adapter coalesces them
using native event/session identity or registers only one. A resume/compaction
event produces one resume message for that event. No previous results or body
content are replayed.

No hook invocation is registered for edits, reads, grep/glob, CLI calls, source
changes or scheduled compounding. Provider-native prompt hooks deliver only the
reflection reminder; they do not plan or perform retrieval. A provider without
a usable lifecycle event is documented as instruction-only rather than
receiving a heuristic fallback.

#### Business Rules

- Package installation and normal setup include the hook by default. Explicit disable/remove is supported after installation.
- One install scope owns the package registration. Reconciliation updates only that marked registration and never appends duplicates or deletes unrelated entries.
- The authored APM instruction is the only mechanical discovery-policy owner. Generated `AGENTS.md`, `CLAUDE.md` and Copilot projections are derived outputs.
- The installed guide is the detailed contract. Skills reference it and add workflow-specific behavior. The hook reminder is a short activation nudge, not a second guide.
- `first_task` is a reserved event for a future provider with no native session-start callback. It is a no-op in the three current adapters; no prompt or tool event is promoted into a lifecycle event.
- Each provider invocation has at most one agent-visible context field. Populating `systemMessage` and `hookSpecificOutput.additionalContext` together is invalid.
- No completion event is registered. The current reflection reminder is
  delivered by provider prompt events and points to the source-owned workflow;
  it remains advisory and does not judge or write signals itself.
- Hook execution does not inspect configuration or knowledge. Setup/`doctor` own those checks and show repair guidance.
- Hook failures are advisory: malformed payloads, unsupported events, missing executables and provider output errors become no-op/allow behavior with safe diagnostics.
- No old organization-specific environment variables, service lists, path fallbacks, compatibility imports, source-edit receipts or generic “knowledge completed” state are restored.
- Receipts are never consulted for start/resume suppression. They cannot authorize an action, prove a body read or trigger compaction replay.
- Lifecycle payloads are not receipts. The discovery hook may use opaque provider session/event IDs for coalescing, but it never persists them as search coverage, signal state or compaction replay state.
- Receipt writes remain append-only, no-follow and mode-restricted where the existing adapter supports it. The parent directory is not created as a search side effect; a write failure is reported separately from a successful search/inspection.
- The pure hook and domain layers have no filesystem, environment, network, Git, clock, subprocess, model or receipt side effects. Provider and receipt adapters remain outside them.

#### Config

- The package manifest declares the hook resources and provider capabilities.
- Setup defaults to `codex`, `claude` and `copilot` when installed/available. It does not ask the developer to select providers or supply taxonomy values for the hook.
- Setup registers the documented start/resume event entries that can deliver context (`startup` plus `resume`/`clear`/`compact` as mapped in the matrix). Where a provider has no `SessionStart` matcher (Copilot CLI), one handler branches on the supplied `source`; it does not use prompt inspection. It does not register `PreCompact`, `PostCompact`, `Stop`, `TaskCompleted`, `agentStop` or `SessionEnd` for reflection merely because their names sound like lifecycle boundaries.
- A provider or workspace may explicitly disable the package-owned hook. Re-enabling runs the same idempotent reconciliation.
- Registration uses explicit package/runtime paths captured during installation; it does not depend on the current working directory or ambient shell variables.
- No new organization, service, technology, scope or organization-specific environment configuration is embedded in the hook.
- Receipt paths remain explicit runtime options. If a consumer enables a trace, setup may recommend a scaffold-local ignored runtime directory, but receipts never live in canonical knowledge, `ai/signals/`, generated instructions or provider hook state.

#### Automated Tests

| Capability | Test Level | Existing Test Pattern / File | What The Test Proves |
| --- | --- | --- | --- |
| C1-C2 | integration/static | New package-install and registration fixtures under `tests/integration/`; APM projection checks | Fresh installation declares the hook, registers once, preserves unrelated configuration and removes only its own registration. |
| C3 | unit | New pure hook decision tests under `tests/unit/domain/` | Session-start, reserved first-task no-op, resume/compaction, duplicate event and ordinary-event truth tables behave deterministically without prompt heuristics; Copilot's unfiltered `sessionStart` source branch is covered. |
| C4 | unit/integration | Provider adapter fixtures under `tests/unit/` and `tests/integration/` | Each supported provider emits valid output through exactly one context channel, with native snake_case/camelCase payload shapes kept at the adapter boundary. |
| C5-C6 | unit/integration | Hook runtime and fresh-consumer fixtures | Missing paths, malformed payloads, deep cwd, absent environment and unsupported events fail open without retrieval, file, model or blocking side effects. |
| C7 | unit/integration | Existing `tests/unit/infrastructure/test_receipts.py` and `tests/integration/application/test_retrieval.py` | Receipts remain optional, append-only and honest; hook execution creates no receipt and never interprets one. |
| C8 | acceptance/e2e | `tests/e2e/` fresh-consumer and provider drivers | Source/projection/guide/adapter parity holds in an isolated consumer, with one-shot discovery start/resume proof for every available supported harness. |

The fast semantic suite must exercise the pure event decision in memory. Provider installation, filesystem and live harness checks remain integration or acceptance tests. The live proof records unavailable or unauthenticated providers without treating them as implementation failures.

#### Required live Claude Code acceptance (H4)

The first live-provider proof must run against the fixed Claude Code CLI using
the installed Opus 5 model. The driver must discover and validate the exact
installed model identifier (for example, the CLI may expose `opus` as an alias
or a full `claude-*-5` name) and must fail rather than silently fall back to a
different model.

Run the package in a disposable consumer directory with disposable Claude
settings/plugin state. Do not use `--bare`, because that mode deliberately
skips hooks. Capture `--include-hook-events` with
`--output-format stream-json`, the Claude Code version, the model identifier,
the opaque session id and the hook event payloads; redact prompts, credentials
and unrelated transcript content before retaining evidence.

The acceptance sequence is:

1. Start a new session and prove one `SessionStart(source=startup)` event and
   one model-visible discovery reminder delivered through
   `hookSpecificOutput.additionalContext`, with no second context channel.
2. Resume the same session using the native resume path and prove one
   `SessionStart(source=resume)` rediscovery reminder.
3. Exercise `/clear` and a controlled manual or automatic compaction when the
   installed CLI exposes them, proving the corresponding `clear`/`compact`
   `SessionStart` event and one rediscovery reminder. If a compaction cannot be
   triggered deterministically in the isolated run, record that limitation and
   retain the synthetic payload proof; do not claim live compaction coverage.
4. Run with a deliberately unavailable or failing hook subprocess and prove
   the Claude session continues, establishing advisory fail-open behavior.
5. Confirm the package registers no `Stop`, `TaskCompleted`, `SessionEnd` or
   signal-writing hook. This acceptance does not record signals or invoke
   compounding.

The test must leave the user's global Claude settings and sessions unchanged.
An unauthenticated CLI, unavailable Opus 5 model or missing lifecycle callback
is a clearly reported unavailable proof, not permission to substitute a
different provider or model.

#### Brief operator instructions

Run this acceptance from a disposable consumer with a temporary local settings
file. Do not use `--bare`, because it disables hooks:

```bash
claude --model opus \
  --setting-sources project,local \
  --include-hook-events \
  --output-format stream-json \
  --verbose \
  --permission-mode plan \
  --max-budget-usd 0.25 \
  -p 'Respond with exactly START_OK.'
```

Extract the `init.session_id`, assert `model` is the exact Opus 5 identifier,
and assert one `hook_started`/`hook_response` pair for
`SessionStart:startup`. Parse the response JSON and assert that
`hookSpecificOutput.additionalContext` is populated; the required
`hookEventName` envelope is not a second agent-visible context channel.
Resume that same ID with `--resume "$SESSION_ID"` and a `RESUME_OK` prompt,
then assert `SessionStart:resume`, the same session ID, the same model and one
rediscovery `additionalContext`. Ignore non-JSON diagnostic lines when parsing
`stream-json` output, but retain their presence in the raw disposable log.

Run the clear/compaction and failing-hook checks from the acceptance sequence
only when the installed CLI exposes a deterministic way to trigger them. Keep
those results separate from the startup/resume proof, and report an unavailable
or non-deterministic provider event rather than substituting a different event.
Record only the CLI version, exact model, event names/sources, session identity,
exit codes, result markers and redacted hook payloads; delete the temporary
consumer, settings, sessions and logs after the run.

### 2.3 Deployment

This is local package and harness configuration work. There is no repository daemon, scheduler, background loop, network service or database migration. The normal order is H1, H2, H3 and H4, with each slice independently green and reviewable.

Rollback is a package/source revision revert or disabling the package-owned registration. It does not remove user-authored configuration, knowledge files, signal files or receipt logs. Existing old registrations are not migrated; conflicts are reported for explicit operator cleanup.

### 3. Appendix

#### 3.1 Context Used

- [`ai/plans/organization-neutral-knowledge-core.md`](organization-neutral-knowledge-core.md) — establishes the fresh-core boundary, pure `domain` module, optional honest receipts, explicit configuration, scheduled compounding and no legacy compatibility.
- [`docs/agent-contract.md`](../../docs/agent-contract.md) — defines the installed guide, progressive search/inspect contract and current `knowledge-receipt.v1` behavior.
- [`packages/knowledge-agent-pack/.apm/instructions/agent-knowledge-discovery.instructions.md`](../../packages/knowledge-agent-pack/.apm/instructions/agent-knowledge-discovery.instructions.md) — current single authored discovery instruction.
- [`packages/knowledge-agent-pack/README.md`](../../packages/knowledge-agent-pack/README.md) and [`docs/fresh-consumer.md`](../../docs/fresh-consumer.md) — current installation/projection documentation that must be updated when the hook becomes part of installation.
- [`src/agent_knowledge/infrastructure/receipts.py`](../../src/agent_knowledge/infrastructure/receipts.py) — existing append-only trace adapter and failure semantics preserved by C7.
- [Codex Hooks](https://learn.chatgpt.com/docs/hooks) — official `SessionStart` (`startup`, `resume`, `clear`, `compact`) and `SessionEnd`/`Stop` semantics, context delivery and continuation limits (retrieved 2026-09-11).
- [Claude Code Hooks reference](https://code.claude.com/docs/en/hooks) — official `SessionStart` (`startup`, `resume`, `clear`, `compact`, `fork`), `PreCompact`/`PostCompact`, `TaskCompleted`, `Stop` and `SessionEnd` semantics (retrieved 2026-09-11).
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference) and [Using hooks with GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks) — official CLI `sessionStart`, `preCompact`, `agentStop`, `sessionEnd`, payload/output and configuration-scope behavior (retrieved 2026-09-11).

#### 3.2 Additional Notes

The provider probe (2026-09-11) used a disposable Claude Code 2.1.236
consumer and `--model opus`, which resolved to the exact `claude-opus-5` model.
It emitted `SessionStart:startup` and `SessionStart:resume` for the same
session; both responses delivered the expected marker through one
`additionalContext` field and the model returned `START_OK`/`RESUME_OK`.
The installed-package fixture provides the deterministic implementation proof;
the reusable live driver keeps authenticated execution opt-in and reports
`auth-required` when its isolated configuration has no usable credential.
Compaction has no deterministic live trigger in the available CLI and remains
covered by synthetic provider fixtures. The live failing-hook path is likewise
available through the driver when authentication is supplied.

Receipts have a special implementation boundary but no special hook role. Their code stays in infrastructure, the application layer supplies the returned identities, and the domain remains pure. They are useful for operational inspection and retrieval evaluation, while ordinary `cat`, `grep` and editor reads remain unknown. They should not be moved into `ai/signals/`, canonical knowledge, generated harness instructions or hook state.

The current core plan's statements that hooks are outside the original core
slice remain historical context. H3/H4 updated the affected package, setup and
documentation surfaces so the hook manifest, generated projections, guide and
documentation agree. No retrieval planner, coverage checklist, automatic
compaction replay or scheduled-compounding behavior is added by this plan.

The provider research remains in the matrix as future design context. A
lifecycle event existing does not mean it is a usable agent context boundary:
Codex `Stop`, Claude `Stop` and Copilot `agentStop` are per-turn continuation
controls; Claude `TaskCompleted` is a task-registry completion gate; and all
three providers' session-end outputs are not delivered back to the model. This
change deliberately does not implement or test those events, and leaves signal
writing to the existing workflow/compounding design.
