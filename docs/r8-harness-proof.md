# R8 harness proof

R8 exercises the complete neutral retrieval and compounding contract in
disposable consumers. It has three layers: deterministic acceptance cases,
byte/line/latency measurements, and an opt-in provider one-shot run.

## Run the local acceptance and measurement layers

These commands do not need a provider account or a knowledge checkout:

```bash
uv run pytest tests/acceptance/test_retrieval_walkthrough.py -q
uv run python tests/e2e/retrieval_measurement.py --repeat 3 \
  --output .cache/r8-retrieval-measurement.json
```

The measurement report records UTF-8 bytes, physical lines, elapsed
milliseconds, returned previews, selected body ranges, misses and
irrelevant-body reads. It explicitly reports that tokens are not measured.
The runbook case searches for a warning, inspects its outline, and reads only
that section; it does not claim that a matching section is semantically
complete.

The fresh-consumer run also installs the package-owned discovery hook marker,
lets setup bind each provider registration to the verified venv's
`agent-knowledge-hook` launcher, and executes that installed launcher with
Codex, Claude and Copilot lifecycle fixtures. It checks startup and resume
reminders, prompt reflection for all three providers, exact session-ID
propagation, Copilot's `userPromptTransformed` output, session-filtered signal
listing, unrelated event no-ops, hand-authored hook preservation, package-only
uninstall and source-path reinstall. Setup also reconciles the dependency and
deployment hashes for the rewritten Copilot hook before proving uninstall:

```bash
uv run python tests/e2e/fresh_consumer_smoke.py \
  --output .cache/r8-fresh-consumer.json
```

The smoke defaults to a supported installed CPython, independently of the
interpreter running the script. To verify setup with a particular installed
CPython 3.11+ version, pass `--python`, for example:

```bash
uv run python tests/e2e/fresh_consumer_smoke.py --python 3.14 \
  --output .cache/r8-fresh-consumer-python314.json
```

It exposes that interpreter to the isolated consumer, checks that setup selects
it, and exercises environment reuse, CLI operations and all three provider hook
fixtures. It does not download a Python interpreter. CI runs the core and this
installation proof on Python 3.11, 3.12, 3.13 and 3.14; live model proof remains
separate.

Local verification on 2026-09-25 passed fresh setup, reuse, CLI operations and
all three provider hook fixtures with CPython 3.11.8, 3.12.12, 3.13.12 and
3.14.6. The default launcher also passed when started by the system Python,
selecting a supported installed interpreter for the consumer.
The initial version-matrix run exposed a macOS receipt-lock creation race on
3.13, previously observed on 3.11: concurrent directory-relative opens with
`O_CREAT` could fail with `ENOENT` before acquiring the lock. The follow-up fix
creates the lock exclusively and opens it without creation when another writer
has already created it. No-follow access, inode checks, hardlink rejection and
serialization remain in place.

After the fix, all 1,388 tests passed on each of 3.11, 3.12, 3.13 and 3.14.
The new fresh-lock contention regression reproduced the failure before the fix
and passed afterward. Additional macOS stress checks on 3.11 and 3.13 each
passed 100 fresh-lock batches with eight threads and another 100 with eight
separate processes, preserving all 3,200 receipts across both versions. The
compounding concurrency test now requires the losing caller to receive
`compound-active`; it no longer accepts a lock-acquisition failure. Ruff,
formatting and mypy checks passed.

Remote APM binding was verified on 2026-09-25 against a real APM 0.29.0 install
of `musingsofv/agent-knowledge-scaffold/packages/knowledge-agent-pack#main` in
a disposable consumer. The updated setup helper bound Codex, Claude and
Copilot, preserved the portable manifest, reconciled Copilot hashes and remained
unchanged on repeat bind. Installed provider fixtures passed for all three;
APM uninstall removed the package hooks while preserving unrelated hooks.
This is installation and provider-fixture proof, not a new live-model run.

The full suite passed 1,399 tests after the remote-binding fix. Regression
coverage includes remote standalone/subdirectory packages, canonical versus
materialized repository casing, transitive local packages, ignored source
copies, ambiguous bundles, malformed/escaping lock records, and wrapped YAML
paths containing spaces. Dependency YAML is parsed by the verified runtime,
so the bootstrap interpreter needs no additional packages. The existing local
fresh-consumer proof also passed on Python 3.13, including prepare/bind,
reinstallation and all three provider fixtures. Build, Ruff and mypy passed.

