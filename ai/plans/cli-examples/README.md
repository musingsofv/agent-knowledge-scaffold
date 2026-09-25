# CLI planning fixtures

Fictional design-review data for [the CLI examples](../knowledge-cli-examples.md).
These are not organizational policies, active knowledge sources, a live signal
inbox, or a working installation. The ten available CLI methods use these as
synthetic inputs; publication coordinates are fictional.

The examples place this tree under `/work/code`. `orders-api` represents the
consumer checkout and `commerce-knowledge` represents its configured source.
Relative configuration paths also resolve inside this fixture tree. Signal
capture/list tests must copy these fixtures into a temporary directory and create
an independent Git repository at `orders-api` before testing signal origin.
Do not infer the fictional origin from this containing scaffold repository.
For a successful doctor write-mode case, fresh setup must also prepare the
ignored signal-storage directory; doctor itself does not create that directory.

All Markdown under the fixture source's `knowledge/` is complete synthetic
`knowledge.v1` input. The runbook is deliberately compact for checking physical
line locations; generated multi-match documents exercise bounded location pages in R3. Broader
consumption and workflow measurements remain with R8.
`index-observation.md` is authoring input, not a captured/published signal.

## Named profiles

The adjacent `knowledge-profiles.yaml` is an executable registry fixture. Both
labels intentionally alias the same workspace/store; `commerce-review` disables
optional diagnostics. They are not separate personal/work data stores.

```bash
uv run agent-knowledge --settings ai/plans/cli-examples/knowledge-profiles.yaml profiles list
uv run agent-knowledge --settings ai/plans/cli-examples/knowledge-profiles.yaml context
uv run agent-knowledge --settings ai/plans/cli-examples/knowledge-profiles.yaml --profile commerce-review doctor
```

Replace the direct `--config` selector in any example with `--settings` and an
explicit `--profile` to exercise the same operation through the named registry.
