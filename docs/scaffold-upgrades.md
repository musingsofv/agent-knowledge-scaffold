# Upgrade existing knowledge installations

Use the installed [knowledge-upgrade skill](../packages/knowledge-agent-pack/.apm/skills/knowledge-upgrade/SKILL.md)
for existing installations, on local hosts or inside developer-owned containers.
It coordinates upstream integration when needed, runtime refresh, consumer APM
deployment, hook rebinding and affected readiness checks. Consumer-only updates
do not require merging or changing the canonical knowledge repository.

Its [upstream reference](../packages/knowledge-agent-pack/.apm/skills/knowledge-upgrade/references/scaffold-upgrades.md)
owns verified remotes and ancestry-preserving instance upgrade PRs. First
adoption and initial maintainer routing stay with setup's
[knowledge-instance procedure](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/knowledge-instance.md).
Scaffold and knowledge-instance maintainers follow these ownership boundaries;
ordinary application work and compounding do not perform upgrades implicitly.

Upgrade reuses setup's runtime, profile and hook mechanisms rather than copying
them. Container upgrades distinguish rebuilding an immutable image from updating
a writable container-local venv, then verify the actual harness launch route.
For shared container/host checkouts, preserve the
[portable binding mode](../packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/portable-hooks.md)
when refreshing installed consumers; their registries and runtimes remain local
while committed hook commands stay unchanged across environments.