For a prepared consumer, the provider-only fixture driver is:

```bash
python3 tests/e2e/provider_hook_smoke.py \
  --consumer /absolute/path/to/consumer \
  --launcher /absolute/path/to/consumer/.agent-knowledge-venv/bin/agent-knowledge-hook \
  --output .cache/r8-provider-hooks.json
```

It invokes the explicit launcher supplied by setup. It is dependency-free and
does not call a model, read knowledge or write a receipt. The hook itself
remains advisory and fail-open.

## Prepare a fresh provider consumer

The harness driver builds the same isolated wheel/APM consumer used by the
fresh-consumer proof. It creates a pending Markdown signal, discovers the
installed `knowledge-compound` skill, and prints the exact provider command
with the explicit launcher and configuration path. No model call is made by
default:

```bash
uv run python tests/e2e/harness_agent_smoke.py \
  --providers codex,claude,copilot \
  --output .cache/r8-harness-ready.json
```

Each provider gets a separate disposable consumer. The report status is
`ready` when all requested providers are prepared and `not-run` entries are
shown. Use `--keep` to retain the consumer and redacted logs for inspection.

The corresponding first-run `knowledge-setup` interaction is intentionally
small: it establishes the workspace configuration location and meaningful
business scopes. It reuses registered IDs or proposes a small catalog from the
business context for confirmation. It derives the workspace ID, source/catalog defaults,
producer root, `ai/signals`, `<scaffold>/.agent-knowledge-venv`, all three APM
targets and the daily local-time cadence. Current setup defaults to an explicit
GitHub PR route derived from the canonical knowledge checkout's verified remote
and default branch, included in the setup proposal. Missing destination/access is
pending; explicit local-only choices remain supported. The disposable proofs
below deliberately omit remote publication and do not prove PR creation.
Unavailable or unauthenticated providers are reported without asking for a
different target list.

## Run a real one-shot agent

Only run this when the provider accounts are authenticated and a disposable
model request is acceptable:

```bash
uv run python tests/e2e/harness_agent_smoke.py \
  --providers codex,claude,copilot \
  --live-agent --require-passed --keep --timeout 600 \
  --output .cache/r8-harness-live.json
```

The prompt tells the agent to read the installed skill and compiled discovery
instruction, use the installed launcher with `--config`, start a compound run,
record harness/session/automation provenance, use a `keep` no-write
disposition, perform the guarded drain and finish the run. The verifier then
checks an inactive activity log, matching provenance and a drained disposable
signal. It never publishes a PR, edits canonical knowledge or touches a real
inbox.

Provider outcomes are kept separate:

- `passed` means the agent performed the complete disposable workflow.
- `auth-required`, `usage-limited`, `unavailable`, `timeout` and `failed` are
  explicit blockers; they are not converted into a pass.
- `--require-passed` turns any non-passed provider outcome into a failing exit
  code for an authenticated gate.

The command is a provider-native non-interactive/one-shot invocation, which is
the reproducible equivalent of a durable provider task's **run now** control.
The repository does not implement a scheduler or mutate provider account state.
`knowledge-setup` reports scheduling separately per provider. Codex Scheduled
is a durable native surface. Copilot CLI `/every` and `/after` remain attached
to an open interactive session, so unattended Copilot compounding needs an
explicitly authorized external scheduler invoking `copilot -p` or a cloud
automation.

The 2026-09-21 cross-provider run passed with Codex CLI 0.154.0, Claude Code
2.1.236 and GitHub Copilot CLI 1.0.86. Each authenticated agent read the
installed `knowledge-compound` skill, completed guarded start/drain/finish in a
separate disposable consumer, preserved its harness/session/automation
provenance, and left the run inactive with the selected signal archived and
drained. Copilot used `--model auto --auto-tier efficiency`. Separate narrow
Codex and Copilot startup probes returned their exact hook-supplied session
handles; prompt reflection is live-proven for Codex and Copilot. A separate
Codex desktop Scheduled task subsequently processed a seeded signal through the
installed compound skill and was removed after the successful run. Remote
publication remained excluded. See the
[harness support matrix](harness-support.md) for the feature-level proof and
remaining limits.

## Native scheduling evidence

