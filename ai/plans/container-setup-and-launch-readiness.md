# Existing-container setup and launch readiness

Date: 2026-10-06
Status: Planned; implementation and acceptance execution have not started.
Owner: Agent Knowledge Scaffold, primarily the `knowledge-setup` skill.
Baseline: the local `nik/local-compounding-hooks` candidate based on
`c2e6d875a68d165e3d94870c5040980625ac9451`, including its uncommitted changes.

This is a follow-up to
[local compounding and container setup](local-compounding-hooks-and-container-setup.md).
It preserves that work and its recorded proof; it adds container launch and
acceptance requirements. The owner requested this plan, not implementation,
consumer installation, publication or changes to running sessions.

## Outcome and boundaries

An agent can guide setup inside a developer's existing container, prepare the
selected profile, provide the exact launch integration and prove that knowledge
works from the launched harness. Support Codex CLI, Claude Code and Copilot CLI
through the existing provider contracts. Keep all distributed material
organization-neutral, with fictional examples and explicit configuration.

We supply skills, instructions, narrow reusable setup/preflight support and
verification methods. We do not supply or require a Docker image, base image,
Dockerfile, devcontainer definition, Compose project, Docker socket or privileged
container. Small adaptations to the consumer's existing launcher/build are
derived from its conventions. Disposable image fixtures are tests, not a
deployment product. No separate container skill is required: `knowledge-setup`
owns the flow and links its detailed container reference.

Preserve consumer-owned APM pins, install/compile/check commands, authored
instructions, local skills, target sets, generated outputs and approval policy.
Preserve explicit profile selection, publication rules and user-wide defaults.
Do not copy a corpus, change the knowledge schema, install a scheduler, introduce
a second compounding state store or broaden publication authorization.

## Developer workflow

1. The developer invokes `knowledge-setup` in the existing environment. Before
   selecting paths or making changes, the agent establishes whether its tools
   and the intended harness run inside the target container, on its host, or in
   an uncertain/different environment.
2. When inside the target container, the agent inspects its user, mounts,
   runtime, selected profile and consumer integration. It reuses prior setup and
   prepares only missing or changed pieces. From the host, it supplies the
   existing container's exact entry/resume action and continues container checks
   there; a host result is never labelled container proof.
3. Setup prepares the selected container-local profile and supplies the exact
   launch integration, including inherited runtime PATH, registry selection and
   provider-specific credential activation where configured.
4. One bounded acceptance sequence runs through that launcher: selected-profile
   retrieval, receipt and signal writes, credential activation, native hook
   delivery, and repeat/reuse behaviour. Report each result independently.
5. Later launches perform lightweight readiness checks. Relevant changes lead
   to the specific setup/acceptance steps they invalidate, without routine
   package installation, APM compilation or rebinding on every launch.

## Evidence and starting point

The existing candidate already provides immutable image-runtime verification,
portable hooks, explicit environment-local paths, persistent storage/lock
checks, repository-owned APM sequencing and separate readiness results.
[Its proof](../../docs/local-compounding-proof.md) records Debian/Alpine runtime
tests and separate host-native harness tests. Authenticated harness execution
inside Docker and Windows-host mount behaviour are not established by combining
those two sets of results.

The owner's photographed rollout feedback (IMG_1208 through IMG_1215) reports
Windows bind-mount permission problems, actual harness sandbox write failures,
launch-environment differences and hook trust/delivery distinctions. APM 0.31.0
target pruning and Codex CLI 0.160.1 observations are version-scoped reports,
not independently reproduced universal claims. Preserve that distinction in
troubleshooting guidance and acceptance results.

## Design decisions

### 1. Establish where execution happens

Add this check early in `knowledge-setup`, even when the developer has not said
"container". Inspect available container markers, process/cgroup/mount evidence,
existing devcontainer or launcher configuration, effective UID/home/cwd and
actual path access. Do not dump process environments or secret-bearing arguments.
Linux, a `/workspace` directory, a Docker client or an absent marker alone does
not establish container/host identity. Detection is evidence, not a security
boundary; record uncertainty and conflicting observations.

