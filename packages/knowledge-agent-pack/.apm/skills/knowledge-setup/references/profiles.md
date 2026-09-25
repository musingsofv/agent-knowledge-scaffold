# Register and verify a named profile

Read this when setup adds or changes a label. The installed guide owns runtime
selection and override semantics. This reference owns the setup write procedure.
It is an agent-facing adapter reference: the developer supplies the profile,
env-file path and variable purposes once; the setup skill chooses and applies
the harness-specific mechanism.

1. Inspect the registry at `~/.config/agent-knowledge/config.yaml`, or the user's
   explicit alternative. Suggest a lowercase label from the supplied business
   or project name. Ask once if that name is unclear. Confirm the label together
   with the workspace choices; propose the first label as default. Preserve an
   existing default when adding another label. Direct-path setup is also valid.
2. Inspect an existing mapping before editing. Reuse an unchanged mapping.
   A name pointing elsewhere needs a deliberate replace-or-new-name choice.
   Preserve unrelated entries, overrides, comments and formatting. Never
   rewrite a default to select a session. Record the SHA256 of the complete
   inspected bytes, or `missing` for a new registry.
3. Prepare the proposed complete YAML in a candidate file outside the corpus.
   Show the focused diff. Use `knowledge-profiles.v1` and the installed schema.
   Typical first setup:

   ```yaml
   schema_version: knowledge-profiles.v1
   default_profile: personal
   profiles:
     personal:
       config: /work/personal/knowledge-workspace.yaml
       environment:
         file: /Users/me/.config/agent-knowledge/personal.env
         variables:
           github:
             from_env: GITHUB_V_TOKEN
             expose_as: GH_TOKEN
             description: Personal GitHub repository access
   ```

   `environment` is optional. It stores only an external path, exact variable
   names and a human description. Never put values, defaults or command
   substitutions in registry YAML. Suggest the developer's absolute home path
   ending in `.config/agent-knowledge/<profile>.env` when they have no preferred
   location; authored `~` paths are invalid and must be expanded before writing
   the registry. The file uses strict literal `NAME=value` lines, may prefix a line
   with `export `, must be UTF-8, current-user owned and mode `0600` or stricter.
   Values are literal and do not use quote wrappers or interpolation. Blank
   assignments are allowed as unfinished setup placeholders, not valid
   credentials. The strict parser reports them as environment-not-ready while
   independent runtime and reminder-hook setup can continue. Ask the developer
   to populate/rotate it outside chat; do not print or copy values.
   `expose_as` must be a unique tool credential name, not a shell, runtime or
   provider-control name, or anything in the setup-owned `_ak_` namespace. Keep mappings focused; the
   complete value-free declaration must fit the bounded Claude session pin and
   setup rejects it before hook binding if it does not.

4. Use the installed runtime's Python to publish the candidate through
   `scripts/register_profile.py`, resolved relative to this setup skill:

   ```bash
   /work/personal/.agent-knowledge-venv/bin/python /installed/knowledge-setup/scripts/register_profile.py \
     --candidate /work/local/profile-candidate.yaml \
     --settings /work/local/profiles.yaml --expected-sha256 missing
   ```

   For an existing file, pass its inspected hex SHA256 instead of `missing`.
   The helper validates through the installed core and atomically publishes
   the exact candidate bytes after a change check. A conflict requires
   reinspection and a new candidate; do not retry with a new hash blindly.
   This is an internal setup helper, not an agent-written receipt or a new
   public CLI configuration language. Do not add a round-trip YAML dependency.

