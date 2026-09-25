---
name: knowledge-setup
license: 0BSD
description: >
  Set up an organization-neutral knowledge workspace from business context,
  including runtime, hooks and compounding. Use when onboarding or reconfiguring.
  Do not use when processing signals; use knowledge-compound.
  Success means validated configuration and reported runtime/automation readiness.
---

# Knowledge setup

Use this skill when a consumer adopts the scaffold or changes its business
context, workspace, runtime or harness targets. Help the developer choose
meaningful knowledge boundaries and vocabulary; derive routine paths and
runtime values. Setup may create an empty knowledge source. It does not invent
business facts, copy a corpus or implement a scheduler.

For first use, the developer clones the scaffold and opens that checkout in
their harness. The agent can read this bundled `SKILL.md` by path before APM
installs the native skill catalog. Setup then configures that existing clone;
it does not require a second checkout to obtain the skill.

## Discover context and confirm the meaningful choices

Read [Business onboarding](references/business-onboarding.md) before creating
or changing catalog/workspace configuration. It covers discovery, a small
proposal and the empty-catalog case, with schema-valid examples. For labels,
read [Register and verify a named profile](references/profiles.md); it owns
registry confirmation, checked writes, the consumer's persistent profile
recommendation, bootstrap order and automation selectors.
Read [Configure reviewed knowledge publication](references/publication.md) to
derive and verify the default GitHub PR destination from the canonical knowledge
checkout, preserve existing publication choices and report pending access.
It also establishes standing compounding PR authorization for all participating
consumers and records their routes in the shared automation; human review and
merge remain separate from opening a PR.
When adopting a fresh scaffold clone, or configuring an existing scaffold-derived
knowledge instance, read [Scaffold maintenance and upgrades](references/scaffold-upgrades.md)
before selecting publication. It owns conversion of the clone into one instance
checkout with `origin` for the user's repository and `scaffold` for updates,
plus the central maintainer instruction. Do not infer that role from the
application consumer or apply it to arbitrary knowledge sources.
For a repository with existing APM generation or layout checks, also read
[Integrate with repository-owned APM](references/existing-repository.md). Inspect
its applicable instructions, manifests, pinned commands, targets and local skill
catalog before choosing the setup mode or mutating consumer configuration.
Preserve those contracts; already authorized integration does not need another
approval merely because the repository owns its build commands.
For shared checkouts or hooks committed for multiple environments, read
[Portable hooks](references/portable-hooks.md). Select `--portable-hooks` with an
explicit profile, provision the runtime and registry locally in each environment,
and verify PATH in the harness process. Do not bind a shared checkout to one
machine's absolute paths or put credentials in committed configuration.

1. Resolve the intended workspace path, suggesting
   `<current checkout>/knowledge-workspace.yaml` when not supplied. Inspect
   existing configuration, catalogs, local instructions and relevant business
   or product documentation. Preserve established identifiers and settings.
2. Ask a short batch of questions only for missing or conflicting context:
   what the business does and for whom, what agents should help with, and what
   knowledge is shared versus restricted to this workspace. Do not ask for
   facts already supplied or ask the developer to invent raw schema IDs.
3. Propose the configuration path and a small catalog using business language:
   a profile label and first-profile default when wanted, scope boundaries,
   topics, named entities and technology applicability only
   where supported. Show the suggested IDs and cite the context supporting
   them. A solo workspace can start with one business scope and one source;
   do not manufacture teams or a departmental hierarchy.
   Include the knowledge repository and base branch in this same proposal;
   default to PR review with branch prefix `knowledge/`. For a fresh clone,
   propose the user's own private repository, suggesting the name `knowledge`;
   the clone's upstream `origin` is not their publication destination.
   If the developer wants external tool credentials associated with the profile,
   also propose one external env-file path and the smallest explicit set of
   human-readable source-to-target variable mappings. Confirm names and purpose,
   never values. Do not ask the developer to choose Claude, Codex or Copilot
   injection mechanics; setup owns that translation.
