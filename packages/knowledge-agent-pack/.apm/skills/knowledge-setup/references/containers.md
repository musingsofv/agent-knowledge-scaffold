# Adapt an existing container environment

Use this reference when the whole Codex CLI, Claude Code or Copilot CLI process
runs inside a developer's existing Linux container or devcontainer. Inspect the
existing image, runtime user, mounts, tool versions and startup commands. Adapt
those conventions; do not introduce a scaffold base image, mandatory Dockerfile,
Compose project, privileged mode or Docker socket. No host-side harness is needed.

The setup agent derives the paths and produces the exact integration for the
existing environment. Business/profile choices still follow the setup skill.
Do not make the developer assemble raw flags or repeat already approved choices.

## Establish execution location first

Check this even when the developer has not identified the environment. Record
the tool process and intended harness separately as container, host or unknown.
Before choosing paths or preparing files:

1. Inspect `uname -s`, `id`, `pwd -P`, home and selected executable locations.
   They describe the process, not container membership. Use platform equivalents
   on a native Windows shell.
2. On Linux, check existence of `/.dockerenv` and `/run/.containerenv`, and read
   at most 80 lines of `/proc/self/cgroup` and `/proc/1/cgroup`. Missing markers
   and cgroup-v2 `0::/` remain inconclusive. Use `systemd-detect-virt --container`
   only if installed. Missing/denied tools do not require installation or sudo.
3. Trace the existing devcontainer, entrypoint, remote executor or wrapper that
   launches the harness. Configuration describes intent, not proof this session
   used it. Inspect executable-name ancestry with
   `ps -o pid=,ppid=,comm= -p "$$"` and relevant parents where available.
   A tool shell need not descend from the harness. Namespace references from
   `/proc/self/ns/mnt` can compare known contexts but are not portable IDs.
4. Cross-check native session/executor metadata and paths through the intended
   route. Repeat inside an actual harness tool during acceptance. An unrestricted
   `docker exec` shell proves only that shell's context.

Do not dump environments, full process arguments, Docker inspection output or
credential-bearing config. Linux, `/workspace`, a Docker client or negative
probes alone do not establish the target. If the outer harness is unobservable,
say so. From a known host, supply the existing container entry/reopen action;
do not create a container, restart a live session or require a Docker socket to
resolve location. Ask only for a missing target/launch fact blocking dependent work.

Once installed, `preflight` returns bounded execution/readiness observations.
It leaves outer-harness location, native trust/firing and tool-sandbox proof
unverified; agent inspection and native acceptance resolve those separately.

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

When the approved package is mounted only after startup, explicitly provision
a container-local writable venv through install mode, separately from ordinary
launch. A changed mounted checkout does not update installed code: reprovision
deliberately or rebuild the immutable image and verify the running container
uses it. Reuse package/index conventions and supported Python. Don't downgrade
a compatible interpreter or fetch source/Python implicitly. Diagnose stale
launchers, interpreter failures and unwritable inherited uv caches separately;
use a user-owned cache instead of deleting shared caches or changing all owners.

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
When a designated host mount cannot enforce those private-file requirements,
use [container profile preparation](container-profiles.md) for a guarded local
copy. Keep activation validation strict. Translate all effective paths using
supported overrides and their original relative bases; replacing only the env
file path is insufficient.

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

Retain the full established APM target set. Helper-managed installation rejects
omitting an existing harness projection before installation; preserve the set or
use repository-owned `prepare -> install/compile -> bind -> final checks`.
Verify other targets survive. Final consumer/index checks run after binding.

## Integrate the actual launcher

Save successful setup JSON outside shared source. Its `launch` section contains
exact provider argv, inherited runtime PATH/registry, selected configuration and
credential declaration, and preflight command/request. Execute its recipe with
the installed skill's helper, preserving provider arguments after `--`:

```sh
python3 /opt/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/launch_container.py \
  --setup-report /home/developer/.local/state/agent-knowledge/setup.json \
  --provider codex --
```

Derive actual paths and locate the skill through APM. The helper adds the venv
bin to inherited PATH, selects the registry, requires container execution and
runs read-mode preflight, then executes setup's activation or native-start route.
It performs no shell evaluation, installation or rebinding; pending credentials
or changed configuration/declarations require repair first. Preserve original
provider sandbox/readonly flags. Pre-launch permission checks do not establish
the sandbox that native tools will later use.

Integrate the same route into fresh and reused container branches. A
`postStartCommand` does not run for every `docker exec`, and exports in one
shell do not activate another process. Do not modify shell rc files. For a
projected credential file, guarded refresh is a separate explicit pre-step that
must succeed before launch. Independent knowledge/hook setup remains usable
while credential activation is pending.

This launcher is strict. An explicitly chosen consumer advisory/degraded route
must retain failures and remediation; it must not use ambient credentials,
disable receipts silently or claim complete readiness.

## One acceptance sequence through that launcher

Run in a fresh actual harness session through the configured launch route:

1. Confirm installed `describe` and selected `context`; run `preflight` with
   `mode: write`, the intended provider/consumer/runtime and
   `expected_execution: container`. Its disposable writes use that tool's actual
   permissions. Keep read, signal, receipts and environment results separate.
2. Retrieve and inspect a representative selected-source document and verify
   its CLI-written receipt. Empty fixtures prove operation, not matching quality.
   Use isolated fixtures for signal record/list/lifecycle tests; never manually
   delete user signals to clean a run.
3. For configured credentials, verify presence through the native provider
   route with mapped targets removed from the test parent. Keep provider login
   separate. Never print, transform or hash values. Blanks remain pending;
   profiles without credentials report this step not applicable.
4. Observe registration, native trust where exposed, and actual lifecycle plus
   prompt-hook delivery separately. Enabled registration or echoed instruction
   text is insufficient. Retain bounded real-event evidence. Do not grant trust
   automatically; registration/regeneration changes can invalidate prior trust.
5. Inspect effective sandbox policy. Where authorized, configure only required
   signal/usage/private-state paths through the consumer's real settings,
   preserving comments/unrelated settings and native overrides. Verify actual
   native policy rather than flags alone; retain intended source/credential
   access and explicit read-only choices. Do not disable sandbox protections.
6. Repeat launch in the existing container and preparation/bind for idempotence.
   Recreate a disposable container against the same persistent storage to check
   history, signal/receipt routes and locks. Do not interrupt real sessions or
   remove their volumes for acceptance.

The scaffold checkout's `tests/e2e/container_launch_acceptance.py` supplies an
isolated reproduction route; inspect its `--help`. Use fictional knowledge and
provider-approved authentication. Keep preparation/fixtures distinct from native
live proof. Record provider/APM/runtime/image identities and each missing
prerequisite without secrets. Windows-host mounts need their own proof; passing
Debian/Alpine runtime tests does not certify them or every provider on Alpine.

## Persistence and later changes

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
