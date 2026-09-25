---
description: Local development instructions for the agent-knowledge-scaffold repository.
---

# Agent Knowledge Scaffold Instructions

- This repository contains an organization-neutral knowledge core and APM
  package. Keep organization names, service inventories, business policies and
  credentials out of the reusable runtime and distributed skills.
- The scaffold has no organizational corpus. Use explicit source configuration
  and fictional fixtures; do not copy knowledge from another repository or
  installed package. Other checkouts and global harness configuration are
  outside this repository's maintenance scope.
- There is no backwards-compatibility requirement. Do not add aliases, shims,
  legacy imports or ambient environment fallbacks for retired implementations.
- The current architecture and delivery evidence live in
  `ai/plans/organization-neutral-knowledge-core.md` and
  `ai/plans/knowledge-final-pass.md`. Implement authorized work directly.
  Native scheduling tests remain paused unless the user reauthorizes them.
- Keep APM distribution under `packages/`. The current package contains
  `knowledge-setup` and `knowledge-compound`; broader skill ports are separate
  work and must include their templates, references and scripts.
- Root `.apm/instructions/` owns repository development instructions. The
  package owns its consumer discovery instruction. Regenerate harness
  projections from these sources; do not hand-edit compiled copies or create
  competing always-on instructions.
- Use the `agent-knowledge --profile` / `--settings` selector contract or
  direct `--config`. The installed
  `describe` response identifies the matching guide and templates. Do not infer
  workspace roots or organization membership from ambient variables.
- Group Python implementation under `src/agent_knowledge/`:
  - `domain/`: pure immutable models, validation, catalogs and matching; no
    filesystem, environment, clock, Git, network or receipt operations.
  - `application/`: coordinate explicit operations and shared diagnostics.
  - `entrypoints/`: CLI and provider-hook input/output boundaries.
  - `infrastructure/`: concrete configuration, Markdown/YAML, files and Git.
- Use ordinary typed functions and immutable dataclasses. Prefer `match` for
  multi-branch dispatch. Do not introduce frameworks, service classes or
  dependency-injection containers without a concrete need.
- Mirror implementation responsibilities under `tests/unit/` and
  `tests/integration/`; keep semantic tests in memory and provider/installation
  scenarios under `tests/e2e/`.
- Run the native gates: `uv run pytest -q`, `uv run ruff check .`,
  `uv run ruff format --check src tests`, and `uv run mypy`. For packaging or
  APM changes, build with `uv build` and run the isolated fresh-consumer check
  described in `docs/r8-harness-proof.md`. Report real-model proof separately
  from provider fixtures and CLI startup checks.
- When changing a package contract, synchronize the source instructions,
  templates, examples, tests and documentation. When removing a feature,
  inspect explanatory prose as well as symbol references.
- Knowledge and signals use Markdown with YAML frontmatter; catalogs and
  workspace configuration use YAML. Signal inboxes and usage evidence stay
  outside canonical knowledge and remain ignored by Git. Let the CLI own
  receipts, archives and guarded drainage.
- Preserve the user's work and unrelated configuration. Use ASCII unless the
  existing content needs otherwise. Do not write normalization trace files.
- Follow `docs/scaffold-upgrades.md` for scaffold/instance maintenance. Reusable
  changes belong upstream; preserve published scaffold ancestry. Instance
  upgrades use reviewed merges that retain ancestry and instance content.
  Normal compounding does not upgrade the runtime or fetch scaffold changes.
