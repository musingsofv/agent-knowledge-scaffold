# Knowledge Agent Pack

knowledge-agent-pack is the minimal organization-neutral APM package
for the agent-knowledge command. It installs one concise discovery
instruction plus knowledge-setup and knowledge-compound skills for Codex,
Claude Code, Copilot and other APM-compatible targets. The Python
distribution remains the owner of the CLI contract, guide and authoring
templates.

See the repository's [harness support matrix](../../docs/harness-support.md) for
the verified Claude Code, Codex and Copilot capabilities and provider limits.

## Install in a consumer

For first adoption, the setup skill turns one scaffold clone into the user's
knowledge instance: `origin` publishes to their own private repository and
`scaffold` supplies upstream updates. It verifies that separation before
configuring compounding PRs. Follow the installed
[adoption procedure](.apm/skills/knowledge-setup/references/scaffold-upgrades.md#first-adoption-one-checkout-two-remotes);
existing instances reuse their repositories and remotes.

For a fresh consumer, install the APM CLI first, then install this package
from an explicit checkout path. Setup currently binds the installed local
dependency at `apm_modules/_local/knowledge-agent-pack`:

```bash
apm install --target codex,claude,copilot --no-policy \
  /path/to/agent-knowledge-scaffold/packages/knowledge-agent-pack
apm compile --target codex,claude,copilot --force-instructions
```

For a repository with owned APM commands, invoke `knowledge-setup` before
running these generic installation commands. The skill inspects the consumer's
manifest, pinned generation and local catalog. Its helper supports
`--apm-mode prepare` (runtime/profile only), followed by the repository's own
registered install/compile and `--apm-mode bind` (bind existing package-owned
hooks). Bind updates installed hook resources and Copilot lock hashes; run the
repository's checks afterward. The default `managed` mode retains the complete
helper-owned flow. See the
[existing-repository reference](.apm/skills/knowledge-setup/references/existing-repository.md)
for the exact integration boundaries and commands.

The normal path is to invoke `knowledge-setup`; it checks for an installed
CPython 3.11.x, creates the scaffold-local runtime and installs the Python
package for you. If Python 3.11 is unavailable, setup reports the install
remediation and does not fall back to another interpreter. For a direct smoke
or deliberate manual override, install the Python runtime separately. During
local development the wheel can be installed into a dedicated environment:

```bash
uv venv --python 3.11 --no-managed-python .agent-knowledge-venv
uv pip install --python .agent-knowledge-venv/bin/python \
  /path/to/agent-knowledge-scaffold
export PATH="$PWD/.agent-knowledge-venv/bin:$PATH"
```

From the same harness, verify the installed runtime and pass an explicit
workspace configuration or a registered profile:

```bash
command -v agent-knowledge
agent-knowledge describe
agent-knowledge profiles list
agent-knowledge --profile personal doctor
# With a non-default registry:
agent-knowledge --settings /path/to/config.yaml --profile work doctor
# Direct workspace paths remain available without profile environments:
agent-knowledge --config /path/to/workspace/knowledge-workspace.yaml doctor
```

`describe` is the binding between the APM instruction and the installed guide
and templates. The instruction never references this repository's `src/` or
`docs/` directories. No organization, source root, scope hierarchy or
technology list is assumed. The package installs one advisory discovery hook
for each selected provider. Codex and Claude receive reflection on
`UserPromptSubmit`; setup translates the portable Copilot projection into
native `sessionStart` plus `userPromptTransformed`, so Copilot also receives
reflection on each model-facing user prompt. Native `sessionStart` handles a
Copilot resume. Copilot has no model-visible event after in-session compaction;
always-on discovery instructions remain and the next user prompt receives the
reflection reminder only. The package does not install a scheduler.

The hook is package-owned and idempotent. APM first records one
`agent-knowledge-hook` marker for each selected provider; `knowledge-setup`
then replaces that marker with the absolute `agent-knowledge-hook` executable
from the verified 3.11 environment. The setup report includes the exact
launcher command and provider registration path, and reconciles both Copilot
hook hashes in `apm.lock.yaml` so package-only uninstall remains safe after
setup. Hand-authored hook entries remain in place. Inspect `apm deps list` for
the package key before removal; normally
`apm uninstall _local/knowledge-agent-pack` removes only this package's
primitives. Re-enable it by installing the package source again with
`apm install --target codex,claude,copilot --no-policy /path/to/knowledge-agent-pack`.
The hook emits a short discovery/reflection reminder, the normalized provider
name and the exact opaque provider session ID. The agent copies those values
into `origin.harness` and `origin.session_id`; the hook never reads knowledge
or signals. The installed guide and skills remain the authoritative
instructions.

When a profile declares an external environment, configure its label, private
env-file path and variable mappings once, then invoke `knowledge-setup`.
Setup owns the provider differences, applies the required configuration and
returns the exact start action to follow. It reports app limitations only when
they apply; users do not assemble provider flags or edit hook files. Detailed
provider mechanics remain in the setup skill's agent-facing references.
Intentionally blank env assignments remain invalid credentials, but do not
block runtime or reminder-hook setup when the workspace is otherwise read-ready.
Setup reports activation pending and provides no loader command; doctor retains
its environment diagnostics and failing overall status. Fill values privately,
rerun the same selected binding mode and repository checks, then start a new
harness session from its returned action.

One harness session uses at most one credential profile. To switch, ask or run
`knowledge-setup` for the target profile and then start a new session using its
newly reported action. Passing another `--profile` changes knowledge selection
only, and starting a new Claude session alone does not rebind the configured
credential profile. Use separate consumer/project configurations or
provider-native cloud environments for simultaneous tasks that require
different credential profiles.

Profile users run `agent-knowledge --profile <label> doctor`, adding
`--settings /path/to/config.yaml` for a non-default registry. Direct workspace
users may instead run `agent-knowledge --config <workspace.yaml> doctor`; that
path has no profile environment. `doctor` verifies the running launcher,
selected workspace, catalog, source roots and signal/usage-storage readiness
without modifying the host.

## First-run setup

Invoke knowledge-setup from the selected harness. It reads existing business
context and configuration, asks only about missing or conflicting facts, and
proposes a small catalog and configuration path for confirmation. It handles
empty catalogs without asking you to invent IDs. It then derives
the workspace identity, source/catalog paths, producer root, signal inbox and
scaffold-local runtime. Managed setup compiles all three supported APM targets
(`codex`, `claude`, `copilot`) and binds their hooks by default. An explicit
consumer target restriction is preserved; repository-owned setup uses the
prepare/install/compile/bind sequence above. It configures durable
automation only through a supported, authorized provider surface; unavailable,
unauthenticated or session-only scheduling is reported without asking for a
different target subset. It uses a daily local-time cadence by default where
durable scheduling is available. Fresh setup defaults to GitHub PR publication
using the canonical knowledge checkout's verified remote and default branch,
with prefix `knowledge/`. It includes that destination in the setup proposal and
writes explicit configuration. Existing settings and explicit local-only choices
are preserved; unresolved destination/access is pending. The runtime still treats
an absent publication block as disabled. See the setup skill's
[publication procedure](.apm/skills/knowledge-setup/references/publication.md).
It defaults diagnostic receipts to enabled with 30-day
retention in `<scaffold>/ai/usage` and keeps that directory, `ai/signals/` and
`.agent-knowledge-venv/` ignored in a Git scaffold. Receipt paths resolve from
the config, so setup writes the appropriate path when it lives elsewhere.
Disabling diagnostics preserves required compounding archives and drain evidence.
The skill creates usage storage and checks write readiness through `doctor`. Confirm actual applicability
boundaries; a directory name does not establish scope membership. Existing
configuration and unrelated catalog records are preserved on repeat setup.
It uses the bundled
knowledge-setup/scripts/setup_runtime.py helper to create or reuse a virtual
environment, install the runtime, run describe and doctor, and compile all
three APM targets by default. The helper never edits shell startup files or
registers a scheduler.

Setup can register a label in `~/.config/agent-knowledge/config.yaml`, preserving
existing defaults and comments through its checked registry helper. The installed
guide owns profile selection and overrides. For named-profile onboarding, setup
also writes the consumer's profile recommendation into its authored instruction
source and verifies the regenerated harness outputs. Existing recommendations
are reused or deliberately resolved, never duplicated or silently replaced.
This agent-owned step preserves the user's session override and leaves the
generic hook unchanged. Use one explicit label (and registry
path) throughout a session. If the profile declares an environment, provide its
env-file path and variable mappings during setup and follow the exact reported
start action. To change credential profiles, run setup for the target label and
then start a new session from its new action; `--profile` alone does not switch
loaded credentials. Aliases share a signal-store owner.

For a verified scaffold-derived central knowledge checkout, setup separately
persists a maintainer route in that checkout's authored instructions and checks
its generated outputs. The [upgrade procedure](.apm/skills/knowledge-setup/references/scaffold-upgrades.md)
ships inside the installed skill; application hooks stay generic. Existing
upstream identity is verified, and unrelated histories are not joined implicitly.

The skill verifies runtime/read and signal/receipt write readiness before
automation, along with installed skills and the dependencies the run actually
uses. Unrelated unfinished service credentials do not block local compounding;
required publication credentials do.

The skill configures one durable automation owner per signal store where the
provider offers an authorized persistent surface. Its marker is
`agent-knowledge-compound:<workspace_id>`. Codex Scheduled is supported by a
provider reference. Copilot CLI `/every` and `/after` are session-scoped and do
not qualify as unattended daily automation; the Copilot reference recommends an
explicitly authorized external scheduler invoking `copilot -p` or a cloud
automation. The task invokes knowledge-compound with the absolute launcher,
registry and explicit profile, or a direct configuration path, and exposes
pause/remove controls. It never relies on the global default. Run it once
immediately to verify the installed launcher and activity log; do not replace a
provider task with a hidden daemon or background loop.

## Compounding

knowledge-compound reads the advisory activity log before selecting signals,
keeps complete-byte snapshots, discovers existing owners through the explicit
catalog/search contract, and validates proposed canonical changes. Its owner
discovery reference distinguishes skill-only corrections, independently useful
central knowledge and findings requiring both. Existing local skills are updated
in their authoring repository through an authorized publication route; a
skill-only correction needs no knowledge document. For central changes, it reuses
the current user's eligible knowledge PR or creates one only when validated
changes exist. A human merges the PR. Unavailable publication routes and signals
requiring changes across repositories remain deferred. It drains only selected,
unchanged inputs after verified publication or an explicit no-write
disposition; failures, edits and uncertain responses remain inspectable.