5. If the runtime does not exist yet, first run `setup_runtime.py` with explicit
   `--workspace`, `--venv`, `--package`, `--consumer`, the intended `--targets`
   and `--apm-mode prepare` to bootstrap without looking up APM or changing
   consumer configuration. Register the reviewed profile, then rerun with the
   selected name and `managed` mode, or complete the
   [repository-owned integration](existing-repository.md) before `bind`:

   ```bash
   python3 /installed/knowledge-setup/scripts/setup_runtime.py \
     --workspace /work/personal/knowledge-workspace.yaml \
     --venv /work/personal/.agent-knowledge-venv \
     --package /work/agent-knowledge-scaffold \
     --consumer /work/app \
     --settings /work/local/profiles.yaml --profile personal --apm-mode managed
   ```

   Explicit paths bootstrap installation; the installed core resolves the
   profile for `context` and `doctor`. The helper rejects a different base
   workspace or effective `setup.venv` before binding hooks. Preserve an existing
   runtime and pass its matching path; do not silently install another venv.
   An installation failure leaves registry/workspace choices available for a
   later retry and reports the incomplete stage. Recheck the final context.
   `doctor` reports environment readiness separately. If only environment
   diagnostics remain and reads are ready, setup can bind reminder hooks while
   credential activation stays pending. The report retains doctor's diagnostics
   and overall failure, but a successful setup stage returns `ok`. It provides
   no activation command until credentials are ready. Other configuration,
   runtime, source or receipt failures still stop setup. Inspect the separate
   readiness fields rather than treating `ok` as complete credential readiness.

6. For named-profile onboarding of this consumer, persist its project
   recommendation using the procedure below before reporting setup complete.
   Prepare its authored source before the chosen compilation stage; if already
   compiled, regenerate through the same owned commands and rebind as needed.
7. Compare the resolved physical signal store and configuration route with any
   existing automation before registration. Keep the workspace marker and one
   owner for the store across all providers. Equivalent aliases reuse the task;
   incompatible source/scope/publication routes for the same store need a
   configuration decision, not a competing task. Do not alter unrelated tasks.
   Hooks remain one generic installation per consumer, independent of labels.

## Persist the consumer's profile recommendation

The setup agent owns this step. Registering a profile, setting a user-wide
default or binding a hook does not persist the consumer's intended profile.
Use the name and registry verified by the installed `context` response, not
the checkout's name. Do not change the registry default to route one project.

Find the consumer's existing authored APM instruction source and compilation
command. Put one short recommendation in the source that applies to this
consumer, preserving unrelated instructions and narrower product boundaries.
Reuse an equivalent recommendation. If a different profile or registry is
already specified, resolve whether this setup intends to replace it; an
explicitly requested replacement is sufficient authorization. A temporary
session choice or credential-only rebind must not rewrite project defaults.

For the standard per-user registry, use this shape with the verified label:

```text
Default to knowledge profile personal in the standard user registry
(~/.config/agent-knowledge/config.yaml), unless the user explicitly selects
another profile for this session. Follow the installed agent-knowledge guide
and retain the selected profile on every configured call.
```

For a nonstandard registry on one machine, replace the standard-registry phrase
with its verified durable absolute path and state that configured calls retain
`--settings /absolute/registry.yaml`. For a shared checkout, keep machine paths
out of the authored recommendation: say to use the named profile from the local
registry selected by `AGENT_KNOWLEDGE_SETTINGS` or the standard user location.
Follow [Portable hooks](portable-hooks.md) to configure and verify that route
in each environment. The `~` above describes the standard user
location; it is not a literal path to write into registry YAML or pass to the
CLI. Keep this instruction limited to routing: do not copy credential values,
env mappings, query rules or the guide's complete selection procedure into it.

If a fresh consumer has no authored instruction source, add one through its
approved APM layout, such as `.apm/instructions/project-knowledge.instructions.md`
with valid description frontmatter. Existing repositories use their registered
sources and grammar; do not assume this example path is allowed. Do not edit a
generated `AGENTS.md`, an installed dependency or the reusable package's generic
discovery instruction to hold a consumer-specific preference. Hooks stay generic.

Run the chosen compilation flow: managed setup after authoring, or the
repository-owned commands before `bind`. Then inspect the instruction output
actually loaded by each selected harness, such as `AGENTS.md`, `CLAUDE.md` or
Copilot instructions. Verify the intended profile and registry survived
compilation, no conflicting applicable recommendation remains, and the user's
session override is preserved. Run consumer consistency checks after binding.
Resolve the explicit selector with `context` and `doctor` to verify the expected
workspace. An unchanged repeat setup must not append another recommendation.
Report the authored source, verified outputs and selected route; an uncompiled
or missing recommendation remains pending even if the runtime helper succeeds.

