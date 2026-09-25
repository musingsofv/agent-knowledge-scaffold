# Contributing

The repository contains the Python knowledge core and the neutral
`knowledge-agent-pack` APM package. Start with [consumer setup](docs/fresh-consumer.md)
when adopting the scaffold; use the steps below to change the implementation.

## Development

Use Python 3.11 and uv. Install the pinned dependencies and run the native gates:

```bash
uv sync --locked
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run mypy
uv build --out-dir .cache/dist
```

For a focused semantic change, start with `uv run pytest -q tests/unit/domain`.
Keep domain logic pure and mirror the source responsibilities in unit and
integration tests. Use temporary directories and fictional business data.

## APM package changes

Maintain the package under `packages/knowledge-agent-pack`. Its setup and
compounding skills include their own references and setup script. The Python
package owns the installed CLI guide and knowledge/signal templates.

Update affected contracts, examples and tests together. Root repository
instructions are authored in `.apm/instructions/scaffold-local.instructions.md`;
consumer discovery instructions are authored in the package. Regenerate their
projections with APM instead of editing the generated files:

```bash
apm install --target codex,claude,copilot --no-policy
apm compile --target codex,claude,copilot --force-instructions
```

APM generates portable hook markers; actual consumer setup binds those markers
to its verified runtime. Never commit machine-specific launcher paths or
provider credentials.

Run `tests/e2e/fresh-consumer-smoke` after changes to packaging, setup or hooks.
It installs a fresh wheel and APM package in a disposable workspace and needs
APM, uv and Python 3.11. Additional [harness checks](docs/r8-harness-proof.md)
separate deterministic provider fixtures from optional authenticated model runs.
Native scheduling and remote publication are not exercised by the default tests.

## Repository content

- Keep reusable implementation and skills independent of any organization.
- Keep sample knowledge fictional; an adopter configures their own sources.
- Track design contracts in `ai/plans/` and operational documentation in `docs/`.
- Keep signal inboxes, usage evidence, runtime environments and test caches ignored.
- Port additional skills only as separately reviewed work, including their
  templates, references and scripts.

The current CI validates the core and fresh APM consumption. This scaffold has
no marketplace-release automation; distribution changes need an explicit design.
