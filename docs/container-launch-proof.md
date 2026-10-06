# Existing-container setup and launch proof

Implementation contract: [container setup and launch readiness](../ai/plans/container-setup-and-launch-readiness.md).
This extends the [local-compounding candidate](local-compounding-proof.md) on the
same branch. The previous feature is preserved in `f0186a1`; implementation slices
are `e8859ce` (preflight), `67af72a` (private profile preparation), `ddf33fe`
(owned setup and checked launches), `62ef1ed` (review fixes) and `27cd6e9`
(acceptance driver and failure evidence). The subsequent authorized Docker
retest proves Codex tool execution, retrieval, writes and credential activation;
native container acceptance is still partial for the limits below. No consumer installation
or publication is part of this work.

## Developer-facing change

The existing `knowledge-setup` skill now checks tool and harness execution
locations separately, derives container-local paths, prepares the selected
profile and supplies a checked launch recipe. It preserves the developer's image,
user, tools, sandbox and repository-owned APM workflow. Distributed resources do
not include an image, Dockerfile or devcontainer definition.

An installed `preflight` command checks runtime, paths, selected configuration,
credential-file readiness and registration availability without installation,
network, model calls or routine writes. Native hook delivery, credential
activation and effective sandbox access remain separate acceptance results.

The profile helper guards explicitly selected private projections, registry
updates, refresh and removal. Blank values remain pending. Values and credential
digests are absent from its reports and provenance. Removal is possible without
an available knowledge mount and never certifies a replacement launch route.
The launch helper retains argument boundaries and runs the generated provider
activation route with the selected runtime and registry.

## Reproduce

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run mypy
git diff --check
uv build
uv run python tests/e2e/fresh_consumer_smoke.py \
  --output .cache/container-launch-proof/fresh-consumer-final.json
uv run python tests/e2e/container_runtime_smoke.py \
  --output .cache/container-runtime-final
uv run python tests/e2e/container_launch_acceptance.py \
  --output .cache/container-launch/acceptance-new --live-agent \
  --docker-seccomp-profile .cache/container-launch-proof/docker-codex-seccomp.json \
  --auth-env codex:OPENAI_API_KEY --timeout 180 --keep
