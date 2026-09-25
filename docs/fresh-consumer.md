# Fresh APM consumer setup

This is the setup path for a new organization or project using the neutral
knowledge scaffold. It installs the APM discovery instruction and the Python
`agent-knowledge` runtime independently. An existing repository with owned APM
commands uses the staged integration below to preserve its generation contract.
The scaffold does not select an organization, source root, scope hierarchy or
technology stack for you.

## Create your knowledge instance

Clone the scaffold with its Git history into one durable directory, typically
`knowledge`, and ask the bundled
[`knowledge-setup`](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/SKILL.md)
skill to set it up as your knowledge instance. Setup proposes your own private
GitHub repository, confirms the owner/name when not already supplied, and
connects the same checkout to two remotes:

- `origin`: your knowledge repository, where commits and compounding PRs go.
- `scaffold`: the verified upstream scaffold, where implementation updates come from.

The skill file is available inside the clone before native skill installation.
Open the clone in your agent and ask: "Read
`packages/knowledge-agent-pack/.apm/skills/knowledge-setup/SKILL.md` and set up
this checkout as my knowledge instance."

You do not need another local scaffold checkout. Setup preserves the cloned
history, verifies the initial push and publication destination, and records
maintenance instructions. It then publishes the non-secret instance bootstrap,
including the catalog and authored instructions; local settings and credentials
remain ignored. Existing instances reuse their remotes. GitHub's
**Use this template** creates separate history and requires additional baseline
handling; a normal clone supports future merge-based updates directly. See the
installed [adoption and upgrade procedure](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/scaffold-upgrades.md).

## Prerequisites

Install CPython 3.11 or newer and `uv`; the installation/compilation stage also needs
APM. Runtime-only preparation and binding do not need an APM executable. The
setup skill targets all
three supported harnesses by default and reports any provider that is absent
or unauthenticated:

```bash
apm --version
uv --version
codex --version       # report if unavailable
claude --version      # report if unavailable
copilot --version     # report if unavailable
```

## Install the runtime

For a published Python distribution, the normal path is to invoke
`knowledge-setup`; it requires an installed CPython 3.11 or newer, creates
`<scaffold>/.agent-knowledge-venv` and installs the runtime for you. If no Python
3.11+ interpreter is installed, setup reports the remediation (for example,
`uv python install 3.11`) and stops. The commands below remain useful for a
direct smoke or a deliberate manual override. Install the released
`agent-knowledge-scaffold` package into a dedicated environment. During local
development, install the checkout or a wheel built from it:

```bash
uv venv --python 'cpython>=3.11' --no-python-downloads .agent-knowledge-venv
uv pip install --python .agent-knowledge-venv/bin/python \
  /path/to/agent-knowledge-scaffold
export PATH="$PWD/.agent-knowledge-venv/bin:$PATH"
```

Verify the exact process that the harness will use:

```bash
command -v agent-knowledge
agent-knowledge describe
```

The `describe` response reports the installed guide and authoring template
paths. Read those paths from the response; do not point an agent at this
checkout's `src/` or `docs/` directories.

## Install and compile the APM package

For a fresh consumer that permits helper-owned APM installation, use the
explicit local package source below. The setup binder currently locates
`apm_modules/_local/knowledge-agent-pack`; arbitrary marketplace/registry
installation layouts are not covered by this binding contract:

```bash
apm install --target codex,claude,copilot --no-policy \
  /path/to/agent-knowledge-scaffold/packages/knowledge-agent-pack
apm compile --target codex,claude,copilot --force-instructions
```

The package owns one discovery instruction and one advisory discovery hook.
Compilation projects the instruction to the selected harnesses (`AGENTS.md`,
`CLAUDE.md` and `.github/copilot-instructions.md` where supported). Installation
registers a provider-owned `agent-knowledge-hook` marker for the selected
providers. Codex and Claude have `SessionStart` plus `UserPromptSubmit`
registrations. Setup converts Copilot's portable projection to native
`sessionStart` plus `userPromptTransformed`. All three CLIs receive reflection
on each model-facing prompt; startup and resume receive discovery plus
reflection. Copilot has no model-visible event after in-session compaction. Its
always-on discovery instructions remain, and the next user prompt receives the
reflection reminder only. The package does not install a scheduler or copy a
knowledge corpus. The setup skill replaces the marker with the absolute
launcher from the verified Python 3.11+ virtual environment.

