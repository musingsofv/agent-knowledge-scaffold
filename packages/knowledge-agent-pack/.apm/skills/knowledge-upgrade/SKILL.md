---
name: knowledge-upgrade
license: 0BSD
description: >
  Upgrade existing scaffold-derived knowledge repositories and installed consumers
  on hosts or in containers. Use for upstream, runtime or package refresh.
  Do not use for first adoption or compounding.
  Success means source, runtime and consumer readiness are verified.
---

# Upgrade an existing knowledge installation

Update an established installation without repeating business onboarding or
replacing its knowledge. This skill owns upgrade coordination; `knowledge-setup`
continues to own provisioning, profiles, activation and binding mechanisms.
Use its helpers from the complete matching package, not copied scripts or a
second hook implementation. Keep the selected profile/registry or direct
workspace explicit on every configured runtime call.

## 1. Identify what needs updating and where it runs

Inspect the current instructions, Git state, verified remotes, installed package
metadata and selected `describe`/`context`. Record the coordinator skill's revision
separately from the selected installation target and which
knowledge repository, runtimes, consumers and environments are in scope. A
consumer-only refresh need not merge or alter its canonical knowledge source.
If the installed catalog predates this skill, read it from the verified target
checkout before refreshing APM; a Python wheel does not contain the skills.
The coordinator may be newer than the target; derive the expected installed
skills and resources from that target's manifest, source tree and ownership
records, not the coordinator's own catalog.
Do not infer access, publication permission or instance membership from a token,
folder name or package installation.

Before replacing a runtime, verify that both its selected artifact and the
matching APM dependency are available through the consumer's intended installation
and publication route. A local commit alone does not make a remote dependency
reproducible. Preserve approved local-source workflows; a reviewed remote PR
must be reproducible through its repository-owned workflow. Resolve missing
artifacts before dependent runtime changes, while continuing independent work.

