# Updating knowledge instances from the scaffold

The authoritative maintenance procedure ships with `knowledge-setup`:
[Updating a knowledge instance from the scaffold](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/scaffold-upgrades.md).

It covers setup of the central maintainer route, verified upstream remotes,
ancestry-preserving upgrade PRs and refresh of installed runtimes, skills and
hooks. Scaffold and knowledge-instance maintainers follow that procedure;
ordinary application work and compounding do not perform upgrades implicitly.

For shared container/host checkouts, preserve the
[portable binding mode](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/portable-hooks.md)
when refreshing installed consumers; their registries and runtimes remain local
while committed hook commands stay unchanged across environments.
