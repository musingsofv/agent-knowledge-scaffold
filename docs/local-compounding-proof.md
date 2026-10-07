# Local compounding and container verification

The implementation contract is
[the local compounding plan](../ai/plans/local-compounding-hooks-and-container-setup.md).
Proof uses fictional, isolated consumers. Existing consumer configuration,
credentials, automations and pending signals are outside this change.

## Reproduce

Run the repository's deterministic gates, then build the installed artifact:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run mypy
git diff --check
uv build
uv run python tests/e2e/fresh_consumer_smoke.py --keep \
  --output .cache/local-compounding/fresh-consumer.json
```

The local prompt driver prepares a separate installed APM consumer per provider.
Without `--live-agent`, it performs preparation without a model call. With that
flag, it submits an ordinary file task, observes native subagent delegation and
the automatic compound lifecycle, resumes the same session, and verifies that
the second prompt starts no additional run. Reports preserve exact available
session/worker handles, commands, redacted transcripts and fixture locations.

```sh
uv run python tests/e2e/local_compounding_acceptance.py --provider codex \
  --live-agent --output .cache/local-compounding/codex-live.json
uv run python tests/e2e/local_compounding_acceptance.py --provider claude \
  --live-agent --output .cache/local-compounding/claude-live.json
uv run python tests/e2e/local_compounding_acceptance.py --provider copilot \
  --live-agent --output .cache/local-compounding/copilot-live.json