```

The last command uses an explicitly selected provider-authentication variable;
it is not a requirement to copy credentials into the image. Other supported
routes are `codex:CODEX_API_KEY`, `claude:ANTHROPIC_API_KEY`,
`claude:CLAUDE_CODE_OAUTH_TOKEN` and
`copilot:COPILOT_GITHUB_TOKEN`. Missing routes remain pending. Pass names only;
never put values in flags, build contexts or saved reports. Real profile/service
credentials are not mounted. The fixture uses a synthetic tool credential.

The driver builds an isolated nonroot Debian/Node fixture, installs the matching
wheel and APM package, runs prepare/install/compile/bind, then invokes the actual
setup-generated launcher. It attempts fresh, reused and recreated-container
sessions, requires correlated native shell execution and exact session IDs,
checks retrieval receipts, and records/drains its fictional signal through the
supported CLI. It exports evidence before cleanup on failures. `--keep` retains
only the named disposable fixture image/volume for diagnosis.

`--docker-seccomp-profile` is an explicit operator-supplied fixture policy, not
an automatic setup change. Omit it to retain Docker's default syscall policy.
The driver drops container capabilities and sets `no-new-privileges`, preserves
Codex's workspace sandbox and copies the selected policy into the evidence.

Fixture versions: Codex CLI 0.160.1, Claude Code 2.1.236, Copilot CLI 1.0.86,
APM 0.29.0; image/runtime identities are in the resulting reports. Outer CLI
processes are acceptance harnesses; the existing compounding feature still uses
native subagents. No scheduler or real compounding run is created here.

## Consolidated review

One independent read-only round used four reviewers covering credential state,
setup/launch/APM, preflight/native evidence, and semantic skill behavior. They
compared the actual original and replacement sources with the full plan. There
was no second round or repeated reviewer approval after fixes.

Seven defects were corrected in `62ef1ed` and the acceptance-driver slice,
with focused regressions:

1. Recover the two journaled links left by interrupted credential publication,
   while rejecting unknown additional hard links.
2. Allow owned credential removal when the knowledge config, catalog or source
   mount is unavailable, preserving registry defaults and unrelated entries.
3. Include lock deployments and native skill catalogs when protecting existing
   APM targets; unsupported lock layouts defer to the repository-owned workflow.
4. Do not add the working directory to PATH when the inherited PATH is absent.
5. Convert runtime path-resolution failures into structured preflight diagnostics
   and suppress requested writes on an invalid route.
6. Preserve structured failed-child results and export native evidence before
   disposable cleanup, including failed runs.
7. Require the exact fixture signal to be drained and absent; successful compound
   finish alone cannot prove cleanup.

The eighth finding identified incomplete sandbox proof. The driver now reports
credential-write and explicit read-only launch checks as **unverified** and keeps
native acceptance partial. Canonical fixture write denial alone is not complete
sandbox coverage. The subsequent authorized Docker retest supplies these checks through the actual
Codex sandbox helper. The original driver reports remain unchanged, with this
separate evidence clearly identified; native hook delivery is still unverified.

The semantic review confirmed preservation of explicit profile overrides/defaults,
local skills, instruction ownership, strict activation, publication boundaries,
shared compounding state, and the absence of automatic sandbox widening or trust
grants. This is an assessment of the authored procedure, not a substitute for
native execution in the developer's environment.

## Results and limits

The final deterministic suite passed **1,825 tests in 64.30 seconds**. Ruff,
formatting, mypy (57 source files), whitespace checks, skill validation and
wheel/source builds passed. The isolated fresh-consumer check passed actual
APM installation/compilation/audit, all three targets, source/resource parity,
staged prepare/bind, credential readiness/activation fixtures, hook ownership,
reinstall/rebind, signals and guarded cleanup.

Evidence is in `.cache/container-launch-proof/`: `pytest-seccomp-final-trust.txt`,
`ruff-seccomp-final.txt`, `format-seccomp-final.txt`, `mypy-seccomp-final.txt`, `skill-final.txt`,
`build-final.txt`, `fresh-consumer-final.json` and its `.log`.
One earlier full run had two detector classification failures; a repeat passed
all 1,816 then-current tests. 1,350 isolated real detector executions did not
reproduce the failure. The original diagnostic did not distinguish I/O from a
bounded-wait failure, so load attribution is uncertain. Exact classification and
wait/kill semantics now have deterministic fixtures; a real noisy child still
proves bounded termination and output privacy. Production deadlines were unchanged.
Failed and repeat results are preserved as `pytest-final.txt`,
`preflight-detector-retry.txt` and `pytest-final-retry.txt`.

The current-wheel Debian and Alpine runtime checks passed under UID/GID 1000
with immutable runtime, no uv, filesystem lock exclusion, concurrent receipts,
private-environment checks, guarded reads and state-preserving recreation.
Evidence: `.cache/container-runtime-final/report.json`. Python versions were
3.12.13 (Debian) and 3.12.15 (Alpine); the runtime payload fingerprint was
`6a2ac00abe68f04819fe23d208d1b489192c7106f387bca5984e17941f74de7d`.
This remains runtime/registration-fixture proof, not native model proof. The
writable-runtime installation route passed the host fresh-consumer check and
deterministic tests; direct Linux-container provisioning remains unverified.

### Authorized Docker retest

After the initial failure, the owner authorized reconfiguring Docker for local
testing. Docker Desktop 4.60.0 / Engine 29.2.0 on arm64 reported builtin seccomp
and cgroup namespaces. A nonroot `unshare(CLONE_NEWUSER)` probe failed with
`EPERM` under that default and passed when that operation alone was permitted.
The kernel supports user namespaces; a global kernel/Docker change was unnecessary.

The local test profile extends a saved upstream Moby default profile, retaining
its default-deny action and original rules. It additionally permits:

- `clone` only when the `CLONE_NEWUSER` bit is set;
- `unshare` only with exactly `CLONE_NEWUSER`;
- `mount`, `umount2` and `pivot_root`, needed for the nested sandbox filesystem.

Removing each of those five syscall permissions separately made the sandbox
fail. `setns` and `sethostname` were tested and not needed. This establishes the
tested command's requirements, not a universal policy for every kernel/harness.
The upstream profile snapshot is identified by digest, not asserted to be
byte-identical to this engine's builtin profile.

The disposable container remains UID/GID 1000, with `--cap-drop ALL`,
`no-new-privileges`, no privileged mode, no host-directory or Docker-socket
mount, and the existing Codex `workspace-write` sandbox. Only its fictional
state volume is mounted. Docker Desktop settings, daemon configuration, host
sysctls and actual consumer/user configuration are unchanged.

The retained image was reused with a copied disposable volume. Native tools
then exposed two fixture defects: central signal storage had not been
initialized as a Git checkout, and Debian login-shell startup reset the
runtime PATH. The driver now initializes both fixture repositories and uses
Codex's `allow_login_shell=false` for this test route. Exact fixture-project
trust uses the native top-level TOML map; quoted dotted-path overrides are
ignored by this CLI. No hook-trust or sandbox bypass flag is used.

Actual Codex tools passed selected retrieval, catalog/search/inspect receipts,
write-mode doctor, synthetic credential activation, signal capture/listing,
guarded drain with confirmed absence and canonical-file write denial:

| Phase | Native session | Result |
| --- | --- | --- |
| Fresh | `01a11318-5422-7791-affc-0e056568bad6` | Tool acceptance passed |
| Reused | `01a11319-24e1-7f41-b6f7-231e1a550739` | Tool acceptance passed |
| Recreated | `01a1131a-6eeb-78f2-9bf4-f2f1c74166f2` | Tool acceptance passed |
| Fixture trust follow-up | `01a1131b-f9f5-7440-979f-436b4bcad937` | Tool acceptance passed; hook delivery still unverified |

Recreation preserved 16 populated signal/receipt/coordination files, with
matching hashes and inode identities, and repeat binding passed. The final
checkpoint contains 24 files. Old failure evidence is retained separately.

A separate **model-free native sandbox helper** ran through the generated
launcher under both `workspace-write` and explicit `read-only` policies.
It verified runtime selection, mapped canary presence and canonical reads.
Workspace-write permitted the three selected write roots and produced real
retrieval receipts. Both policies denied opening the private credential fixture
for writing, although the same UID could open it outside the inner sandbox.
Read-only denied write opens in every selected root. Its read-only child did
not attempt data writes or receipt-producing retrieval. Canonical-file denial
also has an image-ownership constraint, reported separately. These are actual
native sandbox API checks, not model/session or hook evidence.

Hook delivery remains unverified. Native saved messages did not supply the
exact installed lifecycle/prompt reminders; successful probes obtained their
session IDs from native environment variables. Registration, project trust and
tool success do not substitute for native hook-delivery evidence. Claude and
Copilot still lack designated container authentication; Windows-host mount and
direct container-local writable-runtime provisioning proof remain outstanding.

Evidence: `.cache/container-launch/seccomp-verified/report.json`, its native
transcripts/tool reports, `sandbox-helper.json`, `prepare-recreated.json`,
`docker-security.txt` and `docker-seccomp-provenance.json`. The profile, original
upstream snapshot, reduction tests and diagnostic script are under
`.cache/container-launch-proof/`. The test container
`knowledge-launch-seccomp-proof` is stopped; its image, volume and evidence are
retained. Starting another test requires the same explicit per-container policy.
Two earlier task-owned failure volumes were removed for space; the original
authenticated fixture and exported evidence were preserved.

### Initial native container result

Before the Docker retest, `.cache/container-launch/authenticated/report.json` was
**partial**. On Debian 13.7/aarch64 with glibc 2.41, all three installed CLIs
started through the generated launcher; preparation, repeat binding, target
preservation and container recreation passed. Codex authenticated and completed
model turns in all three phases:

| Phase | Native Codex session | Model result | Tool acceptance |
| --- | --- | --- | --- |
| Fresh | `01a112cf-bae2-76b2-a691-e37177ccc722` | Completed, exit 0 | Blocked by namespace policy |
| Reused | `01a112cf-d977-7273-9120-587ac4770f7f` | Completed, exit 0 | Blocked by namespace policy |
| Recreated | `01a112d0-08b4-77e1-8531-a9823a67e4e2` | Completed, exit 0 | Blocked by namespace policy |

The native shell tool returned:

```text
bwrap: No permissions to create a new namespace, likely because the kernel does not allow non-privileged user namespaces.
```

The agents stopped without changing permissions. This proves authenticated
model execution through the in-container launcher, but not selected retrieval,
receipt/signal writes, mapped fixture-credential activation or native hook
delivery. Those remain pending. State checkpoints were empty, so this native
attempt does not prove persistence of written state or locks; the separate
Debian/Alpine runtime tests do. No sandbox bypass, privileged container or
host-policy change was attempted. A compatible owner-approved environment is
required before repeating native tool acceptance.

Native evidence is in `codex/{fresh,reused,recreated}-native.jsonl` beside that
report. The transcripts contain five failed shell calls (two fresh, two reused,
one recreated); prerequisite discovery was attempted, but the fixture probe
never ran. The report records the then-current `62ef1ed` revision; its driver
digest matches the subsequently committed `27cd6e9` driver exactly, and runtime
and package sources are unchanged between those commits. The final candidate
manifest records this correspondence.

Claude and Copilot have startup/registration proof only: designated
live authentication was unavailable. Canonical-write denial, credential-write
denial and explicit read-only launch proof remain unverified for native tools.

The preceding `.cache/container-launch/verified/` attempt failed before tools
because the driver did not activate Codex's API authentication. It reported
"Missing bearer or basic authentication in header"; that was not evidence of an
invalid credential. The corrected driver maps the explicitly selected source
to `CODEX_API_KEY` only in the Codex child, as required by the
[noninteractive authentication contract](https://learn.chatgpt.com/docs/non-interactive-mode#use-api-key-auth).
Other providers' auth variables and conflicting Codex values are removed. No
login/keychain fallback, alternate account or secret persistence is used. Focused
regressions cover this bridge; the successful model turns used the same source.

### Earlier failures and corrections

Earlier attempts remain separately recorded under `prepare/`, `prepare-final/`,
`final/`, `trixie/` and `trixie-resumed/`. They preserve dependency, storage,
binary-compatibility and audit failures.

The first attempt exposed a missing fixture-script dependency, now included in
the driver's build context. A subsequent attempt failed with a Docker BuildKit
metadata I/O error after storage exhaustion. No live model acceptance began in
those attempts; they establish neither harness success nor failure.

The next image build succeeded, but APM 0.29.0's SHA-verified Linux arm64 release
failed to load on `node:24-bookworm-slim`: its bundled Python library required
`GLIBC_2.38`. Evidence is `.cache/container-launch/final/report.json` and
`build.log`. No native harness ran. The fixture was corrected to
`node:24-trixie-slim` with its `libicu76`; this is a disposable test-base choice,
not a consumer image requirement or a change to the APM pin. Verify actual pinned
setup-tool/harness binaries independently of Python-runtime compatibility.

The Trixie image built but preparation initially hit `ENOSPC`: Docker's internal
118 GiB filesystem had zero available space despite free host storage. Removing
only earlier task-owned images and volumes freed 758 MiB; no broad prune or
Docker restart was used. The resumed setup then installed/compiled/bound the
package, but the fixture wrongly required raw install-replay audit to remain
clean after binding. Audit reported exactly the five hook files that binding
intentionally changes; its other nine checks passed.

The corrected fixture requires clean audit after install/compile, then verifies
binding/idempotence and the post-bind audit separately. It requires all nine
other audit checks to pass and precisely those five modified hook paths. Raw
post-bind `passed:false` remains saved, and any additional/removed file, missing
check or other failure rejects acceptance. This is the disposable fixture's
explicit two-owner final-state check, not permission to alter a consumer's native
checks or skip drift checks. Final reports record the bound-hook differences.

Actual Windows-host mount behavior requires a Windows-host run. Unix permission
fixtures do not establish it. Missing provider authentication, native trust,
hook firing and sandbox proof are reported separately. Host-native compounding
proof from the previous feature is not authenticated-in-container proof.
Native scheduling tests remain paused.