On 2026-09-21 a disposable Codex desktop Scheduled task named
`agent-knowledge-compound:workspace:fresh-consumer:codex-schedule-proof`
launched a real task, loaded the installed `knowledge-compound` skill and
processed seeded signal `r8-codex-observation`. Run
`compound-f50aa8a557dc420d154acf78ca465c38` retained harness, session and
automation provenance, archived the input, recorded `no_update`, drained it
exactly once and left the inbox empty. The automation was deleted immediately
and its proof task archived. This proves Codex Scheduled registration and
execution through the desktop surface; it does not claim that
`setup_runtime.py` itself registers account tasks.

Copilot CLI 1.0.86 recognizes experimental `/every` and `/after`, but those
schedules are scoped to the open interactive session. A live free-tier
`/after 5s` attempt reached schedule parsing and returned HTTP 400 because the
automatically routed `mai-code-1.1-flash` model was unsupported for parsing;
the account did not expose the explicit alternative models tried. No Copilot
schedule was created. Even on an eligible model, `/every` runs only while the
session is open, resumes its next wait from reopen and does not catch up missed
recurring runs. Durable unattended Copilot compounding therefore needs an
explicitly authorized external scheduler invoking `copilot -p` or a Copilot
cloud automation.

## Live Claude discovery-hook acceptance

The live provider proof is opt-in because it consumes an authenticated model
request. It uses a prepared disposable consumer, the project/local settings
only, a temporary `CLAUDE_CONFIG_DIR`, `--model opus`, and the exact resolved
`claude-opus-5` model. The driver captures only redacted event summaries and
deletes the temporary configuration after the run:

```bash
python3 tests/e2e/claude_hook_acceptance.py \
  --consumer /absolute/path/to/consumer \
  --hook-launcher /absolute/path/to/consumer/.agent-knowledge-venv/bin/agent-knowledge-hook \
  --require-passed \
  --output .cache/r8-claude-hook.json
```

The explicit launcher must be the consumer-local path that setup reported. The
driver checks both the package sidecar and the active `.claude/settings.json`:
each must have one exact absolute managed command for `SessionStart` and
`UserPromptSubmit`, with no bare `agent-knowledge-hook` marker.

The report separates transport from model flow. It proves startup and native
resume lifecycle delivery plus one model-visible context for each lifecycle and
prompt event through `hookSpecificOutput.additionalContext`, with the same
session ID in each context. The first bounded turn receives that ID only from
hook context, uses the installed CLI and explicit configuration to make an
inline, session-filtered `signal list` request, then records the fixed
fictional fixture observation and returns `MODEL_RECORD_OK`. The resume turn
lists the same session, reads the returned candidate body, makes an independent
duplicate decision, and returns `MODEL_DEDUP_OK`. An installed-CLI verifier
then proves that exactly one Claude-origin signal retained the hook session ID.
If the model flow fails after hook transport succeeds, the report retains the
captured transport evidence instead of claiming an end-to-end pass.

Each model turn has a `$1.0` maximum budget. The driver constructs a minimal
`PATH` containing the consumer runtime, Claude, Node, Git and system tools,
while retaining the existing provider authentication environment. An absent
CLI or authentication is reported as `unavailable`/`auth-required`;
`--require-passed` turns that status into a failing acceptance exit. When the
account is authenticated through Claude's default keychain, add
`--use-global-auth` to opt into that account explicitly; the driver still loads
only the consumer's project/local settings and reports that global
authentication was used. The default command does not use `--bare`, the user's
global Claude settings or its session directory.

## Provider prerequisites

The driver uses the installed command versions and provider-owned credentials:

```bash
codex --version
claude --version
copilot --version
```

Codex is invoked with an ephemeral disposable session and an explicitly
bounded temporary workspace. Claude uses print mode without session
persistence; Copilot uses prompt mode with automatic updates disabled. The
driver retains credentials only in each provider's own account/configuration
state and redacts token-shaped values from retained logs.

For the optional live Copilot probe, prefer `--model auto --auto-tier
efficiency` unless the developer requests another model. Record the model that
auto routing actually selects. Do not hard-code an internal model alias merely
because it appears in an auto-routing event; the account may reject that alias
when passed directly.

## Final-pass harness checks

The final-pass onboarding driver exercises business setup in a fresh consumer:

```bash
uv build --out-dir .cache/dist
uv run python tests/e2e/setup_onboarding_acceptance.py \
  --wheel .cache/dist/agent_knowledge_scaffold-0.1.0-py3-none-any.whl \
  --provider claude --live-agent --keep \
  --output .cache/onboarding-claude.json
uv run python tests/e2e/setup_onboarding_acceptance.py \
  --wheel .cache/dist/agent_knowledge_scaffold-0.1.0-py3-none-any.whl \
  --provider codex --live-agent --keep \
  --output .cache/onboarding-codex.json
uv run python tests/e2e/setup_onboarding_acceptance.py \
  --wheel .cache/dist/agent_knowledge_scaffold-0.1.0-py3-none-any.whl \
  --provider copilot --live-agent --keep --max-ai-credits 30 \
  --output .cache/onboarding-copilot.json
```

Each invocation creates a separate disposable APM consumer with no organization
catalog, supplies a fictional business brief, confirms the model's proposal,
checks repeat setup, captures/compounds a marketing signal and presents
conflicting business notes. The report separates deterministic checks from
semantic review of the proposal and authored workflow. Claude retains its Opus
5, project/local-settings and per-turn $4 limit. Codex starts one persisted
`codex exec --json` thread and resumes that exact emitted thread ID for the
remaining phases; it deliberately does not use `--ephemeral`. Copilot chooses
one UUID, resumes it across phases, uses automatic efficiency routing, disables
automatic updates, remote/export surfaces and the built-in MCP, and defaults to
the provider's minimum 30-credit session cap. Its disposable `COPILOT_HOME`
trusts only the consumer so prompt-mode repository hooks load without changing
the user's settings. Every provider defaults to a
600-second process timeout. Without `--live-agent`, the selected invocation
prepares the installation without calling a model. Native scheduling remains
excluded.

The remaining B3-B5 scenario uses a separate disposable business workspace:

```bash
uv run python tests/e2e/final_pass_acceptance.py \
  --wheel .cache/dist/agent_knowledge_scaffold-0.1.0-py3-none-any.whl \
  --live-agent --keep --max-budget-usd 4 \
  --output .cache/final-pass-acceptance.json
```

It checks incoming-link discovery and rename maintenance, skill-reference
ownership, a trial followed by confirmed business adoption, and retrieval of
current instructions versus historical rationale. It verifies tool-written
receipts, exact archived signal bytes and the checksums of a local usage export.
Publication is deliberately disabled in this fixture: unpublished changes retain their signals, while
an already-covered observation can be drained with its archived input intact.
No native scheduler or remote publication is exercised.

Both drivers accept `--resume-report /absolute/path/to/report.json` for supported
preserved sessions. Resume verifies the prior evidence and keeps failed attempts
in the report; it does not make a failed provider turn a successful one. Keep the
consumer and original logs available, use the same wheel and write a new output
report. See the current [final-pass plan](../ai/plans/knowledge-final-pass.md) for
observed results and remaining proof limits.

The incoming-scan measurement and source-instruction ownership checks do not
call a model:

```bash
uv run python tests/e2e/incoming_measurement.py \
  --output .cache/incoming-measurement.json
uv run python tests/e2e/instruction_ownership_smoke.py \
  --output .cache/instruction-ownership.json
```

## Evidence interpretation

The acceptance fixture is intentionally neutral and fictional. It proves
selection algebra, progressive navigation, catalog validation and guarded
compounding behavior. The measurement is a repeatable baseline for this
fixture; it is not a tribe-scale performance claim. A real organization can
run the same scripts against its own explicitly configured workspace after
validating that its files use `knowledge.v1` and that the source is safe to
inspect.

## Named-profile acceptance

Build the entire profile plan before running a real model. The fresh-consumer
check above now verifies profile-selected setup and effective receipt overrides,
including repeated setup/reinstall and all three provider hook fixtures. Keep
its consumer for the profile scenario:

```bash
uv run python tests/e2e/fresh_consumer_smoke.py --keep \
  --output .cache/profiles-fresh-consumer.json
uv run python tests/e2e/profile_acceptance.py \
  --consumer /absolute/consumer_root/from/that/report \
  --live-agent --output .cache/profiles-claude.json
```