4. Confirm those meaningful choices together before writing configuration or
   registering vocabulary. Existing user approval carries forward; an unchanged
   setup does not need another interview. For fresh adoption, establish and
   verify the user's repository and both remotes using the scaffold-upgrades
   reference before authoring publication settings. Register confirmed new
   concepts when necessary, then create or complete the catalog and workspace
   YAML using the defaults below. Empty catalogs are supported; an unknown ID in
   an ordinary search remains an error, not a reason to invent membership silently.
5. Run the runtime helper below, inspect `describe`, `context` and `doctor`, and
   validate any authored knowledge. For named-profile onboarding, persist the
   selected project recommendation in the consumer's authored instructions and
   verify its compiled output using the profile reference. This is setup work,
   not a manual follow-up for the developer. Report configuration, project
   recommendation, runtime, hooks and automation readiness separately. Unclear
   business meaning requires a
   focused clarification before dependent writes; independent readiness checks
   may continue.
6. For a verified scaffold-derived knowledge instance, persist its brief
   central-maintainer route in that checkout's authored APM source, including
   its verified upstream URL/name, then regenerate and check its harness outputs
   using the scaffold-upgrades reference. This is distinct from the consumer's
   profile recommendation. Reuse existing authorization and equivalent routing;
   report an unresolved source owner, upstream or ancestry as pending rather
   than guessing or creating a history baseline automatically.
7. Finish fresh adoption by reviewing and publishing the instance's non-secret
   bootstrap files through the scaffold-upgrades reference. Verify the catalog
   and maintainer instructions reach the remote base branch before declaring
   the shared instance ready; an initial push of untouched scaffold files is
   not a published setup.

The skill owns these defaults and does not ask the developer to supply them:

| Value | Default and behavior |
| --- | --- |
| Profile label/registry | Suggest a lowercase business/project label in `~/.config/agent-knowledge/config.yaml`; confirm it with the meaningful choices. Propose the first as default; preserve later defaults. Use the profile reference for reviewed atomic edits. |
| Knowledge instance | Reuse one adopted scaffold clone. Suggest a private repository named `knowledge` under the confirmed owner; `origin` publishes there and `scaffold` fetches the verified upstream. Preserve existing repositories and paths; follow the scaffold-upgrades reference before publication. |
| Project profile recommendation | For named-profile onboarding, persist the selected name and registry location once in the consumer's existing authored instruction source, then regenerate and verify its harness projections. Preserve an equivalent recommendation; resolve a conflicting one before replacing it. An explicit session choice still takes priority. |
| Profile environment | Optional. Suggest the developer's absolute home path ending in `.config/agent-knowledge/<profile>.env`, mode `0600`, and mappings such as `github: GITHUB_V_TOKEN -> GH_TOKEN` when existing tool needs justify them. Expand `~` before authoring because registry paths are literal. Preserve an existing path/mapping. Never ask the developer to paste values into chat, copy values into YAML or create guessed credentials. |
| Workspace identity | Preserve an existing ID. For a new file, derive a stable `workspace:<directory-slug>` from the configuration's durable parent and persist it. This identifies the setup; it does not claim organizational membership. |
| Source roots/catalogs | Preserve the selected configuration. For a new file, scaffold one empty source at `<scaffold>/knowledge` with `<scaffold>/catalog.yaml`. Additional sources remain an explicit configuration edit. |
| Producer code root | Derive the durable code-root parent from the current Git checkout/common directory; fall back to the scaffold's parent when no Git association is available. When the scaffold checkout itself can produce signals, its resolved path must be strictly below `code_root`: `scaffold_root: .` therefore pairs with `code_root: ..`, never `code_root: .`. The origin check still reports an unsafe mapping rather than guessing a project. |
| Signal storage | `<scaffold>/ai/signals`; create it when needed, keep it outside every canonical source and ensure that path is ignored by the scaffold. |
| Usage evidence | Enable diagnostic receipts with 30-day retention at `<scaffold>/ai/usage`; create this directory, keep it outside canonical sources and the signal inbox, and ignore it in Git. Preserve an existing policy/path. |
| Runtime virtual environment | `<scaffold>/.agent-knowledge-venv`; create or reuse it and ensure that path is ignored by the scaffold. |
| Harness targets | `codex`, `claude` and `copilot` in that order. Install/compile and bind those targets by default; preserve an explicit user or consumer target restriction with `--targets`. Use `--apm-mode prepare` when consumer installation is intentionally deferred. Automation being paused or unavailable never means passing an empty target list. Report unavailable or unauthenticated providers without asking the developer to choose a subset. |
| Automation | Name `knowledge-compound`, cadence `daily`, and the local system timezone where the provider offers durable scheduling. Treat provider-limited session schedules separately. |
| Publication | GitHub PRs by default. Derive the destination from the canonical knowledge checkout's verified remote, use its verified default branch and prefix `knowledge/`, and write the explicit source publication block. Preserve approved settings and explicit local-only choices. Missing destination/access is pending; follow the publication reference. |