APM writes package-owned hook records under `.codex/apm-hooks.json`,
`.claude/apm-hooks.json` and
`.github/hooks/knowledge-agent-pack-knowledge-discovery.json`. Before setup,
the generated provider files contain only the package marker. After setup they
point at the absolute installed launcher reported by the setup result.
Re-running setup updates that one owned command in place and reconciles the
dependency and deployment hashes for the standalone Copilot file;
hand-authored provider hook files remain in place. To remove the package, use
the exact key from `apm deps list`, normally `apm uninstall
_local/knowledge-agent-pack`; re-enable it by installing the package source
path again, then rerun the same `knowledge-setup` flow. Reinstallation restores
the portable package marker; setup rebinds every package-owned command to the
absolute launcher in `.agent-knowledge-venv` and translates Copilot's prompt
event to `userPromptTransformed`. Do not rely on an ambient `PATH` entry after
recovery. Copilot prompt mode loads repository hooks only for an already trusted
working folder; `-C` and `--add-dir` do not grant that trust.

When a hook response includes `Provider harness (...)` and `Provider session ID
(...)`, preserve those values exactly as `origin.harness` and
`origin.session_id` in a harness-origin signal. To avoid duplicate observations,
list the pending inbox with the same session value before recording:

```bash
agent-knowledge --config /path/to/workspace/knowledge-workspace.yaml signal list \
  --request-file - <<'YAML'
include_shared: true
session_id: "opaque-provider-session-id"
limit: 50
YAML
```

The result is a metadata preview with body and line ranges. Inspect likely
equivalents with ordinary file tools, then record at most one concise signal
for the same observation. A harness-origin signal without that exact session
ID is rejected; manual signals may omit harness provenance.

## Integrate with an existing repository

Invoke `knowledge-setup` and let it inspect the consumer's instructions,
manifests, pinned APM commands, targets and local skills before editing them.
It supports three helper modes:

| Mode | Effect |
| --- | --- |
| `--apm-mode managed` (default) | Verify/install runtime, run APM install/compile, then bind package-owned hooks. |
| `--apm-mode prepare` | Verify/install runtime and selected workspace/profile; no APM lookup/command or consumer-configuration changes. Requested hooks remain pending. |
| `--apm-mode bind` | Verify/install runtime and bind an already installed package's hook projections; no APM commands or instruction/manifest generation. |

For a strict consumer, use `prepare`, then register the exact package and its
resources through the repository's approved integration. Run its own APM
install/compile commands, run helper `bind`, and run repository checks against
the final state. Bind updates installed package-owned hook resources and the
Copilot lock hashes, so checking only before bind is insufficient. Preserve
local skills and deliberate output/ownership/index checks. A `--local-only`
compiler needs an explicit composition change to include the package's one
source-owned discovery instruction; merely declaring the dependency does not
import it. No manual hook copy or alternate implementation is needed.

The setup skill's [existing-repository reference](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/existing-repository.md)
contains the exact prepare/bind commands and integration checklist. Its Python
`--package` input and the consumer's APM dependency are separate installations.
All three targets remain the default; an explicit consumer restriction such as
`--targets codex` is supported. A successful prepare report does not mean hooks
are installed or the consumer's instruction generation has been verified.

If the canonical source is a verified scaffold-derived knowledge checkout,
setup also persists a brief central-maintainer instruction there and checks its
compiled outputs, separately from the application's profile recommendation.
The installed setup skill ships the [upstream maintenance procedure](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/scaffold-upgrades.md),
including verified remote configuration per clone and reviewed upgrade merges.
Arbitrary knowledge sources and application repos do not inherit that role;
setup does not automatically join unrelated histories or apply upgrades.

