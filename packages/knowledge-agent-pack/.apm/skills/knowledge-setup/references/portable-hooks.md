# Portable hooks for shared checkouts

Use this mode when hooks are committed for multiple developers or the same
consumer checkout is mounted into different execution environments. The shared
hook must not encode one machine's venv, credential file or session-state path.
Absolute binding remains the default for a single-machine installation.

## Per-environment setup

1. Install the Python 3.11+ runtime separately in each environment. Keep the venv
   outside a checkout shared by incompatible operating systems. For example, a
   Linux container can use `/opt/agent-knowledge-venv`; its host has its own venv.
2. Put that environment's venv `bin` on the PATH inherited by the harness.
   A Dockerfile can use `ENV PATH="/opt/agent-knowledge-venv/bin:${PATH}"`.
   Do not assume a desktop app inherits interactive shell startup files.
3. Register the same explicit profile name, such as `work`, in each environment's
   `~/.config/agent-knowledge/config.yaml`. Its workspace and credential paths
   are local to that environment. Keep the normal source-to-target credential
   mappings in this registry; do not duplicate them in hook JSON.
4. For a nonstandard registry, set `AGENT_KNOWLEDGE_SETTINGS` to its absolute
   path in the harness/container environment. Explicit CLI `--settings` wins
   over this variable; otherwise the variable wins over the standard user path.
   Empty or relative overrides are errors. Direct `--config` ignores it.
   This variable points to a registry, not a dotenv file, and contains no secret.
5. Keep the repository's authored profile recommendation portable too: name the
   profile and the environment-selected/standard registry without embedding an
   absolute path in generated `AGENTS.md` or other shared instructions.

Example local registry, stored outside the consumer checkout:

```yaml
schema_version: knowledge-profiles.v1
default_profile: work
profiles:
  work:
    config: /workspace/knowledge/knowledge-workspace.yaml
    environment:
      file: /run/secrets/knowledge-work.env
      variables:
        github:
          from_env: WORK_GITHUB_TOKEN
          expose_as: GH_TOKEN
          description: Work GitHub repository access
```

Mount credentials privately with mode `0600` and ownership for the runtime user.
Use existing profile overrides for environment-specific workspace paths when
needed. Do not share a Linux venv with a native macOS or Windows process.

## Bind once, verify in each environment

After the repository's normal APM installation/compilation, run:

```sh
python3 /opt/scaffold/packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py \
  --workspace /workspace/knowledge/knowledge-workspace.yaml \
  --package /opt/scaffold \
  --venv /opt/agent-knowledge-venv \
  --consumer /workspace/orders-api \
  --profile work --apm-mode bind --portable-hooks
```

Fresh helper-managed APM installations can use the same flag with
`--apm-mode managed`. `prepare` still installs no hooks and leaves binding
verification pending. Portable binding requires an explicit profile; register a
profile first for a direct-config installation.

Setup checks both launchers on PATH against the selected venv and checks that
runtime registry lookup resolves the same selection as setup. Passing only
`--settings /local/path.yaml` does not make that path available to the portable
hook: configure `AGENT_KNOWLEDGE_SETTINGS` or use the standard registry.

The provider commands then have this form:

```sh
agent-knowledge-hook --provider claude --profile work
agent-knowledge-hook --provider codex --profile work
agent-knowledge-hook --provider copilot --profile work
```

The hook resolves only credential declarations; it does not search knowledge or
require the workspace/catalog to be readable to emit reminders. Claude writes
credentials through its native `CLAUDE_ENV_FILE` channel. Its private declaration
pins live under `~/.local/state/agent-knowledge/claude-environment` and retain the
first activated declaration across resume. Changing the registry does not
retarget an existing session. Missing or invalid credentials prevent activation
but leave advisory discovery/reflection intact. A profile without credentials
needs no activation.

For CLI credential activation, setup reports these commands:

```sh
agent-knowledge-hook --profile work --launch-provider codex --
agent-knowledge-hook --profile work --launch-provider copilot --
```

These keep the existing provider-specific credential protections. They do not
add generic credential injection to desktop apps. Starting another credential
profile requires a new harness session.

Run `agent-knowledge --profile work context` and write-mode `doctor` in each
environment. Verify hooks from a fresh actual harness session too: setup's PATH
check proves only its own process environment. Repeat bind should leave the
shared hook files and Copilot deployment hashes unchanged across environments.
APM upgrades can restore marker commands, so repeat installation and binding
with the same mode. Preserve unrelated hooks and repository-owned checks.

## Linux containers and host mounts

A Linux container on Windows uses Linux Python and `fcntl`; it does not require
native Windows Python support. File locks, permissions and guarded writes must
still work on the actual mounted storage. In the scaffold checkout, run the
reproducible filesystem probe with the installed runtime Python:

```sh
/opt/agent-knowledge-venv/bin/python tests/e2e/filesystem_probe.py \
  --directory /workspace/knowledge/ai/usage
```

The directory must exist. The probe uses a disposable subdirectory and no real
credentials; it reports lock exclusion, concurrent receipt writes, private-file
permissions and guarded reads. Run it on each relevant mount, under the same
user as the harness. It tests processes within that environment, not exclusion
between a host process and a container process. If the mount fails, retain the
guards and use suitable Linux storage for the affected private/runtime data;
do not bypass locks or permission checks. Windows-hosted mounts need their own
proof even when another host's Docker checks pass. Write-mode `doctor` checks
writability but does not establish cross-process lock exclusion. Keep all writers
to the same writable knowledge state on the same storage and lock files; moving
only locks to separate per-process locations would defeat coordination. A
Linux-volume knowledge checkout can coexist with a host-mounted consumer repo.
The recorded Docker comparison is in the scaffold's `docs/r8-harness-proof.md`.