Reuse registered IDs and preserve the selected configuration. New catalog IDs
are deliberate, confirmed vocabulary additions with definitions, not inferred
membership. Internal workspace/source IDs, producer roots, signal-directory
names, virtual-environment paths and default harness targets are derived and
reported, not extra questions. If a path is unsafe or ambiguous, give one
specific remediation. Publication is a setup default, not ambient CLI inference:
an absent source publication block still means disabled at runtime.

Before the first signal or runtime write, ensure the scaffold's `.gitignore`
contains `ai/signals/`, `ai/usage/` and `.agent-knowledge-venv/`. Add those local ignore
entries when the scaffold is a Git checkout; report the exact path if the
scaffold is not writable. For a custom usage directory, add its exact
relative ignore rule to the checkout containing it; report a path outside Git
as local-only storage. Preserve unrelated ignore entries. This is setup hygiene
and does not alter canonical knowledge or shell startup files.

For a new workspace, write `receipts: {enabled: true, directory: ./ai/usage,
retention_days: 30}` when the config is inside the durable scaffold. If it is
elsewhere, write an appropriate config-relative or absolute path to that same
scaffold's `ai/usage` directory. No additional user question is needed for
these defaults. `enabled: false` disables diagnostic retrieval/validation
collection; it does not disable required signal snapshots, dispositions or
drain evidence. Those safeguards continue to use the configured usage path.
Do not move archived inputs into the pending signal inbox or a knowledge source.
After creating the selected usage directory, run `doctor` in explicit write
mode and check its independent `readiness.receipts` result along with signal
write readiness. An unverified/missing path is not proof that evidence can be
written. The tool writes receipts and archives; the agent never writes their
JSONL records or performs manual archive/drain steps.

An invalid existing catalog or source/publication configuration needs a precise
field/path diagnostic. Do not silently rebuild it. Unknown scope/topic IDs can
be proposed for registration during onboarding after their meaning is confirmed;
ordinary CLI validation still rejects them until registered. A directory name,
ambient variable or previous installation is not evidence of organizational
membership. Keep credential values in the provider's native store or the
selected profile's external private env file, never in the registry, catalog,
workspace YAML, a signal, prompt, receipt, setup report or bootstrap file.

The workspace remains an explicit YAML file. Use the paired catalog/workspace
example in the onboarding reference and the installed `describe` schemas;
preserve an existing publication block only within its already approved scope.

Keep source, signal and origin paths distinct. The signal directory is
scaffold-root/ai/signals and must not overlap a configured canonical source.
Use a durable primary checkout or a deliberately non-project scaffold; do not
place the inbox in a temporary linked worktree.

