# Local compounding fallback and bring-your-own container setup

Date: 2026-10-06
Status: S1-S5 complete; all acceptance criteria verified with the stated proof limits.
Repository: agent-knowledge-scaffold.
Inspected baseline: `c2e6d875a68d165e3d94870c5040980625ac9451`.

This plan records the owner's accepted direction and acceptance criteria. It
covers reusable scaffold code, skills, references and proof. Creating this plan
does not install hooks, alter existing automations, change consumer repositories,
publish changes or implement the feature.

Follow-up: [existing-container setup and launch readiness](container-setup-and-launch-readiness.md)
adds environment detection, private profile preparation and actual-launcher
acceptance. Its planned work is separate from the completed results below.

## Outcome and scope

Developers keep their own Docker/devcontainer image, tools and startup workflow.
The setup skill makes the installed knowledge runtime available inside that
environment, including when the whole Codex CLI, Claude Code or Copilot CLI
process runs there. No scaffold-owned base image or mandatory devcontainer is
required.

For compounding, setup prefers an available, durable native local harness
schedule. If that capability is unavailable, it configures a prompt-triggered
hook fallback. The hook normally adds no compounding text; when work is due, it
asks the main agent to delegate to the installed `knowledge-compound` skill.
Timing is opportunistic: no qualifying prompt means no run. Different provider
event names and message wording are acceptable; all three harnesses must deliver
the same user-visible behavior.

Cloud compounding recommendations are removed from current setup guidance,
provider references and examples. Local runs may still publish GitHub PRs under
the existing publication policy. Preserve human merge/review boundaries and all
signal ownership, evidence, validation and guarded-drain requirements.

Out of scope: a scheduler framework, a bundled Dockerfile/Compose/devcontainer,
cloud jobs, hidden daemons, automatic cron/systemd installation, product features,
corpus migration, a second coordination database, and changes to unrelated
consumer or user-wide configuration. Existing external jobs are not silently
deleted or claimed by this feature.

## Developer workflow

1. The developer launches a supported harness inside their existing environment
   and submits a normal prompt in a new or existing session.
2. The provider's prompt hook calls a short installed due-check using the
   explicitly selected profile/registry or supported explicit workspace.
3. If the fallback is disabled, a local schedule owns the store, work is recent,
   the pending inbox is known empty, or a run is active, the hook emits no additional
   compounding instruction. Existing discovery/reflection reminders still work.
4. If due, the hook emits one concise delegation instruction with the exact
   selector and installed resource locations. It does not invoke a model,
   perform compounding or reserve a worker before spawning.
5. The main agent uses its harness's native subagent tool to start a worker that loads `knowledge-compound`, receives
   the selector and work context, and atomically rechecks eligibility before
   starting a run or making compounding edits. A redundant worker exits.
6. The main agent can continue the developer's task. The worker follows normal
   owner discovery, isolation, validation, PR publication and safe-drain rules.
7. Run and available worker identities are recorded. Finished-run evidence,
   rather than reminder delivery or spawning, determines the next due time.
8. Meaningful results, PR links and actionable failures are reported. An
   interrupted run remains inspectable and is reconciled before further work;
   a stored worker ID does not guarantee that worker can be resumed.

## Acceptance criteria

The first five criteria carry forward the agreed implementation bullets.

- [x] **AC1 - Conditional compounding hook.** Codex CLI, Claude Code and Copilot
  CLI each support the fallback. The installed script checks due state and
  emits no compounding instruction when work is not due. When due, it delivers
  concise provider-native instructions to delegate the installed skill. An
  existing session crossing the interval is handled on its next prompt.
- [x] **AC2 - Small runtime changes and existing state.** Eligibility and start
  are checked atomically. Reuse `ai/signals/compound-activity.jsonl`; do not add
  a separate last-run timestamp/state file. Preserve the latest relevant
  completed start/end pair through rollover, retain unfinished runs, and record
  available exact worker IDs. Durable evidence stays in existing run archives.
- [x] **AC3 - Setup owns local scheduling and fallback.** Prefer verified,
  durable native local harness scheduling; otherwise configure the prompt-hook
  fallback. Select one trigger owner per shared signal store, including profile
  aliases and multiple providers. Reuse a matching working local schedule.
  Report selected mode, timing, prerequisites, disable/pause and removal paths.
