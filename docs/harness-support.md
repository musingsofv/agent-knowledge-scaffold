# Harness support matrix

The scaffold supports Claude Code, Codex and GitHub Copilot through one
provider-neutral CLI and a small provider adapter layer. The core retrieval,
signal, receipt and compounding behavior is identical in every harness. APM
projection paths, lifecycle events, credential activation and scheduling are
provider-owned surfaces, so their support and proof differ.

This matrix describes the installed workflow: install/compile the package and
use `knowledge-setup` to verify the Python runtime and bind the package-owned
hook markers. Managed mode owns the entire flow. Existing repositories can use
`prepare`, their registered install/compile commands, then `bind` and repository
checks; see [integration](fresh-consumer.md#integrate-with-an-existing-repository).
Bind does not certify consumer instruction compilation. Default targets are all
three providers; an explicit consumer target restriction is supported. A raw
APM projection alone is not a completed binding.

## Status meanings

| Status | Meaning |
| --- | --- |
| **Live proven** | An authenticated provider model completed the behavior in a disposable consumer. |
| **Installed proof** | Fresh-install, provider-fixture and CLI tests prove the installed contract without relying on model judgment. |
| **Provider limited** | The repository supports the provider-owned surface, with the stated provider restriction or evidence gap. |
| **Unsupported** | The provider does not expose the required surface or the scaffold deliberately omits it. |

## Local harness matrix

| Capability | Claude Code | Codex | Copilot CLI |
| --- | --- | --- | --- |
| APM instructions and skills | **Installed proof.** Setup installs `CLAUDE.md`/rules and both skills under `.claude/skills`. | **Installed proof.** Setup installs `AGENTS.md` and both skills under `.agents/skills`. | **Installed proof.** Setup installs Copilot instructions and hooks; current Copilot discovers the shared `.agents/skills` copies. |
| First-run `knowledge-setup` | **Live proven.** Claude completed the fictional business onboarding flow and the deterministic helper proves repeat setup and recovery. | **Live proven.** A persisted Codex session proposed and confirmed a minimal catalog, ran the current setup helper, bound all three hooks, preserved repeat setup, authored and retrieved a business workflow, retained exact signal provenance and asked for clarification on conflicting scope evidence. | **Live proven.** Copilot proposed and confirmed a minimal catalog, configured all three targets, preserved repeat setup, authored and retrieved a business workflow, retained exact signal provenance and refused an unsupported scope expansion. |
| Core CLI (`describe`, `doctor`, `context`, `catalog`, `search`, `inspect`, `validate`) | **Live proven.** Claude used profile-selected retrieval and the installed navigation contract. | **Live proven.** Codex performed semantic catalog/search/inspect selection and an ordinary body read through the installed CLI. | **Live proven.** Copilot performed semantic catalog/search/inspect selection and an ordinary body read through the installed CLI. |
| Named knowledge profiles and overrides | **Live proven.** Selection, default changes, resume and direct-config isolation were exercised. | **Live proven.** Explicit selection survived a default change, with isolated receipts and signals. | **Live proven.** Explicit selection survived a default change, with isolated receipts and signals. |
| External profile environment in the local CLI | **Live proven.** `SessionStart` writes declared mappings through Claude's private environment channel. | **Live proven.** The setup-generated launcher starts Codex with the selected declared mappings. | **Live proven.** The setup-generated launcher supplies declared mappings to Bash tools and enables native redaction. |
| Session-start discovery reminder | **Live proven.** Native `SessionStart` context reached the model. | **Live proven.** A startup-only probe returned the exact hook-supplied thread handle. | **Live proven.** A startup-only probe returned the exact session handle supplied through `additionalContext`. |
| Resume or compaction rediscovery | **Live proven for resume; installed proof for other mapped lifecycle sources.** | **Installed proof.** Resume, clear and compact sources map to the rediscovery reminder. | **Provider limited.** Native `sessionStart(source=resume)` supplies the resume reminder. Copilot exposes `preCompact` only as notification and has no model-visible event after in-session compaction. Always-on discovery instructions remain, and the next user prompt receives the reflection reminder only. |
| Per-prompt reflection reminder | **Live proven.** `UserPromptSubmit` context reached the model with the session handle. | **Live proven.** A prompt-only probe returned the exact hook-supplied thread handle. | **Live proven.** Copilot 1.0.86 `userPromptTransformed` appended the reminder and exact session ID in both initial and resumed prompt-mode turns. |
| Exact provider and session provenance in reminder context | **Live session plus installed provider proof.** Claude copied the hook-supplied session ID into a signal; provider rendering is covered by the installed three-provider hook proof. | **Live proven.** Startup and prompt-only probes returned the normalized provider and actual Codex thread ID. | **Live proven.** The model copied `copilot` and the exact hook-supplied session ID into a signal and reused the session after resume. |
| `signal record` and session-filtered `signal list` | **Live proven.** Claude recorded, rediscovered and deduplicated a session-scoped observation. | **Live proven.** Codex recorded one session-scoped signal, rediscovered its body after resume and suppressed a duplicate. | **Live proven.** Copilot recorded one session-scoped signal, rediscovered its body after resume and suppressed a duplicate. |
| Retrieval receipts and `usage export` | **Live proven.** The final-pass flow generated and exported retrieval evidence. | **Live proven plus installed export proof.** Catalog/search/inspect receipts retained the exact profile and session; retention/export remain integration-tested. | **Live proven plus installed export proof.** Catalog/search/inspect receipts retained the exact profile and session, including a corrected invalid request; retention/export remain integration-tested. |
| Agent-led `knowledge-compound` | **Live proven.** A real one-shot agent followed the installed skill and completed guarded start, drain and finish. | **Live proven.** A real one-shot agent followed the installed skill and completed guarded start, drain and finish. | **Live proven.** A real one-shot agent followed the installed skill and completed guarded start, drain and finish. |
| Compound snapshots, archives and activity provenance | **Live proven plus installed guards.** | **Live proven plus installed guards.** | **Live proven plus installed guards.** |
| Native recurring compounding | **Provider limited.** Setup explains Claude's available recurring-task command, but registration and scheduled execution are not live-tested. | **Live proven.** A Codex desktop Scheduled task loaded the installed compound skill, processed one seeded signal, archived/drained it once with full provenance, and was then removed. Registration was performed through the Codex Scheduled surface rather than the repository helper. | **Provider limited.** CLI `/every` and `/after` are session-scoped, run only while that interactive session is open, and are not unattended daily automation. A live free-tier `/after` attempt reached the feature but failed schedule parsing because the routed model was unsupported. Use an authorized external scheduler invoking `copilot -p` or a cloud automation for durable work. |
| Remote publication of compounded knowledge | **Provider limited.** Local decisions and guarded drainage are proven; a real remote PR publication is not. | **Provider limited.** Local decisions and guarded drainage are proven; a real remote PR publication is not. | **Provider limited.** Local decisions and guarded drainage are proven; a real remote PR publication is not. |

## App and cloud boundaries

The table above covers the local CLIs. The same repository files can be visible
to desktop or cloud products, but those products do not expose identical local
process, hook, filesystem or credential surfaces.

| Surface | Support boundary |
| --- | --- |
| Claude Desktop | No separate desktop support claim is made. The proven target is Claude Code. |
| Codex desktop app | Instructions, skills and the CLI remain usable in a local project. There is no documented generic per-task arbitrary env-file injection, so use provider-native credentials or the explicit setup-reported CLI launcher. Desktop Scheduled registration and one real compounded run are live-proven. |
| Copilot app | Repository instructions are supported, but generic per-task env-file injection and the local CLI's Bash activation bridge are unavailable. Use the app's selected GitHub identity and provider-native credential surfaces. |
| Copilot cloud agent and cloud automations | Use repository or organization Agents secrets and variables. The local env-file launcher does not configure a cloud agent, and this repository has not live-tested cloud execution. |

## Setup readiness boundaries

Runtime/read, signal/receipt writes, hooks, profile credentials and automation
are reported separately. If knowledge reads are ready and only profile
environment diagnostics remain, setup can bind discovery/reflection hooks with
credentials pending. Doctor still reports those diagnostics and fails overall;
setup does not offer a credential loader command. `prepare` intentionally leaves
requested hooks pending. Populate the private env file, rerun `managed` or
`bind` for the same profile and perform repository checks before using the
reported new-session activation. The parser is unchanged and remains strict.

The staged/pending-credential extension has its own deterministic acceptance
coverage described in [R8 proof](r8-harness-proof.md#staged-setup-and-pending-credentials).
The existing live entries do not imply a new live model or scheduler
run for this extension.

## Known limitations

- The agent chooses queries, relevance, file ranges, graph expansion, signal
  usefulness and compounding owners. The deterministic tool validates and
  records those choices; it does not make them semantically deterministic.
- Search is a bounded local Markdown scan rather than an embedding index.
  Receipts record CLI filters, candidates, bytes and timing. They cannot observe
  ordinary editor or shell body reads, so `body_read` can remain `unknown`.
- Repeated `signal record` calls create distinct files. The reminder tells the
  agent to inspect same-session candidates before recording; the CLI does not
  silently deduplicate observations.
- One local harness session activates at most one credential profile. Changing
  `--profile` changes knowledge selection only; credential changes require setup
  for the target profile and a new session.
- Profile mappings are convenience routing, not an access-control boundary.
  Provider keychains and credential helpers remain active.
- Hooks are advisory and fail open. They remind the model to use the CLI but do
  not perform retrieval, judge signals or block edits.
- Codex project hooks remain subject to Codex's project-trust boundary. Setup
  can install the hook but cannot silently grant that trust.
- The Copilot launcher enables Copilot's Bash-environment preference. Copilot
  persists that value-free preference; the temporary activation file and
  credential values are not stored in its settings.
- Completion hooks are deliberately absent. All three CLIs receive reflection
  on prompts; Copilot's reminder uses `userPromptTransformed` and requires a
  trusted repository in prompt mode.
- Codex desktop scheduling is live-proven. Claude recurring-task registration,
  durable Copilot external/cloud scheduling, provider cloud agents and real
  remote PR publication remain outside the current live evidence.
- Live proof depends on authenticated provider access and current CLI behavior;
  provider upgrades can require adapter or command updates.

## Reproduce the evidence

The deterministic proof is safe to run without a model account:

```bash
uv run pytest -q
uv run python tests/e2e/fresh_consumer_smoke.py \
  --output .cache/fresh-consumer.json
```

The real-agent compounding proof creates separate disposable consumers and does
not create a scheduler, publish a PR, or modify a real signal inbox:

```bash
uv run python tests/e2e/harness_agent_smoke.py \
  --providers codex,claude,copilot \
  --live-agent --require-passed --keep --timeout 600 \
  --output .cache/harness-support-live.json
```

Live tests are evidence for the installed workflow they exercise, not proof of
every possible model decision. The deeper provider hook and onboarding flows, plus the Claude
final-pass flow, are documented in [R8 harness proof](r8-harness-proof.md).

Copilot lifecycle and scheduling boundaries were checked against GitHub's
current [hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)
and [scheduled prompts guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/schedule-prompts).

Last cross-provider verification: 2026-09-21 with Codex CLI 0.154.0, Claude
Code 2.1.236 and GitHub Copilot CLI 1.0.86. Copilot used automatic efficiency
routing. Codex Scheduled completed one real compounding run. Copilot's
session-local scheduler registration was attempted but blocked by the free-tier
routed model; no durable Copilot scheduling claim is made.