Before reporting a fresh setup ready, resolve `scaffold_root` and `code_root`
from the configuration file and prove that the checkout which will originate
signals is strictly below `code_root`. Equality is invalid because it cannot
produce a stable relative project identity. Run one session-filtered
`signal list` from that checkout as part of readiness; repair the derived path
if it reports `origin-outside-code-root`.

## Verify and install the runtime

Resolve the setup script from this skill's own directory. Choose one mode:

| `--apm-mode` | Responsibility |
| --- | --- |
| `managed` (default) | The helper installs/verifies the runtime, runs APM install/compile, then binds and verifies package-owned hooks. Use when the consumer allows that flow. |
| `prepare` | Install/verify the runtime and selected workspace/profile. Report requested hooks pending; do not look up/run APM or edit consumer configuration. |
| `bind` | Install/verify the runtime, then bind and verify an already installed package's hook projections. Run no APM commands and generate no instructions or manifest. The consumer owns installation/compilation. |

For existing repositories, follow the integration reference's
`prepare -> repository-owned install/compile -> bind -> repository checks`
sequence. Bind updates package-owned hook resources and Copilot lock hashes;
it does not certify the consumer's instruction compilation. Local and remote
APM package references are supported, including remote subdirectory packages.
The helper discovers the unique installed hook bundle through `apm.lock.yaml`,
preserving APM's dependency identity and installation path. Keep portable
remote references in shared manifests; do not replace them with machine-local
paths to make binding work. Missing or ambiguous installed bundles need a
repository-owned APM install/repair before retrying bind.

Run with absolute paths and the selected targets:

~~~bash
python3 /path/to/knowledge-setup/scripts/setup_runtime.py \
  --workspace /work/knowledge/knowledge-workspace.yaml \
  --package /work/agent-knowledge-scaffold/.cache/dist/agent_knowledge_scaffold.whl \
  --consumer /work/orders-api
~~~

The helper requires uv and an installed CPython 3.11 or newer, creates or reuses
`<workspace-config-parent>/.agent-knowledge-venv` by default, installs the
supplied source checkout or wheel, then runs the installed `agent-knowledge`
describe, context and configured doctor. With `--profile` and optional absolute
`--settings`, the installed core resolves the effective selection and verifies
that its base path equals the bootstrap `--workspace` before binding hooks. It
verifies the actual interpreter version inside both new and reused environments;
`pyvenv.cfg` alone is not accepted. Reuse a compatible existing environment,
including newer Python versions; do not require a downgrade to 3.11. New
environments use an installed CPython matching `>=3.11`, without downloading
Python automatically. If none can be located, ask the developer to install a
supported version (for example, `uv python install 3.11`) before retrying.
It targets `codex,claude,copilot` by default. In `managed` mode it
runs APM install/compile for those targets; in `bind` mode the repository must
already have done so. APM installs the package-owned discovery
hook marker at the same time; setup then replaces that marker with the
absolute `agent-knowledge-hook` launcher installed in the verified venv. The
helper updates both Copilot entries in `apm.lock.yaml` (the dependency
`deployed_file_hashes` value and the matching deployment `content_hash`) after
that file is rewritten, then verifies one registration per requested target
and includes its path, source marker and resolved launcher command in the JSON
result. This keeps package-only uninstall safe after setup.
Review that result: missing registrations fail a binding stage, while `prepare`
intentionally leaves hooks pending. Configuration, source, runtime and receipt
failures remain failures. A read-ready workspace with environment-only
diagnostics can complete runtime and reminder-hook setup; credential activation
stays pending, without a loader command. `doctor` retains those diagnostics and
its failing overall status rather than pretending credentials are ready. A
setup result of `ok` certifies its selected stage, not every readiness dimension.
The helper does not print command output that could contain credentials. Pass
`--venv` when preserving a configured runtime path or when the durable
scaffold differs from the configuration parent. The installed context checks
that this path agrees with effective `setup.venv` when supplied. Pass `--targets` only for an explicit
harness override.