- [x] **AC4 - Compounding skill supports delegated work.** Native subagents are
  the execution interface for prompt-triggered compounding; never launch a
  model CLI through a shell as a worker substitute. The prompt hook is the
  scheduling fallback, not an alternative worker interface. Document explicit
  context handoff, duplicate workers exiting, worker reuse where supported,
  interrupted-run recovery and recursion prevention. Preserve ownership,
  publication, review and guarded drainage. No fixed reviewer/merge behavior is
  weakened by background delegation.
- [x] **AC5 - Deterministic and real-provider proof.** Test concurrent prompts,
  repeat prompts, rollover, interruption and the complete fallback flow in
  all three actual harnesses. Installed adapter fixtures alone do not satisfy
  live-harness acceptance. Record any unavailable prerequisite as missing proof.
- [x] **AC6 - Local execution guidance.** Remove cloud-compounding setup
  recommendations, cloud-automation examples and cloud credential-routing
  suggestions from active guidance. Session-only timers are not described as
  durable daily automation. GitHub PR publication remains supported. Do not
  erase historical evidence or unrelated explanations of provider boundaries.
- [x] **AC7 - Bring-your-own image.** Setup adapts to existing image/user/tool
  conventions and derives suitable internal paths. Image build can install a
  pinned runtime without mounted knowledge, profiles or credentials; post-mount
  binding can verify an already installed, root-owned runtime without installing
  packages or writing into its venv. Ordinary launches do not reinstall it.
- [x] **AC8 - Paths, persistence and credentials.** Use the existing explicit
  profile/registry/environment contracts and portable hooks. Shared state and
  locks survive container recreation on the same persistent storage. Never
  share an incompatible host venv, embed host-only paths in shared instructions,
  print credentials or borrow an unrelated profile's credentials. Required
  missing access is visible; unrelated blank mappings do not block local work.
- [x] **AC9 - Idempotent owned deployment.** Repeated setup/bind updates only
  package-owned registrations, preserves unrelated hooks and local skills, and
  supports disable/remove/reinstall. Preserve consumer APM pins, authored-source
  ownership, native install/compile/check commands and generated-output rules.
  Discovery/reflection continues even when compounding readiness fails.
- [x] **AC10 - Bounded prompt overhead.** Normal prompts do not wait for a
  compounding lifecycle lock, perform body reads, call a model or start network
  work. Due checking is bounded; busy/ambiguous state never emits permission to
  start competing work. Errors leave the developer's request usable and remain
  diagnosable without repeatedly flooding prompt context. Inbox checking uses
  bounded metadata for potential pending files; semantic eligibility belongs to
  the worker, and an incomplete scan is never reported as an empty inbox.

## Existing implementation to reuse

- [Compounding infrastructure](../../src/agent_knowledge/infrastructure/compounding.py)
  records start/end events, rejects active runs under the lifecycle lock,
  archives exact input snapshots and guards drainage.
- [Compounding evidence](../../src/agent_knowledge/infrastructure/compound_evidence.py)
  owns the shared lock and `ai/usage/compound/<run-id>/` artifacts.
- [Current hook runtime](../../src/agent_knowledge/entrypoints/hooks/runtime.py)
  and provider adapters supply discovery/reflection transport. Keep their
  provider-neutral decisions pure; workspace I/O belongs outside domain code.
- [Setup helper](../../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py)
  already separates APM `managed`, `prepare` and `bind` ownership. It currently
  installs Python in every mode and requires a real workspace and consumer.
- [Portable hooks](../../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/portable-hooks.md)
  already resolve runtime PATH and environment-local registries.
- [Repository-owned integration](../../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/existing-repository.md)
  owns prepare -> consumer install/compile -> bind -> consumer checks.

Baseline limitations were explicit: there was no daily eligibility operation or
worker-identity contract, completed activity is removed from the live log during
rollover, and `finish.outcome` is free-form text. A recent record or arbitrary
outcome string cannot by itself establish successful automatic completion.

## Implementation decisions and invariants

### One coordination authority

Extend existing activity records and their strict codec; do not maintain a
parallel hook-owned state file. Keep starts and finishes paired during rollover
so existing active-run reconstruction remains valid. Preserve the latest pair
needed for automatic eligibility even after older history is archived. Identify
the canonical shared signal store, not a profile name or container path alias,
when coordinating multiple sessions/providers. The existing lock file and run
archives remain; this requirement forbids an additional duplicate state store.