Distinguish the agent tool process, intended harness process and any host
orchestration process. Record the target identity and the evidence for
`container`, `host` or `unknown/conflicting`. Inspect existing remote/exec
routing rather than assuming the visible shell and harness share a machine.
When location is unclear, continue independent read-only discovery and ask one
short question only if needed to choose the execution target. Do not mutate
host paths while assuming they are container paths. Do not create a container,
restart a session or require access to a host Docker socket to resolve uncertainty.

The skill must give the agent this concrete read-only procedure, not just tell
it to "detect containers":

1. **Identify the current tool environment.** Run `uname -s`, `id` and `pwd -P`
   when available; resolve the home directory and selected executable paths.
   These establish OS, user and path context, not container status. On a native
   Windows shell, use its platform equivalents; do not attempt Linux probes.
2. **Collect container evidence on Linux.** Use the following bounded probes
   when their files/tools are available. Missing tools or denied access are
   recorded as unavailable, not repaired by installation or permission changes.

   | Probe | Interpretation |
   | --- | --- |
   | `test -f /.dockerenv` and `test -f /run/.containerenv` | Presence supports a container diagnosis; absence does not establish a host. Check existence only. |
   | `sed -n '1,80p' /proc/self/cgroup /proc/1/cgroup` | Runtime/container-related entries are supporting evidence. A plain `0::/` is inconclusive, including on cgroup v2. |
   | `systemd-detect-virt --container`, if installed | A reported runtime is supporting evidence; an unavailable or negative result is not decisive. |
   | `ps -o pid=,ppid=,comm= -p "$$"` and the relevant parent PIDs | Inspect executable names/ancestry where visible. Do not request full arguments or environments. A tool shell need not be a descendant of the harness. |
   | `readlink /proc/self/ns/mnt` and `readlink /proc/1/ns/mnt` | Namespace references can help compare known execution contexts. They are not portable container IDs or proof of host identity. |

3. **Trace the intended harness launch route.** Read the relevant existing
   devcontainer, entrypoint, wrapper or remote-tool configuration. Identify where
   the CLI is launched, under which user and with which mounts. A devcontainer
   file proves intended configuration only; it does not prove the current
   session used it. Cross-check native session/executor metadata and observed
   process/path evidence. Read targeted non-secret fields; do not dump full
   process environments, Docker inspection output or credential-bearing config.
4. **Verify the target context.** Run the same bounded checks through the
   established target route and later through a tool in the actual harness
   session. Confirm that the resolved runtime, workspace, registry and state
   paths exist there. Host-side `docker exec` can establish a container-shell
   baseline but cannot prove the harness itself runs there or has the same
   sandbox. If the outer harness is not observable, leave its location unknown.
5. **Report and act.** Produce a compact result such as `tool: container;
   harness: unknown; evidence: runtime marker and target-path access; next:
   verify the configured in-container CLI launcher`. Proceed when evidence and
   the requested target agree. For a confirmed host, provide the existing
   container entry/reopen action. For unresolved location, ask only for the
   missing target/launch fact before location-dependent changes. Do not infer
   "host" merely because all container probes were negative.

### 2. Keep preparation and launch checks separate

Extend the existing setup helper for preparation and reuse the installed
runtime's configuration, profile and doctor implementations for preflight.
Expose one installed, bounded preflight operation with a structured value-free
report. Finalize its narrow request/response and CLI spelling in the first
implementation slice, then synchronize `describe`, documentation and tests.
Do not build a second shell implementation of profile parsing or installation.

Preparation is explicit and idempotent: inspect, prepare paths/profile/runtime,
use the owning APM workflow, bind and check. The runtime can be either:

- Image-built and immutable, verified against the exact pinned source/wheel
  with `--runtime-mode existing`; no installer or venv writes are required.
- Provisioned into a container-local writable venv from an explicitly supplied
  pinned artifact or mounted checkout. A changed checkout does not mean the
  installed runtime changed; update explicitly and retain package parity.