```

Provider authentication, project trust and subagent availability are independent
prerequisites. A failed or unavailable real provider is missing live proof, even
when all installed adapter fixtures pass. The driver never publishes or registers
a native scheduler. Native scheduling execution remains outside this proof.

Container verification is a disposable test harness, not a required product image.
It builds the runtime independently of consumer mounts, checks existing-runtime
binding as a nonroot user without `uv`, verifies the immutable runtime and actual
filesystem locks, then recreates the container against the same Linux volume.
See the driver's `--help` and the
[bring-your-own container guide](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/containers.md).

## Current result

Verification date: 2026-10-06. The source baseline is
`c2e6d875a68d165e3d94870c5040980625ac9451`; candidate files and hashes are recorded
in `.cache/local-compounding/candidate-final.json`. Evidence paths below are
relative to the implementation checkout; disposable provider locations and exact
opaque identities are retained in their JSON reports.

The final assembled deterministic suite passed 1,691 tests in 74.75 seconds.
Focused Copilot hook checks passed 53 tests and verifier/isolation checks passed
128 tests. Ruff, formatting, mypy, whitespace checks and wheel/source builds
passed. The live drivers run the full isolated fresh-consumer APM installation,
compile, staged setup and binding checks before calling a model.

Final evidence:

- `.cache/local-compounding/pytest-copilot-bound-worker.txt`
- `.cache/local-compounding/copilot-bound-worker-hooks.txt`
- `.cache/local-compounding/copilot-bound-worker-fix.json`
- `.cache/local-compounding/build-copilot-bound-worker.txt`
- `.cache/container-runtime-proof-2026-10-06-copilot-bound/report.json`

An earlier full-suite run overlapped edits to the verifier fixtures and reported
19 failures with 1,635 passes. Its output remains in
`.cache/local-compounding/pytest-native-final.txt`; the fresh full-suite result
above supersedes it. Failed live attempts are also preserved independently of
later fixes and successful proof.

### Container proof

Debian (`python:3.12-slim`, Python 3.12.13) and Alpine
(`python:3.12-alpine`, Python 3.12.15) passed under UID/GID 1000. The runtime was
root-owned, unwritable and byte-for-byte unchanged; `uv` was absent and checks
ran without network access. Each image was removed/recreated against the same
Linux-backed persistent volume. The activity digest stayed identical, and all
five filesystem guards passed before and after recreation: lock exclusion,
concurrent receipts, guarded reads, private environment permissions and unsafe
environment rejection. Disposable containers, images and volumes were cleaned.

This is installed-runtime and provider-registration fixture proof. Actual APM
installation and live provider runs are separately exercised on the host. No
claim is made that an authenticated harness was run inside these images, that
arbitrary images are supported, or that every host bind mount has equivalent
locking semantics. Run the mount probe in the developer's actual environment.
The final container and live-probe runtime payloads match. The tested wheel is
`e4037e00564962e833a8440d1d3a1f7ca12002cc45acc67dd926c36925dd1bbd`;
its installed payload fingerprint is
`8b8d59cfc8f97b358b40e72975c1e0c7ffde22e621ecaa967ee96117a904ee74`.

### Prompt overhead

Ten final installed Copilot prompt-adapter subprocess measurements on a recent-run
quiet path had a median of 152.2 ms and a maximum of 182.8 ms. Each retained the
original prompt and reflection, emitted no compounding text or stderr, and left
the activity digest unchanged. Session-start discovery/reflection also remained
intact. Evidence and the exact reproducible command are in
`.cache/local-compounding/hook-overhead-copilot-bound.json` and
`measure-hook-overhead-copilot-bound.py` in the same directory. These are local
subprocess timings, not model latency or a worst-case storage guarantee. The
separate metadata subprocess has a one-second timeout; timeout and busy-lock
behavior have deterministic coverage. Earlier timings remain saved separately.

### Consolidated review and fixes

One consolidated round used four independent read-only reviewers covering
state/concurrency, hook transport/proof, setup/runtime and semantic guidance.
They compared original sources and replacements against the accepted plan.
No weakening of ownership, publication, human review/merge, changed-input
protection or guarded drainage was found. Six findings were corrected:

1. Preserve Claude's established credential-pin directory across rebind.
2. Verify both launchers actually execute the selected venv, including shell
   trampolines and relocated environments.
3. Keep optional compounding failures separate from valid reminder-hook binding.
4. Activate the trigger explicitly only after final consumer checks.
5. Compare the installed compound skill and its resources with the owning
   package, rather than checking only that a skill file exists.
6. Require native identity and actual child execution evidence in live proof.

Additional live verification found that some providers expose worker handles
only to the parent, and that an inherited prompt hook can be mistaken for a new
delegation instruction. `record-worker` now associates the exact late handle
without changing lifecycle state, and the hook identifies an already delegated
worker before giving main-agent instructions. A conflicting identity is still
rejected. These fixes received affected verification, not a second review round.

### Live prompt fallback

A successful ordinary turn alone is insufficient: proof correlates the native
worker, installed skill read, selected start/finish and repeat-prompt suppression.
Shell-launched model workers are rejected by the observable-command verifier.
The outer CLI processes belong to the test driver and supply actual harness
sessions; the compounding workers must use native subagent tools.

Claude Code 2.1.236 passed both turns using `claude-opus-5`. Its parent session
was `696ef63e-a2af-4f9c-bdd9-a49f4677061a`, native worker
`af1a67d08925897d8`, and run `compound-1fae603eccaf83dc2d368a4311728fbd`.
The report `.cache/local-compounding/claude-live-native.json` correlates the
native Agent call, returned worker handle, child tool events, installed skill
read and successful automatic start/finish. The repeat prompt produced no
second worker or run, and the disposable input was guardedly drained.

Codex CLI 0.160.1 completed the native run in session
`01a111cc-0a58-7ef2-b791-60cbad9b71ac`, worker `/root/compound`, child session
`01a111cc-71ba-7880-b776-481ebfca14e3`, run
`compound-7e05bafd8a8a8c7d0a74644777765f89`. Its original driver report rejected
valid relative launcher/settings paths. The corrected verifier resolves only
the child's recorded working directory and `$PWD`/`${PWD}`, retains exact-path
checks, and passes on the saved native trace in
`.cache/local-compounding/codex-native-offline-verification.json`. Codex's public
stream omits child events, so proof uses parent/child native rollout snapshots
and post-fork tool calls. The encrypted native handoff is not decrypted; the
marker text itself is not observable there. Actual child skill and selector
execution is observable. The exact same session's repeat prompt passed with no
new native spawns, unchanged activity and terminal identity, a complete empty
inbox and `due:false`. Combined evidence is
`.cache/local-compounding/codex-live-native-with-repeat.json`.

Copilot CLI 1.0.86 passed both turns with `auto` at its efficiency tier, routed
to the same `mai-code-1.1-flash` model used by the failed probes. The final report
is `.cache/local-compounding/copilot-live-bound-worker.json`. Parent session:
`fc7a8c71-6664-4d83-b387-a66fb2af44b2`; native worker and child session:
`0dc0d1b6-2777-4702-b0a9-5baf46ea53f2`; run:
`compound-4188d8ba4b6a8b0e31b8b5ef104171c9`.

The report correlates the native task dispatch, native child event, exact marked
child prompt, installed skill read and selected successful start/finish. Both
the parent handoff and the actual child's setup-bound context carried the exact
selector. The hook supplied the native worker ID directly, and the child saved
it with its own session ID and the separate original parent ID on automatic
start. Reflection was retained and recursive due context suppressed. The signal
was guardedly drained, the same-session repeat launched no worker or run, and
`due_after` was false. No driver identity backfill or model substitution was used.

Earlier Copilot probes exposed recursive delegation, ignored delegation, and
then omitted native worker ID/selector handoff. Their reports remain preserved,
including `copilot-live-task.json` and `copilot-live-worker-id-with-repeat.json`.
They remain failed/partial, rather than being reclassified by the later pass.
The targeted correction reasserts the setup-bound runtime, selector, installed
skill and verified native child ID inside the marked Copilot worker hook. It
performs no new due check, compounding action or credential activation. Original
parent identity and consumer/publication context still come from the parent.
Missing/conflicting context remains a prerequisite, with no default-profile
substitution. The verifier accepts actual bound child context as effective
handoff while still rejecting conflicting parent routes, wrong IDs, missing
child execution and recursive or shell-spawned workers.

A prior failed probe also queried the real registry after losing its selector.
Those calls read context/status/inbox metadata and ran a write-mode doctor that
created and removed two readiness probes; both cleanup results passed. The
transcript shows no real start, drain or publication. Doctor read declared
credential readiness internally without printing or editing values. The driver
now pins `AGENT_KNOWLEDGE_SETTINGS` to the disposable registry; missing selectors
and unrelated profiles fail there. This prevents implicit profile fallback,
not deliberate access to an explicitly supplied outside path. The audit and
regressions are saved in `copilot-bound-worker-fix.json`.

These are observed behavior proofs for the recorded provider/model versions,
not a guarantee of every future model response. Atomic start, changed-input
protection and guarded drainage retain independent deterministic coverage.

Native scheduling execution remains paused and was not run.

## Acceptance summary

All ten criteria have the required implementation and verification evidence.
AC1/AC5 now include actual native-worker and same-session repeat proof for all
three providers. The Copilot-specific correction leaves Codex/Claude rendering
unchanged, so their prior native evidence is retained alongside final shared
regressions. Native schedule execution and authenticated model sessions inside
Docker remain separately unperformed; neither is represented by the container
fixtures. All six findings from the single consolidated review were fixed, and
the subsequent Copilot handoff/provenance gap is resolved by the targeted check.
No additional review round was commissioned.

The local `.cache/local-compounding/transcripts/` directory holds redacted
copies of direct probe logs and native proof snapshots. `transcript-manifest.json`
records their source paths and checksums. Provider authentication directories
are excluded. That candidate was subsequently preserved as commit `f0186a1` on the same
implementation branch. Its [container-launch follow-up](container-launch-proof.md)
adds separate setup/launch proof. No consumer install, automation change or
remote publication was made by either implementation task.