Add a runtime-owned advisory eligibility operation and an automatic-start path
that rechecks eligibility under the same lifecycle lock as run creation. Exact
operation/field names are implementation details to expose through `describe`.
The worker can discover/snapshot inputs before this atomic start, but must not
edit owners, publish, drain or finalize a competing run before it wins. Manual
compounding remains available under its existing explicit workflow.

No pre-spawn reservation, lease expiry or exactly-one-spawn promise is required.
The owner accepts redundant subagents that promptly exit. Duplicate reminders
must not produce duplicate work even if one worker finishes between another
worker's advisory check and its start attempt.

### Due time and terminal outcomes

Proposed first-version default: a rolling 24-hour interval for the hook fallback.
Native local schedules retain their configured cadence and timezone. Document
this distinction; a calendar-day policy is not silently inferred from timezone.

Define a structured terminal classification for automatic eligibility rather
than parsing free-form prose. A fully dispositioned run can finish with retained
signals and a reported prerequisite; this does not mean those signals were
published or drained. Distinguish completed checks, failed attempts and
interrupted/active work. Define bounded retry behavior so a prerequisite failure
does not spawn a worker on every prompt. An empty inbox returns no work and must
not prevent newly arriving signals from being considered later.

Finalize these small state semantics in the first slice and synchronize the
request schema, `describe`, guide, examples and tests. Record attempts separately
from completion. Clock changes, corrupt records and interrupted writes must not
be treated as evidence that another run is permitted.

### Worker identity and recovery

Record the provider plus exact parent/session/subagent handles only when exposed
by that provider. Keep worker identity separate from signal-origin provenance
and compound run identity. Never fabricate IDs or assume one provider's IDs can
be used by another. Preserve attempt lineage if recovery uses a different worker.

Reuse an available worker through the provider's supported mechanism. If it is
unreachable, inspect the recorded run and publication/drain evidence before
recovery; elapsed time alone never authorizes taking over an active run. A
worker must recognize its own recorded run rather than treating it as foreign.
Delegated workers receive an explicit no-recursive-compounding instruction;
their native task begins with `[agent-knowledge-compound-worker]`. The prompt
adapter recognizes this explicit role marker and suppresses only conditional
delegation, retaining discovery/reflection. The marker grants no ownership,
readiness or authorization and replaces no atomic start check. Preserve the
original parent's handoff when child prompt hooks expose the worker's own
session handle. The active-run guard also protects against inherited prompts.
For the verified Copilot child-hook mapping, reassert the setup-bound runtime,
selector and installed skill directly to the marked worker and identify its
hook session as the native worker handle. Preserve the separately handed-off
parent identity and consumer/publication context; missing or conflicting
bindings remain explicit prerequisites. This context restoration neither
rechecks advisory due state nor grants ownership or permissions.
Use native harness subagent tools; a shell-launched model CLI is not a supported
substitute. Missing native delegation is a visible prerequisite.

### Hook transport and prompt latency

Use the verified provider prompt surfaces: Codex/Claude `UserPromptSubmit` and
Copilot's model-visible `userPromptTransformed` adapter, subject to current
version/trust verification. Preserve Copilot's incoming prompt content and one
appropriate context channel per provider. Event names are not portable policy.

Keep the conditional compounding capability distinct from unconditional
discovery/reflection. Reuse package/runtime/adapters where appropriate; do not
copy a private shell hook into each consumer. Failure of the due-check must not
suppress the existing reminders or block user work. The current lifecycle lock
is blocking and hook timeouts are short: provide a bounded/nonblocking busy path
for advisory checks, while the authoritative automatic start stays serialized.

The hook's inbox probe checks only for potential pending signal files within a
small metadata budget. It does not validate bodies or decide applicability. A
truncated probe is inconclusive; when otherwise due, a worker may discover that
candidate files are malformed, out of scope or leave no eligible work. That
occasional no-op worker is acceptable. Ambiguous coordination state, in contrast,
must never be treated as permission to start. Large inboxes cannot cause an
unbounded scan on every prompt.