The matching APM package still supplies skills/scripts; the wheel alone does
not. Reuse compatible installed Python and image package/index conventions.
Do not automatically download Python, fetch arbitrary source, downgrade a
supported interpreter or replace the developer's tools. Diagnose missing
interpreter, launcher, cache permissions, reference mismatch and dependency
failure separately. Preserve partial installations for diagnosis and give a
specific repair; do not delete shared caches/volumes or recursively change owners.

Normal preflight checks the current route, executable/registration availability,
private-file readiness and required storage. It neither installs nor repairs.
It does not claim live hook or sandbox proof from a previous unrestricted check.
Bound its work: no model invocation, network request, corpus scan, package install
or full dependency compilation. Explicit acceptance may perform disposable writes;
ordinary checks must not append signals or run compounding.

Preparation and acceptance fail their required stages explicitly. A consumer
may preserve an existing advisory/degraded launch policy, but failure must stay
visible with a non-success readiness result and exact remediation. Never swallow
errors with a success marker, activate invalid credentials or silently substitute
ambient credentials. Unrelated pending credentials do not erase read readiness.

### 3. Prepare portable profiles and private credentials

Use the existing registry/profile/environment contract. Preserve explicit
session choices, unrelated profiles and existing global defaults. Resolve all
effective paths in the target container: workspace/config, catalogs, sources,
signal and usage storage, code root, runtime and private environment file.
Respect each path's original relative base; copying a registry and replacing
only `environment.file` is insufficient. Use supported local overrides and
checked profile registration rather than textual search/replace or interpolation.
Keep environment-specific absolute paths out of shared generated instructions.

Reuse an already valid container-local private environment file. For a selected
host-mounted source that cannot satisfy runtime ownership/permissions, provide
an explicit preparation route to a user-owned Linux-backed private directory
outside Git and image layers (directory `0700`, environment file `0600`). The
source must be designated by the selected setup, never discovered from ambient
credentials. Reject unsafe traversal, nonregular files and unexpected identity
changes. Copy atomically, preserve the original, and publish the local registry
route only after its target is safely prepared. Keep the runtime parser strict;
projection is not a permission-check bypass. Copying does not establish the
security of the original mount; retain any source-side limitation in the report.

Define repeat preparation, interrupted writes, concurrent attempts, credential
rotation and removal. An explicitly configured projection refreshes through the
same guarded preparation operation before a new credentialed launch; it may be
a narrow launcher pre-step, never an implicit installer. Preflight itself does
not copy secrets. A failed refresh must not silently activate an old copy.
Cleanup removes only setup-owned private projections, never host originals,
unrelated profiles or persistent knowledge/session state.

Keep values out of logs, YAML, command arguments, generated hooks, diagnostics,
signals and evidence. Do not print or persist credential hashes. Preserve blank
entries as pending and quoted/interpolated-value rejection. A changed profile
declaration requires the owning setup/rebind checks and a new harness session;
already running processes are not remotely re-credentialed.

### 4. Produce the actual launch integration

Derive one exact start action for each selected/installed harness using the
existing setup-generated activation route. Preserve the consumer's working
directory, original argument boundaries, intended PATH additions and existing
launch flags. Carry the registry through the inherited environment when
portable hooks need it; a CLI `--settings` argument alone cannot configure a
separate hook process. Do not rely on shell rc files or change them implicitly.

Apply the same readiness route to fresh-container and reused-container launch
branches. A `postStartCommand`, an entrypoint and `docker exec` are different
execution paths; verify the one the developer actually uses. Do not claim that
starting a new shell inherits exports made in a different process.

Keep provider-specific activation/redaction protections. A prompt-hook child
cannot activate parent credentials, and changing knowledge selection does not
switch credentials already loaded into a session. Preserve native provider
login/keychain ownership separately from tool credential mappings.

### 5. Preserve integration and sandbox ownership

"Ownership" means each part keeps its existing authority for making and
validating changes. It does not add a new approval gate for authorized setup.