The second script uses the installed wheel and registry helper, two isolated
fictional sources/inboxes and an explicit registry. Without `--live-agent`, it
prepares the fixture and verifies installed CLI behavior without a model call.
Each run needs a fresh consumer. Select `--provider claude`, `codex` or
`copilot`. The provider discovers and reads the selected release-window body,
uses the exact hook session handle for signal capture, and resumes to inspect
its pending note without duplication after the global default changes. Logs
stay inside the disposable consumer. Claude uses its bounded Opus flow; Codex
and Copilot use their provider-native persisted session forms and explicit
bounds. Semantic retrieval/profile proof is live for all three providers.
Scheduling is a separate acceptance surface.

## Profile-environment acceptance

Run this only after the complete profile-environment slice is built. Use two
temporary mode-`0600` dotenv files with different disposable canaries and two
profile declarations. Do not use real credentials.

The deterministic proof must establish:

- `profiles list` opens neither env file and shows only paths/names/mappings;
- selected `context` and `doctor` report availability/readiness without values;
- direct `--config` reports no profile environment;
- generated provider launchers contain only paths and names, and child-process
  positive controls receive exactly the selected mapped target;
- the reported Copilot command contains no provider flags; its launcher injects
  setup-owned `--bash-env=on` plus native redaction and rejects caller overrides;
  and
  its private mode-`0600`, wrapper-lifetime `BASH_ENV` file restores the declared
  target only inside Bash tools. The Copilot parent receives a protected
  internal redaction alias while any existing declared target such as
  `GH_TOKEN` remains unchanged; the
  file is removed on ordinary wrapper exit and abrupt-termination residue is treated
  as an explicit limitation;
- Claude `SessionStart` appends only the selected shell-quoted exports to its
  private provider-owned `CLAUDE_ENV_FILE`; hook output and prompt, Codex and
  Copilot hooks do not expose or copy values;
- a resumed Claude session retains its original value-free declaration pin
  after setup binds a different registry/profile for new sessions;
- changing the knowledge `--profile` in a started process does not change its
  environment; a new process/session with the other launcher does;
- both canaries are absent from stdout, stderr, setup JSON, hook JSON, launcher
  files, receipts, descriptors and usage exports.

The temporary `CLAUDE_ENV_FILE` is the intentional narrow exception to the
value-at-rest scan because Claude's native contract requires exports there;
delete it immediately after the positive control. Then run one live CLI session
for Claude, Codex and Copilot through each setup-reported activation surface and
have a Bash tool report only a boolean presence check for the disposable mapped
target. Do not ask the model to print the canary. Scan stdout, stderr and saved
transcripts for both disposable values. Codex/Copilot desktop credential
injection remains a capability assertion because neither app exposes a
supported generic per-session env-file surface. This proof does not authorize
additional scheduler registration or execution.

## Staged setup and pending credentials

Run the setup integration cases without a model account:

```bash
uv run pytest tests/integration/apm/test_setup_runtime.py -q
```

The setup integration extension has two additional deterministic proof surfaces:

- Repository-owned APM: `prepare` verifies a real installed runtime without
  looking up APM or changing consumer configuration. A repository-controlled
  install/compile stage preserves local skills and owned instruction generation.
  `bind` runs no APM command, binds only installed package resources and updates
  owned Copilot lock hashes. Checks after bind verify the resulting consumer,
  repeat binding, missing-package failure and unrelated-hook preservation.
- Pending credentials: a profile with blank private assignments keeps its
  environment diagnostics and failing overall doctor status while runtime/read
  and reminder-hook binding succeed. No activation command is returned. Filling
  disposable values privately and rerunning the same binding mode activates the
  declared mappings. Invalid knowledge, source, runtime and receipt conditions
  must still fail independently of environment readiness.

The installed fresh-consumer runner above also exercises this sequence: remove
the package, prepare with blank credentials, run repository-owned install and
compile, bind and execute all three provider reminder fixtures, then fill the
env file and repeat bind. Its `staged_integration` report records those results
and byte-preservation of the manifest, local skill and compiled instructions.
The integration tests additionally cover missing env files, missing declared
variables, unsafe permissions, and failures of knowledge/receipt storage.

These deterministic checks passed on 2026-09-23 with CPython 3.11 and APM 0.29.0.
This evidence is separate from the historical live provider runs above; it does
not claim a new real-model onboarding or native scheduling result. Use
disposable consumers and env canaries only, never a user's active consumer,
signal inbox or real credentials.