Before choosing paths, use setup's
[execution-location checks](../knowledge-setup/references/containers.md#establish-execution-location-first)
to distinguish host, container and uncertainty for both tools and the intended
harness. Apply that discovery on local hosts too; a Docker client or Linux alone
is not proof. Resolve only missing target facts that block dependent work.

Keep a compact before/after record of source commits, runtime paths and payload
identity, APM dependency/lock identity, target set, hook binding mode, selected
profile/workspace and shared state routes. Reuse existing configuration and
explicit session overrides. Preserve unrelated local work, corpus/catalogs,
credentials, signals, receipts, ignores and authored local skills/instructions.
Do not copy another profile or a host venv, reset state or silently change the
registry default. Read setup's
[profile contract](../knowledge-setup/references/profiles.md) when selectors or
activation are affected.

## 2. Integrate upstream when the knowledge repository needs it

Follow [the upstream integration procedure](references/scaffold-upgrades.md).
Verify provenance and common history, select the intended upstream commit, then
merge actual content on an isolated update branch. Preserve instance-owned data
and regenerate conflicting projections from their authored sources. A ZIP or
history-reset template needs a separately verified baseline; do not fabricate
ancestry or merge unrelated histories implicitly.

Validate and publish through the instance's existing workflow and authorized
scope. An instance-upgrade PR must preserve upstream ancestry when merged.
Opening it does not authorize merging it. If this task only refreshes installed
consumers, use the verified target package directly and leave source integration
not applicable. Migrate outdated authored maintainer routes to this skill during
an instance upgrade, as described in the integration reference.

## 3. Refresh the runtime in each selected environment

Use the intended source revision or built wheel and the matching APM package.
Equal version strings are insufficient. The setup helper's `existing` mode
verifies actual payload compatibility; `install` reports installation, not that
independent comparison. Keep the existing supported interpreter, configured venv path,
package/index conventions and pinned repository tools. Python and APM are
separate installations: changing a checkout or pulling main updates neither.

Before replacing files used by active sessions or compounding workers, inspect
the selected activity status and coordinate the environment's normal safe update
point. Do not clear an active run, its exact worker/session handles or its locks
to make an upgrade appear ready. Leave an affected live installation pending when
it cannot yet be updated safely; continue independent environments.

| Existing runtime | Upgrade action |
| --- | --- |
| Writable local-host venv | Reuse setup's `--runtime-mode install` with the explicit configured `--venv` and target `--package`. Do not create a new workspace or reinitialize its corpus. |
| Immutable image-owned container venv | Follow the developer's existing image build process with the target artifact at the final path. Verify a newly running container uses that image, then use `--runtime-mode existing` against its matching reference. This mode verifies; it does not install or repair the venv. |
| Writable container-local venv | Deliberately install the target in that container-local venv, then verify it from the actual harness environment. A changed mount or host installation does not refresh it. |

After a writable-venv install, use the same complete helper and selected inputs
with `--runtime-mode existing --apm-mode prepare` to verify both launchers and
the installed payload against the target `--package`. Repeat that read-only
verification after any later binding step that uses install mode. On mismatch,
refresh the target through the environment's owned package tooling and verify
again; do not treat an `installed` status as exact-revision proof.

For either container route read
[container provisioning and launches](../knowledge-setup/references/containers.md)
and, only when local paths/projections need refresh,
[guarded container profiles](../knowledge-setup/references/container-profiles.md).
Preserve the user's image, user, mounts, tools and launch conventions. Supply no
scaffold image and do not introduce privileged mode, a Docker socket or automatic
sandbox widening. Keep source/catalog, code, private env and signal/receipt paths
resolvable inside the actual container, respecting their original relative bases.
Never put credential values in images, shared instructions or saved evidence.

Preserve provider-owned login/session state and persistent Linux-backed knowledge
storage. All writers to a shared store must still coordinate through the same
state and locks; never move only lock files to a private mount. Inspect the
actual mount when it changes. Do not delete a user's container/volume or restart
live sessions as a verification shortcut. Each host/container has its own runtime,
local registry and private credential route.

## 4. Refresh the package and rebind each consumer

Read [repository-owned APM integration](../knowledge-setup/references/existing-repository.md)
and the applicable consumer instructions. Preserve pinned APM, all registered
harness targets, local skill sources, portable dependency references and the
repository's instruction-compilation and staged-content guarantees. Select APM
responsibility independently from runtime mode.
For a local package input, apply the reference's
[source-inventory checks](../knowledge-setup/references/existing-repository.md#check-local-package-inputs)
before installation; ignored generated files can otherwise enter deployment locks.

Use `knowledge-setup/scripts/setup_runtime.py` from the verified complete target
package with the selected workspace, explicit venv, package, registry/profile
and targets. For repository-owned integration the sequence is:

1. `--apm-mode prepare`: install or verify the chosen runtime and selection.
2. Run the consumer's registered APM install/compile commands, refreshing its
   dependency to the intended revision and deploying the new catalog. Do not
   replace a remote dependency with a machine-local path or edit deployed copies.
3. `--apm-mode bind`: rebind the installed package-owned hooks. Installation may
   restore markers; bind also updates owned descriptors and Copilot lock hashes.
4. Run the consumer's final consistency checks, including actual Git-index checks
   when required. Inspect authored, installed, lock and generated changes together.

Use setup's managed mode only when the consumer permits it. Preserve the existing
[portable binding mode](../knowledge-setup/references/portable-hooks.md) for shared
checkouts; do not replace environment-local lookup with one machine's absolute
paths. Verify the installed skills and their referenced resources against the
selected target's actual inventory; do not require a skill
that exists only in the newer coordinator. Verify the consumer's generated profile
recommendation with overrides intact.
A successful bind does not certify instruction compilation or native hook delivery.

## 5. Verify affected behavior and preserve compounding ownership

From the actual selected runtime, confirm `describe`, selected `context`,
write-mode `doctor` and relevant consumer checks. Verify retrieval and its receipt;
use isolated fixtures for signal-write/lifecycle probes, never manually remove
pending user signals. Reuse valid evidence only when the affected runtime,
resources, configuration and execution boundary still match it.

Follow [provider trust and delivery](../knowledge-setup/references/portable-hooks.md#provider-trust-and-delivery)
after changed binding or definitions: registration, project trust, approval of
exact hook definitions and fresh native reminder delivery are separate evidence.
Do not auto-grant trust or call a successful CLI exit proof that tools ran.
For containers, run the affected
[acceptance sequence through the generated launcher](../knowledge-setup/references/containers.md#one-acceptance-sequence-through-that-launcher),
including fresh/reused launch and persistent-state checks when those routes change.
Keep provider versions, actual mount/sandbox checks and unverified platforms explicit.
Preserve user-selected read-only and sandbox policies; report incompatible access
rather than disabling protections. Host-native proof is not container-native proof.

Use setup's returned activation/launch action for a new session. Refresh a saved
container setup report when its package, image, profile or consumer inputs changed;
its lightweight preflight is not an installer. Verify configured credential
activation without printing, transforming or hashing values or borrowing ambient
credentials. Keep blank entries unchanged and visibly pending. A read-ready
workspace may retain working reminders while credential activation or required
publication access is unavailable. A profile selector does not change credentials
already loaded into a desktop or CLI session.

Follow [local compounding ownership](../knowledge-setup/references/local-compounding.md)
for affected trigger integration. Preserve the existing schedule or prompt/manual/
disabled choice, exact owner and native task/worker handles, interval and history.
Reuse one owner per physical store across aliases/providers/environments. Rebind
neither replaces nor activates an agreement. Execute a returned pending activation
only after final consumer checks, within the existing authorized configuration;
resolve conflicts through that reference instead of resetting the activity log.
Do not create duplicate schedules, a new last-run file or shell-spawned model
workers. Required unavailable access remains pending; unrelated blank service
credentials do not erase independently verified local readiness.

## 6. Report the installed result

Distinguish source integration, runtime revision, each consumer's APM/instruction
state, hook registration/trust/delivery, knowledge read/write/receipts, credentials
and compounding readiness. Include actual environment/provider coverage, retained
state, checks/evidence, PR status within authorized scope, and exact next launch or
pending remediation. Do not call an installation upgraded merely because its Git
checkout is current. Ordinary future launches check readiness; they do not install,
compile or rebind on every prompt. Do not upgrade unrelated consumers implicitly.
