# Integrate with repository-owned APM

Use this procedure when a consumer already owns its APM installation,
compilation, generated files or native skill catalog. Keep the repository's
commands authoritative and use the scaffold's hook implementation unchanged.
The helper supports the local installed dependency at
`apm_modules/_local/knowledge-agent-pack`; another registry layout is not a
supported binding target.

## Discover the consumer contract

Inspect applicable `AGENTS.md` or other harness instructions, `apm.yml`, the
registered architecture/layout, package scripts, APM version pin and generation
checks. Identify the consumer's selected targets and existing local skills,
external dependencies, generated outputs, lock ownership and staging checks.
Do not infer that a repository with an empty dependency list forbids all future
packages: adding this package may require an explicit, narrow contract update.
Use existing setup authorization; ask only about unresolved material policy or
business choices.

Keep the authored package and runtime distribution aligned. The `--package`
argument installs Python from a checkout or wheel; it does not register the APM
package in the consumer. Use the package's authored sources as the integration
inputs rather than copying hook logic or maintaining a second discovery policy.

## Prepare without changing consumer configuration

Create or complete the approved workspace/catalog and private profile registry
using the setup skill and profile reference. To bootstrap the runtime before
registering a profile, omit `--profile` and `--settings` for this first command:

```bash
python3 /work/agent-knowledge-scaffold/packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py \
  --workspace /work/knowledge/knowledge-workspace.yaml \
  --venv /work/knowledge/.agent-knowledge-venv \
  --package /work/agent-knowledge-scaffold \
  --consumer /work/orders-api \
  --targets codex --apm-mode prepare
```

`prepare` requires neither an APM executable nor an installed APM package. It
installs/verifies the Python runtime and reports requested hooks pending. It
writes no consumer configuration or credential activation binding. Register the
reviewed profile through `register_profile.py`, then repeat with the explicit
profile selector to verify the intended route. A mode-`0600` env file containing
blank assignments can remain pending while knowledge setup proceeds. Values
must later be non-empty literal assignments, without quote wrappers or shell
interpolation. Never request or print them in chat.

## Extend the repository's registered integration

Use the repository's owned source and generation tooling to:

1. Register the exact external knowledge package alongside existing local
   skills. Preserve their authored sources and ownership. Amend any dependency,
   approved-tree, output or catalog allowlists deliberately; do not relax them
   to arbitrary paths or dependencies.
2. Compose the package's one source-owned discovery instruction into the
   consumer's approved instruction output. Its source is
   `.apm/instructions/agent-knowledge-discovery.instructions.md` inside the
   package. Declaring a dependency alone does not make a `--local-only`
   compiler import dependency instructions. Extend the consumer's isolated
   source inputs/composition explicitly, preserving its output count and
   generation grammar. Keep ownership provenance and avoid duplicate always-on
   text. Do not edit generated `AGENTS.md` by hand.
   For named-profile onboarding, also persist the consumer's short profile
   recommendation in its own authored source using the
   [profile procedure](profiles.md#persist-the-consumers-profile-recommendation).
   Keep the generic package instruction unchanged; preserve an existing
   recommendation and resolve conflicts before replacement.
3. Register authored skills, installed native skill resources, hook projections
   and lock records as separate owned sets where the repository validates them.
   Preserve source/deployed reference resolution and APM collision protection.
   Extend test-impact classification and actual Git-index consistency checks
   when the repository enforces them. Compare stable lock ownership, paths and
   hashes; do not require a generated timestamp to be byte-identical.
4. Run its install/compile commands in the intended consumer, using its pinned
   APM and chosen targets. APM deploys native skills and hook markers; the
   consumer's compiler owns instruction generation. The package's setup and
   compound skills must be discoverable and their references usable.

The repository owns these integration changes. The scaffold's bind mode does
not modify its compiler, add a dependency, certify instruction composition or
invent arbitrary shell-command adapters. If the repo installs into a temporary
mirror, ensure its approved process projects the owned outputs and installation
metadata back to the actual consumer before binding.

## Bind installed resources and check the final state

After repository-owned installation/compilation succeeds:

```bash
python3 /work/agent-knowledge-scaffold/packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py \
  --workspace /work/knowledge/knowledge-workspace.yaml \
  --venv /work/knowledge/.agent-knowledge-venv \
  --package /work/agent-knowledge-scaffold \
  --consumer /work/orders-api \
  --settings /work/local/profiles.yaml --profile personal \
  --targets codex --apm-mode bind
```

`bind` runs no APM executable and generates no instructions or manifest. It
reuses the same package-owned binding and verification as managed setup. It
updates the installed hook descriptor and selected provider hook projections;
for Copilot it also reconciles the owned deployed-file hashes in `apm.lock.yaml`.
It is not an immutable-consumer check. Missing or conflicting package resources
fail rather than creating a private replacement hook. Run the repository's
checks **after binding**, accounting for the verified absolute runtime command
in owned outputs. When staging is enforced, validate the actual index contents
as well as the working tree. Preserve unrelated/user-authored hooks.
Inspect each selected harness's generated instructions for the intended profile
and registry recommendation, with the user's session override intact. Resolve
that selector through `context` and `doctor`. Binding verifies hooks, not this
agent-authored instruction content; report it separately and leave incomplete
composition pending.

Report runtime/read, environment, hooks, write/receipt and automation readiness
individually. With a read-ready workspace and only environment diagnostics,
binding produces working reminders while activation stays pending. `doctor`
continues to report the environment diagnostics and an overall failure; do not
hide it by rerunning without the selected profile. Run its explicit write-mode
probe to verify signal and receipt storage before compounding.

Repeat bind to check idempotence. On later upgrades, run the repository-owned
install/compile again, then bind and check again; installation can restore
portable markers that need rebinding. Remove the package through the same
repository-owned dependency workflow, preserving other skills and hooks.
After the developer fills the private env file, rerun the same selected bind
command and repository checks. Only then present the returned activation action
for a new harness session. Scheduling remains the setup skill's separate step.