| Authority | What setup must do |
| --- | --- |
| Consumer repository's APM workflow | Use its pinned version and registered install/compile/check commands. Add the package through that workflow and preserve all established targets. |
| Authored instructions and local skills | Edit the real owning source when needed and let its tooling deploy/generate outputs. Preserve unrelated skills and user edits. |
| Scaffold package/runtime | Own generic profile validation, hook behaviour, readiness reporting and guarded state operations. Consumers configure these mechanisms rather than copying a private replacement. |
| User/consumer and native harness sandbox policy | Derive required access, apply authorized narrow changes through the correct configuration, and verify effective permissions. Never silently disable restrictions or grant trust. |
| Existing compounding activity and coordination | Reuse the configured store, run history, trigger owner and locks. A container restart is not a new job, an empty history or permission to start competing work. |

For an existing consumer retain:

`prepare -> repository install/compile -> bind -> repository final checks`

Inventory the established APM target set before installation and verify it
survives afterward. A single-harness test must not prune other targets. Use
repository-native compilation, including its prescribed output topology and
staged-content checks. Do not handcraft locks, edit generated instructions,
replace remote dependencies with local paths as a workaround, or duplicate hooks.
Rebind after the final APM operation when it resets package-owned registrations.

Container filesystem writability and harness sandbox access are separate.
Derive the minimum required signal/usage/private-runtime paths and inspect the
actual selected harness policy. Setup may propose or apply an already-authorized,
targeted consumer configuration change, preserving unrelated settings, comments
and native precedence. It must not universally patch a global config, grant
trust, disable sandboxing or silently widen source/credential write access.
Respect explicit read-only operation and configuration/CLI overrides. Report
effective policy and any still-required owner decision, not just intended flags.

Keep persistent signals, receipts, activity and shared lock files on the same
proven state storage for all writers. Container-local private credentials have
a different lifecycle. Do not move only coordination locks or reset history to
make a recreated container appear ready.

### 6. Verify once through the actual launcher

Provide one reproducible acceptance driver/procedure, with provider adapters
where necessary. It enters the real consumer launch route and saves a value-free
report. Reuse the installed `describe`, selected `context`, explicit write-mode
`doctor`, retrieval and filesystem probes. Do not author receipt JSONL manually.

| Area | Required acceptance evidence |
| --- | --- |
| Execution | Identified container/user, harness/tool execution contexts, runtime and effective selection; host checks labelled separately. |
| Retrieval | A representative selected-source query and inspected result resolve to the intended workspace. Empty fixtures prove operation only, not retrieval relevance. |
| Writes | Signal/receipt readiness through the actual harness tool sandbox plus a real retrieval receipt. Fixture integration also proves signal record/list and cleanup through supported ownership rules. Never manually delete user signals. |
| Credentials | Configured mappings activate through the actual provider route with target variables removed from the test parent. Observe presence/success only. No ambient fallback, real-value output or fake production values. Profiles without credentials report not applicable. |
| Hooks | Registration, native trust where observable, and actual lifecycle/prompt delivery are separate results. Save native evidence; synthetic input, echoed instruction text or registration alone is insufficient. |
| Scope | Effective permissions retain explicit read-only choices and grant no unintended canonical-source or credential writes. Probe with isolated fixtures; do not attempt destructive writes to real source files. |
| Repeat/reuse | Repeat preparation/binding does not duplicate projections or damage targets. Reused container and fresh harness session retain the route. Recreation preserves state/locks; credential refresh respects session boundaries. |

Use disposable fictional fixtures for write/negative tests; tests may use
clearly synthetic canaries inside isolated fixtures, never the user's profile.
Consumer verification uses `doctor`'s disposable probes and ordinary receipt
operations. If real signal capture must be exercised, retain or disposition it
through the supported CLI, never hand-delete it. Native APIs may establish
effective sandbox policy without model tokens where supported; a claim that a
prompt hook fired still requires the corresponding real native event.

Acceptance records exact source/wheel/package and harness/APM versions, launch
mode, container/image identity where available, user/mounts, selected paths,
commands, per-stage results and precise missing proof. Do not retain secret
values or secret-bearing URLs/argv. Registration, runtime, credential, sandbox,
hook, compounding and publication readiness remain separate.