Check Git before signal work. Follow the publication reference to verify the
configured knowledge remote, base branch and intended GitHub account without
printing tokens. Missing Git, authentication or publication permission leaves
that publication path pending; do not register an automation that will
repeatedly fail.

Run the helper again to prove repeatability. An existing complete virtual
environment is reused; a partial or ambiguous directory is rejected for
inspection rather than overwritten. Keep the resulting launcher path visible
to the harness. Do not edit shell startup files or rely on a PATH change being
permanent: the automation prompt carries the absolute runtime/configuration
paths.

## Normalize harness activation

Treat provider differences as setup implementation detail. Read the helper's
`environment.providers` result and reduce it to one concrete outcome for each
installed harness; do not make the developer interpret the provider matrix,
assemble flags or edit generated hook files:

- `native-session-start` means setup completed the binding. Tell the developer
  only to start a new session in that consumer. For Claude, the package-owned
  `SessionStart` hook performs activation automatically.
- `cli-launch` means setup generated the complete value-free command. Show or
  execute that exact `command`; never reconstruct it from remembered flags.
  For Codex and Copilot it already contains the provider-specific behavior,
  including Copilot's Bash activation and redaction arguments.
- `not-configured` means the selected profile has no environment declaration.
  Do not present provider credential instructions.
- `pending` means credentials are not ready. Keep reminder hooks usable; show
  the profile-aware doctor command and ask the developer to fill/repair the
  private env file outside chat. Do not offer a credential activation command.
- `not-bound` means no activation was bound for that harness, including a
  `prepare` run or an omitted target. Complete installation and rerun setup in
  `bind` or `managed` mode with that target before presenting a start action.
- A desktop/app limitation is relevant only when the developer uses that app.
  State the reported limitation and provider-native alternative in one
  sentence; do not turn it into an onboarding questionnaire.

Detect the current harness and installed CLIs, apply every automatic
registration, and leave a copyable command only where a new CLI process is
technically required. If an installed and authenticated CLI is available,
verify the reported activation with a bounded presence-only probe that never
prints, transforms or hashes a credential value. Use an isolated working
directory and remove the mapped target from the probe's parent environment to
avoid a false positive. Retain only the marker and canary-absence result. Do not
spend provider credits merely to explain the matrix; a deterministic launcher
positive control is sufficient unless live proof was requested.

Selecting another knowledge profile later does not mutate credentials already
loaded into the current process. Present one common workflow: **run
`knowledge-setup` for the intended profile, then start a new harness session**.
For Claude, setup rebinding is required before the new session; Codex and
Copilot use the newly reported content-addressed launch command.

## Manage the package-owned discovery hook

APM owns the generated hook registrations. In a repository-owned integration,
perform install/uninstall through its registered commands, then use `bind` and
rerun repository checks. Do not bypass that contract with the generic recovery
commands below. Re-running binding setup or `apm install`
adopts the existing package marker and updates one entry in place; it does not
append a duplicate or remove unrelated entries. To remove the package-owned
hook and its other APM primitives, use the exact dependency key shown by
`apm deps list` (normally `_local/knowledge-agent-pack`) with
`apm uninstall`. Because uninstall removes the dependency from `apm.yml`,
re-enable it by installing the package source again, for example
`apm install --target codex,claude,copilot --no-policy /path/to/knowledge-agent-pack`.
Then rerun this setup helper with the same workspace, package and consumer
paths. Reinstallation restores the portable package marker; setup rebinds each
package-owned command to the verified absolute launcher and translates the
portable prompt event into Copilot's native `userPromptTransformed` event. Do
not rely on an ambient `PATH` entry for recovered hooks.
Do not edit another package's hook entry or copy this hook into a second
provider file.