The short injected message carries the exact selector, installed skill/runtime
location and delegation/recovery direction. Detailed procedures remain in the
skill. It performs no credential activation itself and does not claim to mutate
the parent harness environment. Provider permission/trust boundaries still apply.

### Setup, scheduling and container lifecycle

Setup determines capability for the actual local surface, not just provider name.
Codex desktop scheduling must not be assumed available to Codex CLI. Likewise,
session-scoped loops are not durable native schedules. Missing authentication is
a readiness problem, not proof that switching trigger mode will repair access.

Persist one selected trigger mode/owner through a minimal extension of existing
setup configuration. Equivalent aliases of a store must agree. Existing working
local schedules remain preferred; don't run an independent fallback alongside
them. Expose conflicts and preserve explicit disabled/manual-only choices.

For containers, the skill reads the existing Dockerfile/devcontainer conventions
and proposes narrow integration. Separate image-time Python/venv/pinned-package
installation from post-mount profile/APM/hook binding. Add an orthogonal helper
choice for verifying an existing runtime; do not redefine APM `bind`. In that
mode, verify Python, both launchers and intended runtime/package compatibility
without requiring `uv`, reinstalling Python or writing a generated launcher into
a root-owned venv. A shared version string alone is not package alignment proof.
The matching APM package or source supplies setup scripts; the runtime wheel
does not contain the setup skill.

Use existing PATH/registry/credential contracts. Mount writable knowledge state
and its lock files together on proven persistent storage; keep the consumer
checkout separately mounted if desired. Credentials stay external and private.
Preserve the user's startup commands, base image and tools. No Docker socket,
privileged container or host-side agent is required by this feature.

## Delivery slices

| Slice | Work and primary owners | Acceptance/proof |
| --- | --- | --- |
| S1 - State and eligibility | Domain request/record models, application coordination, infrastructure activity/rollover, CLI `describe` and installed guide. Define terminal outcomes, interval and recovery semantics. | AC2, AC10; concurrent/stale checks, rollover and failure tests. |
| S2 - Conditional hooks and workers | Provider adapters/runtime, package-owned hook declaration, compound-skill handoff and provenance. | AC1, AC4; all three provider fixtures, quiet paths, recursion and duplicate-worker tests. |
| S3 - Setup and local-only routing | Setup skill/helper and provider scheduling references; select one owner/mode, remove current cloud-compounding recommendations. | AC3, AC6, AC9; capability matrix, idempotent installation/binding/removal and current-doc audit. |
| S4 - Existing container/runtime integration | BYO-image setup reference and helper existing-runtime verification. Preserve native consumer tooling. | AC7, AC8; Debian/Alpine, nonroot immutable runtime, persistent storage and credential-path proof. |
| S5 - Consolidated proof and documentation | Native gates, packaging/fresh consumer, live fallback in each harness; README, support matrix and evidence report. | AC1-AC10; record exact candidate identities and unresolved proof. |

S1 precedes S2/S3; S4 can proceed independently after the helper contract is
settled. S5 tests the assembled feature. Keep commits reviewable by slice and
review state/concurrency, provider behavior, setup ownership and documentation
together before claiming completion.

## Validation and evidence

Deterministic coverage must include:

- Not due, disabled, local-schedule-owned, empty inbox, active run and missing
  prerequisites; ordinary prompts remain usable and existing reminders survive.
- Large inboxes and truncated metadata probes, malformed/out-of-scope candidates
  and a worker finding no eligible work; no body reads or false empty-inbox
  conclusion in the prompt hook.
- Interval crossing in an existing session; signals arriving after an empty
  check; simultaneous providers/profile aliases; a stale reminder after another
  run has already completed; only one automatic run performs edits/drain.
- Start/end pairing and retained last-completion metadata through rollover;
  interrupted writes, malformed state, clock movement and recovery without
  timeout-based takeover. Dispositions and edited/new signal protection remain.
- Worker IDs present/absent/unreachable, reuse and recovery lineage, recursion
  suppression, and a losing worker leaving the winning run unchanged.
- Install/rebind/reinstall/disable/remove, unrelated hook preservation, native
  catalog/lock integrity, selected-profile overrides and package alignment.
- Debian and Alpine environments as a nonroot user, image-built read-only venv,
  missing `uv` in existing-runtime mode, PATH/registry mistakes, real mounted
  filesystem exclusion, and persisted state after container recreation.