### 7. Invalidate only affected proof

| Change | Required follow-up |
| --- | --- |
| Image/interpreter/runtime artifact | Verify the running image/runtime, rebuild or explicitly reprovision if needed; repeat runtime and affected launch proof. A rebuilt tag does not update a running container. |
| APM package, target set or generated inputs | Owned install/compile, bind, final consumer checks and affected hook/skill proof. |
| Profile declarations, registry or path mapping | Checked profile preparation, affected binding, new session and selection/credential proof. |
| Credential values in the same declared file | Guarded refresh when projected; new credentialed launch and activation verification. No automatic APM reinstall. |
| Mounts, runtime UID or sandbox policy | Repeat path/write/lock and actual sandbox checks; recreate only when required and authorized. |
| Consumer launcher or harness upgrade | Verify inherited environment, arguments, native hooks/trust and affected sandbox/credential proof. |
| No relevant change | Lightweight preflight; reuse valid acceptance evidence without claiming it certifies a different environment. |

Do not equate timestamp markers or launcher existence with readiness. Any saved
acceptance/setup provenance is value-free and is not a new compounding authority.
Normal startup never invokes compounding directly. Preserve the existing native
local scheduling preference, prompt fallback and native-subagent execution
interface, one shared-store owner and the existing activity log. No shell model
worker, new automation or cloud-compounding recommendation is introduced.

## Delivery slices and owners

| Slice | Work | Exit evidence |
| --- | --- | --- |
| C1 - Context and contracts | Setup skill/container reference; environment assessment, phase/readiness contract and exact preflight interface. | Host/container/uncertain cases and report fixtures; preserve existing contracts. |
| C2 - Profile preparation | Reuse profile/environment/guarded-file infrastructure; private projection, path translation, refresh and cleanup. | Permissions, interruption/concurrency, blanks, paths and secret-output tests. |
| C3 - Launch and preflight | Narrow installed operation and setup integration; exact provider start actions, reuse branches and affected-change guidance. | Runtime/launcher/environment failures and repeatability tests; no routine install/APM side effects. |
| C4 - Owned integration and acceptance | Preserve APM targets; actual-launcher verification, sandbox/trust reporting, persistence and lifecycle tests. | Fresh consumer and deterministic adapters; existing ownership checks pass. |
| C5 - Assembled proof and handoff | All supported harnesses in containers, documentation/examples, one consolidated review and justified fixes. | Native gates and evidence matrix; unresolved environment/provider proof remains explicit. |

C1 precedes C2/C3; C4 integrates their final interfaces. C5 tests the assembled
candidate. Reconcile branch, working-tree changes and package identities before
implementation; do not overwrite the prior candidate or unrelated work. Keep
changes reviewable by slice. Perform one consolidated independent review of the
final setup, credential, integration and evidence behaviour; rerun affected
checks after fixes without requiring repeated reviewer approval.

Primary authored surfaces:

- `packages/knowledge-agent-pack/.apm/skills/knowledge-setup/SKILL.md`, its
  `scripts/setup_runtime.py`, profile registration support and references
  `containers.md`, `portable-hooks.md`, `profiles.md`, `existing-repository.md`.
- Existing domain/application/infrastructure/entrypoint boundaries for the
  installed preflight and guarded projection; reuse doctor/profile primitives.
  Keep host/filesystem/process observations out of pure domain code.
- `docs/agent-contract.md`, `docs/fresh-consumer.md`, `docs/harness-support.md`,
  package/root README and a bounded container proof report. Synchronize generated
  resources through their owned workflow when authored contracts change.
- Focused unit/integration tests and `tests/e2e/` container, filesystem and
  provider acceptance drivers. Avoid a second container orchestration framework.

## Acceptance criteria

- [ ] **AC1:** Agent instructions assess container/host/unknown execution before
  choosing setup paths; distinguish tool and harness locations without relying
  on Linux alone or modifying the wrong environment.