The generated Codex and Claude records carry APM's `_apm_source` marker and
contain both `SessionStart` and `UserPromptSubmit`. The lifecycle response
contains discovery plus reflection; the prompt response contains reflection
only. Copilot uses native `sessionStart` for startup/resume and
`userPromptTransformed` to append the reflection reminder and exact session ID
to each model-facing user prompt. Copilot has no model-visible post-compaction
event; the next actual user prompt receives the reminder. Repository hooks in
Copilot prompt mode require that the working folder is already trusted. The
Copilot record is the package-named
`.github/hooks/knowledge-agent-pack-knowledge-discovery.json` file. Setup and
`doctor` report these paths. When the selected profile declares a ready
environment and setup binds hooks,
setup writes a content-addressed provider launcher under the managed venv. It
contains only the external file path and declared variable names, loads only
declared mappings, and starts Codex or Copilot without printing shell exports.
Codex replaces the launcher process; the launcher supervises Copilot so it can
remove its private temporary activation file on ordinary exit. Claude's `SessionStart`
command reads the selected external file through the guarded parser and writes
only declared exports through `CLAUDE_ENV_FILE`; its prompt hook and both other
provider hooks remain reminder-only. The setup report gives one-session Codex
and Copilot CLI launcher commands, enables Copilot's Bash startup support, and
uses protected internal aliases for native output redaction while restoring
declared targets only inside Copilot Bash tools. The mapped values do not
replace declared targets in Copilot's parent environment, so a mapping such as
`GH_TOKEN` cannot replace Copilot's own login. The Bash support preference is provider-global and
may remain enabled; no profile path or credential value is stored in that
setting. The private file is removed on ordinary wrapper exit; an abruptly terminated
wrapper may leave a mode-`0600` file in the operating-system temporary
directory. Setup states
that Codex/Copilot desktop have no generic per-task env-file injection. Never
edit shell startup files or claim that a hook child mutates its parent process.
The hook exposes the normalized provider name and exact `session_id` value to
the agent for signal provenance; setup does not invent or persist the opaque
session value.

A session activates one credential profile. Passing another knowledge
`--profile` later does not change loaded credentials; start a new harness
session instead after setup has activated the intended profile for that
consumer or reported a new CLI command. Token rotation in the same external
file may be picked up by the loader. Provider keychains and account state
remain provider-owned, so this is a convenience boundary rather than an
access-control sandbox.

One consumer hook can bind only one credential profile for new local Claude
sessions at a time. Running setup for another profile changes that binding for
future sessions while existing sessions retain their private value-free pin.
The profile named in a recurring-task prompt selects knowledge only; it cannot
override the shared hook's credential binding. Use a separate consumer/project
configuration or a provider-native cloud environment for simultaneous Claude
tasks that need different credential profiles.

## Configure durable compounding automation

After runtime/read readiness, signal/receipt write readiness, installed-skill
availability and the consumer's integration checks pass, inspect the selected
harness's native automation surface. Check credentials for dependencies that
the scheduled work actually uses: an unrelated blank service token does not
block local compounding, but required publication authentication does. A
pending credential environment cannot supply a working activation command;
use an already supported native provider environment only when its required
dependencies are verified. Do not switch to unrelated ambient credentials or
register a job known to fail. Search for this exact marker:

~~~text
agent-knowledge-compound:<workspace_id>
~~~

Compare resolved storage and routes as described in the profile reference.
There must be one automation owner for each signal store, including equivalent
profile aliases across providers. If the marker already
exists, update that task in place. If multiple tasks claim the same marker,
stop and ask the developer which one to keep. Do not create a second task.
Show how the provider pauses and removes the task, and leave those controls
visible in the setup report.

Use the provider reference for the selected harness. Codex Scheduled is a
durable provider-owned task surface. For other providers, follow the capability
boundary in their reference and report `provider-limited` instead of claiming
successful native registration. The task prompt should be short, stable and
explicit:

~~~text
Run the installed knowledge-compound skill using
/work/knowledge/.agent-knowledge-venv/bin/agent-knowledge with
--settings /work/local/profiles.yaml --profile work on every configured call. Process pending signals for this
workspace, follow its publication and drain policy, and report the run,
dispositions and retained/drained inputs. Do not merge PRs or force-push.
~~~