## Register a convenient label

During `knowledge-setup`, the agent suggests a profile label from your business
or project name and confirms it with the workspace choices. For the first
profile it proposes making that label the default. Later additions preserve
your default. Registry edits preserve existing comments/entries and reject a
concurrent change before replacing the file. Setup verifies the selected base
workspace and effective venv before binding hooks.

The registry lives at `~/.config/agent-knowledge/config.yaml`; use `--settings`
for another path. It maps names to workspace YAML files with optional validated
overrides. After setup:

```bash
agent-knowledge profiles list
agent-knowledge --profile personal context
agent-knowledge --profile personal doctor
# With a non-default registry:
agent-knowledge --settings /path/to/config.yaml --profile work doctor
```

Tell the agent "Use personal for this session" or "Use work for this session."
It carries that explicit name on every configured command. A project may
recommend a default; an explicit user choice takes priority. During named-profile
onboarding, the setup agent writes the selected name and registry location into
the consumer's existing authored instruction source, compiles through its owned
APM workflow and verifies the generated harness instructions. You do not add
that recommendation manually. Existing recommendations are reused; conflicts
are resolved before replacement. This is separate from the user-wide registry
default and the generic hook. Changing a session
selection does not rewrite the registry. After compaction the agent recovers
its retained selection or asks if it has been lost. Hooks require no toggling.
Native automation prompts pin the absolute launcher, registry and name; aliases
for one signal store reuse one owner. Direct-path setup remains supported.
See the [shared guide](agent-contract.md#select-a-knowledge-profile-for-this-session)
for the YAML format, override rules, path origins and isolation limits.

A label may also declare a private external env file and named mappings such as
`GITHUB_V_TOKEN -> GH_TOKEN`. Setup suggests
`~/.config/agent-knowledge/<profile>.env` and mode `0600`; it confirms names and
purpose but never asks you to paste values into chat or stores values in YAML.
`context` shows safe metadata and `doctor` checks the file and declared source
names without printing values. You may create blank assignments and fill them
privately later. They are not valid credentials: the strict parser continues to
report environment diagnostics. With a valid, read-ready workspace, setup can
still complete runtime and discovery/reflection hook binding. Credential
activation stays pending, with no loader command; `doctor` retains its overall
failure and separate readiness results. After filling the file with non-empty
literal assignments, rerun the same profile-selected `managed` or `bind` setup
command and any repository checks, then follow the new-session action.

Configure the profile label, env-file path and mappings once, invoke
`knowledge-setup`, then follow the exact start action in its report. Setup owns
the provider differences and explains an app limitation only when it applies.
One harness session uses at most one credential profile. To switch, ask or run
`knowledge-setup` for the target profile and then start a new session using the
newly reported action. Passing another `--profile` changes knowledge selection
only; starting a new Claude session alone does not rebind the configured
credential profile. Provider keychains remain independent, so this is not a
hard access-control boundary. Provider mechanics are kept in the installed
setup skill's agent-facing references.

## Configure a workspace

Create a workspace YAML file with your own catalog and source roots. The
committed fictional example is useful for a first configuration check:

```bash
agent-knowledge --config /path/to/workspace/knowledge-workspace.yaml doctor
agent-knowledge --config /path/to/workspace/knowledge-workspace.yaml context
```

Configuration is explicit. The launcher never infers a workspace from the
current directory or ambient organization variables. Follow the installed
guide for catalog discovery, selective search, progressive file reads, links,
validation and signal capture. This direct `--config` path does not activate a
profile environment; profile users run `doctor` with `--profile` and optional
`--settings` as shown above.

Run `doctor` whenever the installation or workspace configuration changes. It
checks the running launcher, explicit configuration, catalog, source roots and
signal and usage-storage readiness without inferring settings or modifying
the host. Explicit write mode probes existing signal and usage directories;
read mode leaves their writability unverified.

## First-run setup and automation

Invoke the installed knowledge-setup skill for the first setup. It reads your
existing business/product documentation and configuration, then proposes the
workspace path and a small catalog of scopes, topics and named entities. If the
context is unclear, it asks a short set of targeted questions; you confirm the
business choices rather than inventing schema IDs. A solo business can start
with one scope and one empty source. Setup registers confirmed vocabulary,
preserves existing definitions and configuration, then derives the workspace
identity, source/catalog paths, producer root,
signal inbox, usage evidence directory and scaffold-local virtual environment.
Managed setup compiles all three supported APM targets (`codex`, `claude`,
`copilot`) and binds their hooks by default; repository-owned setup separates
preparation, installation/compilation and binding as described above. Scheduled
automation readiness is reported separately for each
provider. Missing or unauthenticated providers are reported individually;
setup does not ask you to choose a subset. It uses a daily cadence in the local
timezone where a durable provider surface is available.
Fresh setup defaults to GitHub PR publication for human review. It derives the
destination from the canonical knowledge checkout's verified GitHub remote,
proposes its verified default branch and prefix `knowledge/`, then writes an
explicit source publication block as part of the agreed setup. It never guesses
the destination from the application repo or reusable package checkout. Existing
publication choices and explicit local-only operation are preserved. Missing or
ambiguous remotes or unavailable authentication leave publication pending with
one targeted next step; they do not silently disable the intended workflow.
See the setup skill's [publication procedure](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/publication.md).
The CLI still treats an absent publication block as disabled. Compounding creates
no empty PR and never merges automatically; unresolved updates retain signals.
The skill never reads organization membership from a directory name or ambient
variable. It then runs the bundled runtime helper, creates or reuses
`<scaffold>/.agent-knowledge-venv`, installs the runtime, verifies describe and
configured doctor, ensures `ai/signals/`, `ai/usage/` and
`.agent-knowledge-venv/` are ignored by the scaffold, and reports each APM target's result.
For a configured profile environment, the onboarding user supplies one profile
label, an external env-file path and the variable mappings they intend to
expose. `knowledge-setup` applies the provider-specific configuration and
reports one exact start action to follow. It reports app limitations only when
they are relevant; users do not assemble provider flags or edit hook files.
Changing credential profiles always requires running setup for the target
profile and then starting a new session from its reported action. Use separate
consumer/project configurations or provider-native cloud environments for
simultaneous scheduled tasks that need different profiles. Provider mechanics
remain in the setup skill's agent-facing references.

Usage defaults are `receipts: {enabled: true, directory: ./ai/usage,
retention_days: 30}`. Paths resolve from the workspace config; setup points a
config outside the scaffold at the durable scaffold's usage directory.
Diagnostic collection is optional. Required compounding input snapshots and
drain evidence remain enabled even with `receipts.enabled: false`, using the
same path. Usage is local evidence, separate from canonical knowledge and
pending signals. Setup creates and ignores the directory and checks it with
`doctor` in write mode; no routine storage questions are needed.

Before registering automation, setup verifies runtime/read readiness, signal
and receipt writes, installed skill availability and the dependencies that run
actually needs. Unrelated blank service credentials do not prevent local
compounding; missing authentication required for publication does. Do not
register a job known to fail or mask missing credentials with an unrelated
ambient account.

The skill configures one durable automation owner per signal store, using the
marker `agent-knowledge-compound:<workspace_id>`, when the provider offers an
authorized persistent surface. The automation invokes knowledge-compound with
the absolute configuration path. Run it once from the provider's run-now
control and retain the pause/remove controls. Codex Scheduled is a supported
native surface. Copilot CLI `/every` and `/after` remain attached to one open
interactive session, so durable Copilot work needs an explicitly authorized
external scheduler invoking `copilot -p` or a cloud automation. The provider
owns scheduling; this repository does not run a daemon, cron loop or launchctl
mutation. See the provider references in the installed knowledge-setup skill.