- [ ] **AC2:** Developer retains image, runtime user, tools and launcher. No
  distributed Docker image or required Dockerfile/devcontainer/Compose project.
- [ ] **AC3:** Both immutable image runtime and explicit container-local
  provisioning work, preserve supported Python, and verify exact package parity.
- [ ] **AC4:** Selected profile resolves every relevant path inside the target
  environment, preserving relative bases, defaults and explicit user overrides.
- [ ] **AC5:** Private projection is guarded, atomic and repeatable, with tested
  refresh/removal and interruption/concurrency behaviour. Runtime credential
  validation is unchanged; originals and unrelated profiles survive.
- [ ] **AC6:** Exact provider launch actions carry the intended environment and
  original argument semantics on fresh and reused container routes.
- [ ] **AC7:** Preflight reports independent readiness and specific remediation;
  ordinary launch performs no install, APM compile/rebind, model call or compound.
- [ ] **AC8:** Consumer APM pins, target set, local skills, authored ownership,
  generated outputs and final/index checks survive installation and rebinding.
- [ ] **AC9:** One actual-launcher acceptance sequence proves selected retrieval
  and receipts/signals in the harness's effective sandbox, not only Docker exec.
- [ ] **AC10:** Credential activation is verified without ambient false positives
  or secret output; blanks and unavailable activation remain visibly pending.
- [ ] **AC11:** Native registration, trust and firing are distinguished for
  Codex, Claude and Copilot. Regeneration/upgrade invalidates affected proof.
- [ ] **AC12:** Persistent state and lock coordination survive reuse/recreation;
  private credential lifecycle does not reset signals, sessions or activity.
- [ ] **AC13:** No automatic sandbox widening, trust granting or changes to
  unrelated global configuration; read-only and native override semantics hold.
- [ ] **AC14:** Compounding retains existing state, ownership, native workers,
  scheduling preference/fallback and publication boundaries; no new trigger.
- [ ] **AC15:** Reports distinguish deterministic, container-filesystem and real
  harness proof, with exact version/environment coverage and missing prerequisites.
- [ ] **AC16:** Skills, installed contracts, examples and focused regressions
  agree; native repository gates and applicable fresh-consumer checks pass.

## Validation matrix and proof limits

Run focused deterministic checks during implementation, then the repository's
native gates on the final candidate: `uv run pytest -q`, `uv run ruff check .`,
`uv run ruff format --check src tests`, `uv run mypy`, `git diff --check`.
Packaging/APM changes additionally require `uv build` and the isolated
[fresh-consumer procedure](../../docs/r8-harness-proof.md).

Cover host/container/uncertain detection, missing/stale launchers, offline
existing-runtime checks without uv, cache permissions, unsafe/symlinked paths,
relative registry bases, Windows-style source paths, mounts ignoring chmod,
partial writes, concurrent projection, rotation and blank mappings. Assert that
captured output contains no fixture secret or transformed credential value.
Verify previously installed targets and unrelated hooks remain intact.

Run disposable Debian/glibc and Alpine/musl runtime/file tests with nonroot users,
immutable and writable runtime routes, bind mounts and persistent Linux volumes.
Run actual authenticated Codex, Claude and Copilot acceptance through a compatible
existing Linux container launcher. Do not claim every harness supports Alpine
merely because the Python runtime passes there. Record actual provider/base-image
support and missing auth independently. Use isolated fictional knowledge; no
real corpus migration or public test publication.

Actual Windows-host Docker mounts require their own run/evidence. Simulated
permissions are regression coverage, not Windows proof. If that host or a native
harness is unavailable, finish independent work and record the exact missing
proof; do not check the corresponding live criterion as complete. Native
scheduling tests remain paused under existing instructions. Container acceptance
does not require creating a scheduler or running real compounding.

## Current checkpoint

- Plan saved; C1-C5 and AC1-AC16 are not implemented or verified by this task.
- Earlier local-compounding candidate and its evidence are preserved.
- No runtime, consumer, credentials, automation or running session changed.
- Next action: implement C1 against the reconciled candidate when requested.