Add the marker to the task name or provider metadata, not to a secret or a
knowledge claim. Preserve the harness name, absolute config/runtime paths and
the provider's opaque automation/session handle when the provider exposes one.
For every provider, include the verified consumer routes and standing PR policy
from [publication setup](references/publication.md#include-every-participating-consumer).
Update that list when another consumer joins the shared store. Remove stale
agent-authored demands for separate publication permission that conflict with
the user's authorization; preserve explicit user exceptions. This policy lets
the task present PRs for review instead of stopping before it has a proposal.
The recurring task invokes knowledge-compound; it does not run APM compilation
or a repository daemon.

Trigger one run-now or one-shot execution before declaring that provider's
automation complete. The
verification should reach the installed skill and configured doctor, record
activity/session provenance when available, and report retained or drained
inputs. It does not need to create a production PR. If the provider lacks
durable native automation or requires unavailable authentication, report the
provider limitation and leave the workspace and signals unchanged. For Copilot
CLI, `/every` and `/after` are session-scoped conveniences rather than durable
unattended automation; recommend an explicitly authorized external scheduler
that invokes `copilot -p`, such as GitHub Actions, or a Copilot cloud automation.
Never create a remote workflow without user confirmation, and never silently
substitute a daemon, cron loop, launchctl mutation or hidden background process.

## Completion report

Show a concrete summary:

~~~text
Profile:   work (--settings /work/local/profiles.yaml)
Workspace: /work/knowledge/knowledge-workspace.yaml (workspace:example)
Runtime:   /work/knowledge/.agent-knowledge-venv/bin/agent-knowledge
Doctor:    /work/knowledge/.agent-knowledge-venv/bin/agent-knowledge --settings /work/local/profiles.yaml --profile work doctor
Environment: work, /Users/me/.config/agent-knowledge/work.env
Activation: one credential profile per new harness session
Harness activation:
  Claude: configured automatically; start a new session in this consumer
  Codex: /absolute/generated/profile-launcher.sh codex
  Copilot: /absolute/generated/profile-launcher.sh copilot
Usage:     /work/knowledge/ai/usage (diagnostics enabled, 30-day retention)
Sources:   example-knowledge; scopes org:example, group:commerce, repo:orders-api
Harness:   codex (native Scheduled task, daily at 09:00 Europe/London)
Automation: agent-knowledge-compound:workspace:example
Publication: example/knowledge, base main, branch prefix knowledge/

The setup is ready to run once now. Future runs invoke knowledge-compound;
they do not merge PRs or drain signals unless publication/disposition is verified.
~~~

Include the project recommendation's authored source and verified generated
outputs in the completion report. Helper success alone does not verify this
agent-authored integration; deferred compilation leaves that step pending.
For scaffold-derived instances, also report the checkout, both verified remote
identities, default push destination, base-branch tracking, initial push and
published bootstrap commit, plus the central-maintainer instruction and generated outputs. Report
the precise pending step if any; never include credentials in remote URLs.
Report the selected APM mode and runtime/read, signal/receipt write,
environment, hook, publication and automation readiness separately. Runtime and hook binding
can be complete when `doctor.readiness.read` is ready and only environment
diagnostics remain; retain its failing overall status in the report. A
`prepare` result is not a completed hook installation. Blank credential entries
are intentionally unfinished, not valid credentials: preserve strict literal
parsing, offer no activation command, and never insert fake values or use
ambient credentials to make checks pass. After the developer fills the private
file, rerun the same profile-selected `bind` or `managed` command, rerun the
consumer's checks, then start a new harness session. Automation readiness is a
separate per-provider result: complete only when the developer can locate,
pause and remove the durable task and can rerun doctor from that task's harness;
otherwise report the exact provider limitation or missing prerequisite.