Run the repository gates for implementation: `uv run pytest -q`,
`uv run ruff check .`, `uv run ruff format --check src tests`, `uv run mypy`,
and `git diff --check`. Packaging/APM changes additionally require `uv build`
and the isolated fresh-consumer procedure in
[R8 proof](../../docs/r8-harness-proof.md).

Live fallback proof is required independently for Codex CLI, Claude Code and
Copilot CLI with fictional isolated knowledge. Each must show an ordinary prompt
causing delegation when due, skill/selector handoff, observed worker identity
availability, a recorded terminal result, and a later prompt producing no second
run. Save versions, commands, transcripts, candidate identities and measurements.
Do not silently substitute another provider/model or claim fixture proof as live
proof. Missing access or unsupported capabilities leave the criterion open.

Native scheduling tests remain paused by existing repository instructions.
This planning task does not lift that pause or register a job. Reuse valid
existing local-schedule evidence and deterministic setup tests; if new native
schedule execution is needed later, report that precise pending proof and the
existing pause. It does not remove the separate live prompt-fallback requirement.

On 2026-10-06 the unmodified baseline passed exploratory checks in
`python:3.12-slim` and `python:3.12-alpine` on Docker Desktop Linux/aarch64:
136 focused tests per image, five filesystem probes per image, and installed
hook fixtures for all three providers, running as UID/GID 1000. Local evidence
is `.cache/container-feasibility-2026-10-06/report.md`. This is not proof of the
new feature: no actual harness CLI, fresh APM install, persistent-volume restart
or new existing-runtime mode was exercised. Re-run affected proof on the final
candidate; do not count these exploratory results toward AC5/AC7/AC8 completion.

## Documentation and ownership audit

Update the owning `knowledge-setup` and `knowledge-compound` skills, relevant
references (`codex-scheduled.md`, `claude-scheduled.md`, `copilot-scheduled.md`,
`portable-hooks.md`, `existing-repository.md`, profile/publication references
where affected), package declarations, installed guide/schema examples,
README, fresh-consumer instructions and harness-support matrix. Search current
prose as well as executable references for cloud-compounding recommendations
and unconditional native-scheduler assumptions. Keep historical plans/evidence
truthful with pointers rather than rewriting past results.

The earlier hook plan's static discovery boundary continues to apply to
discovery/reflection. This plan introduces an explicit separate conditional
compounding capability; synchronize owning instructions/tests that would
otherwise incorrectly prohibit it. Generated harness files remain projections
and are never hand-edited. No changes to the user's current consumer checkouts
or automation are part of creating this plan.

## Current checkpoint

- Implementation branch: `nik/local-compounding-hooks`; baseline unchanged.
- S1-S5 complete. All ten acceptance criteria have evidence in
  `docs/local-compounding-proof.md`; failed intermediate attempts are preserved.
- One consolidated independent review, four reviewers, six findings fixed.
  Subsequent native-probe fixes received affected verification, not another review.
- Final full deterministic suite: 1,691 passed. Focused Copilot hooks: 53 passed;
  verifier/isolation regressions: 128 passed. Ruff, formatting, mypy, diff and
  wheel/source builds pass.
- Codex, Claude and Copilot native-worker plus same-session repeat checks pass.
  Copilot uses the same recorded model routing as the failed attempts. Its marked
  child hook now supplies the exact bound route and native ID; original parent
  and consumer/publication context remain the explicit parent handoff.
- Final Debian/Alpine proof passes with nonroot immutable runtime, no uv,
  network-disabled checks and persisted volume state after recreation. This is
  runtime/registration-fixture proof; actual authenticated harnesses ran on the
  host separately. Native scheduling tests remain paused.
- Ten final quiet-hook samples: median 152.2 ms, max 182.8 ms, reminders retained
  and activity unchanged. Runtime payload matches final container/live fixtures.
- Shared activity log remains the only trigger/attempt/completion authority.
  Hook checks are advisory; workers atomically recheck at automatic start.
- Prior ambient-profile lookups and cleaned readiness probes are documented;
  the live driver now pins its disposable registry against implicit fallback.
- No real consumer installation, existing automation, commit, remote publication
  or merge is changed. Local reviewable implementation and evidence are ready.
- Next action: owner handoff. No implementation or required proof remains open.
