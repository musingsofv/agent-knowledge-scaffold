# Adapt an existing container environment

Use this reference when the whole Codex CLI, Claude Code or Copilot CLI process
runs inside a developer's existing Linux container or devcontainer. Inspect the
existing image, runtime user, mounts, tool versions and startup commands. Adapt
those conventions; do not introduce a scaffold base image, mandatory Dockerfile,
Compose project, privileged mode or Docker socket. No host-side harness is needed.

The setup agent derives the paths and produces the exact integration for the
existing environment. Business/profile choices still follow the setup skill.
Do not make the developer assemble raw flags or repeat already approved choices.

## Image build: install the runtime once

The build needs installed CPython 3.11 or newer, a Python package installer and
a pinned runtime wheel or source revision. It needs no knowledge checkout,
profile registry, private env file, provider login or mounted workspace. The
existing base image also owns installation of the selected harness CLIs and
their documented dependencies, Git, and APM when consumer installation uses it.
The setup helper's `--targets` selects integration outputs; it does not install
the harness CLIs. Check Bash availability for Copilot's Bash activation support.

For an image that already provides Python and uv, the narrow build steps are:

```sh
uv venv --python python3 --no-python-downloads /opt/agent-knowledge-venv
uv pip install --python /opt/agent-knowledge-venv/bin/python \
  /opt/wheels/agent_knowledge_scaffold-0.1.0-py3-none-any.whl
```

These paths and version are illustrative. Select the actual pinned artifact and
existing image conventions. Other image-owned installation mechanisms are fine.
Keep the reference wheel readable in the image: post-mount verification compares
the installed runtime payload with these exact bytes. `--package` can instead
name the matching source checkout. It is a read-only compatibility reference in
existing-runtime mode, never an instruction to reinstall. Matching version
strings alone do not establish matching code or resources.

Make the venv `bin` part of the environment inherited by the harness, for example
`PATH=/opt/agent-knowledge-venv/bin:<existing image PATH>`. Keep the venv outside
host-shared checkouts and at its final path; do not copy a host venv or relocate
console scripts whose interpreter paths point elsewhere. The image may keep the
runtime root-owned and unwritable by the nonroot harness user. Rebuild the image
to update it. Retain the matching APM package or install it through the consumer's
normal APM process; the Python wheel does not contain setup skills or scripts.

## After mounts: configure and bind as the harness user

Provide writable home/state directories for the actual harness user, and
persist provider-owned session/login state according to that provider's rules.
The selected registry and workspace paths must resolve inside the container.
An absolute host path is not a valid container route unless deliberately mounted
there. Use the normal user registry or the existing `AGENT_KNOWLEDGE_SETTINGS`
indirection; portable hooks do not embed a CLI-only `--settings` argument.

Use Linux-backed persistent storage for the knowledge checkout, signals,
receipts and shared lock files when host-mounted storage fails the filesystem
probe. Keep every writer to that state on the same storage; do not split locks
into a private container directory. A consumer code checkout may be a separate
host bind mount. Preserve configured origin/source/storage boundaries. Mount
private credential files separately with the required runtime-user ownership
and mode `0600`; do not bake values into images, examples or committed config.

Create or verify the selected workspace/catalog and profile through the normal
setup procedure. Existing-runtime `prepare` can check an installed runtime
before APM installation; it does not bind hooks or write a compounding trigger.
Run the consumer's own APM installation/compilation and checks, then bind, for
example:

```sh
python3 /opt/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py \
  --workspace /workspace/knowledge/knowledge-workspace.yaml \
  --package /opt/wheels/agent_knowledge_scaffold-0.1.0-py3-none-any.whl \
  --venv /opt/agent-knowledge-venv \
  --consumer /workspace/example-app \
  --profile example --runtime-mode existing --apm-mode bind --portable-hooks
```

`--runtime-mode existing` verifies the actual interpreter, both installed
launchers' selected interpreters and the complete runtime payload against the reference. It requires
neither uv nor package installation and does not create or repair the venv.
Missing, modified or incompatible contents require a matching reference or
image rebuild. It suppresses bytecode generation during its runtime probes.
Portable credential activation avoids writing an environment launcher into the
venv. Existing mode reports a precise remediation if absolute credential binding
would require such a write. A profile without credentials needs no activation.

Runtime mode and APM mode are independent. `bind` still updates package-owned
consumer hooks, installed hook descriptors and Copilot lock hashes; the consumer
must be writable. `managed` still requires and runs APM. Neither mode certifies
the repository's instruction compilation. Repeat bind and run the consumer's
checks to verify idempotence. When compounding is configured, binding checks
write readiness and compares the installed compound skill and all its resources
with the helper's sibling source. Run the helper from its complete package;
a standalone copied script has no compatibility reference and remains pending.
Binding only inspects the trigger in the existing activity log. A matching
agreement is reused unchanged, including during an active run. A missing
agreement returns pending activation with the exact command and request; execute
it only after the consumer's final checks pass. Binding never activates or
replaces a trigger, and a conflicting store owner or schedule remains unchanged.
Compounding readiness, resource mismatch and corrupt-state failures are reported
separately while read-ready discovery/reflection hooks still bind.

## Verify persistence and normal launch

Run profile-selected `context`, explicit write-mode `doctor`, and the filesystem
probe from [Portable hooks](portable-hooks.md#linux-containers-and-host-mounts)
under the actual harness user on each relevant mount. Recreate the container and
verify that the same registry routes to the same persistent activity and signal
store. Doctor proves writable paths; the filesystem probe separately checks
cross-process lock exclusion. A successful test on one host/mount does not
certify another, or host/container exclusion against unrelated writers.

After setup, launch the selected CLI normally inside the container. Where the
setup report requires a Codex/Copilot profile activation command, use that exact
command. Do not reinstall the runtime, run APM or rebind on every launch. Repeat
setup after relevant image, package, profile, consumer integration or trigger
changes. Verify hook delivery in a fresh actual harness session; Python/runtime
tests do not prove provider installation, authentication or subagent behavior.

Compounding follows [local trigger selection](../SKILL.md): prefer a verified
durable native local schedule, otherwise use the prompt fallback. No qualifying
prompt means no fallback run. Missing authentication remains a separate
readiness issue. Report runtime, hooks, persistent storage, credentials and
compounding readiness independently.