Direct `--config` setup does not invent a profile. Preserve its explicit
workspace route in the consumer's existing instructions where needed. Creating
another label alone or switching this session does not authorize changing a
repository recommendation.

## Pin scheduled work

For a profile-based automation, pin **all three** values in the task prompt:

```text
Run the installed knowledge-compound skill using
/work/personal/.agent-knowledge-venv/bin/agent-knowledge
with --settings /work/local/profiles.yaml --profile personal on every configured
call. Process pending signals using the selected context and publication/drain
policy. Report dispositions and retained/drained inputs. Do not merge PRs or
force-push. Marker: agent-knowledge-compound:workspace:personal
```

For direct setup, substitute `--config /absolute/knowledge-workspace.yaml`.
Include the participating consumer routes and standing compounding PR policy
from [publication setup](publication.md#include-every-participating-consumer).
When another consumer shares the profile/store, update that same task's routes;
do not add a separate publication opt-in or narrow the task to its working directory.
Do not depend on the global default. Changes to cadence, launcher or provider
registration take effect through setup updating the native task. Profile edits
affect future explicit CLI calls; active compounding runs reject changed routing.

## Activate credentials for a new session

Knowledge selection and credential activation are related but different. The
CLI can query another knowledge profile at any time. It cannot mutate the
environment of the already-running harness. One harness session therefore
activates at most one credential profile; rerun setup for the intended profile
and then start a new session to use another.
Scheduled tasks pin one profile. Never rewrite `default_profile` or a shared
`active` pointer to switch credentials.

After filling an unfinished env file, rerun the same profile-selected
`managed` or `bind` command, plus repository-owned checks when applicable.
Do not source unrelated ambient credentials or add fake values to make a probe
pass. A `prepare` run does not activate credentials even when they are ready.

Before that new session, rerun binding setup with the intended profile. This
rebinds future Claude sessions in that consumer and returns the content-addressed Codex
and Copilot commands for the same profile. Starting a new Claude session without
rebinding setup keeps the currently bound profile.

With ready credentials, binding setup creates a content-addressed, mode-`0700`
provider launcher under the managed venv. It contains the env-file path and mappings, not values. A changed
mapping gets a new launcher path. Rotation inside the same external file is
observed when a later provider session starts.

The table below is for setup execution and troubleshooting. Do not ask the
developer to select among these mechanisms or manually reproduce their flags.
Use the exact `environment.providers` status and command returned by setup.

| Provider | Local behavior |
| --- | --- |
| Claude Code/Desktop | The selected `SessionStart` hook uses the guarded parser and appends shell-quoted declared exports to Claude's private `CLAUDE_ENV_FILE`; later Bash calls receive the mapped targets. A value-free session pin retains the original declaration across resume/compaction. Prompt hooks never load credentials. |
| Copilot CLI | Start one session with the exact generated-launcher command from the setup report. The launcher injects its setup-owned Bash activation and native-redaction flags and rejects caller overrides; the reported command contains no provider flags to reproduce. It does not replace parent values under declared target names, restores the mapped values only inside Bash tools and removes its private mode-`0600` activation file on ordinary wrapper exit. Copilot persists its Bash-support preference, but that setting contains no profile path or value. An abruptly terminated wrapper can leave the private temporary file for operating-system cleanup. Its lifecycle hook cannot mutate the parent process. |
| Codex CLI | Start one session with the exact generated-launcher command from the setup report. The launcher loads only declared mappings and replaces itself with Codex without printing shell exports. |
| Codex app / Copilot app | No documented generic per-task arbitrary env-file injection. Use provider-native credential stores or an explicit credentialed command as described by setup. |

Do not put values in prompts, hook JSON, provider settings, receipts or setup
reports. Profiles do not suppress provider keychains, credential helpers or
desktop account state and are therefore a routing convenience, not a security
boundary.

If activation fails after setup, use the exact profile-aware `doctor.command`
from the setup report. The hook or launcher emits only this value-free
remediation; it never prints the rejected path contents or a credential value.
