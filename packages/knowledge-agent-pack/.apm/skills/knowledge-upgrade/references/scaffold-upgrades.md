# Integrate upstream into an existing knowledge instance

Use this only for a verified scaffold-derived knowledge repository whose source
is being updated. A consumer-only installation refresh needs no upstream merge.
An application repo, an installed package or a directory name does not establish
an instance's role. Arbitrary data-only knowledge sources retain their existing
ownership and do not acquire scaffold remotes.

First adoption, remote conversion and bootstrap publication remain in setup's
[knowledge-instance procedure](../../knowledge-setup/references/knowledge-instance.md).
An existing installation must preserve its corpus, catalogs, private workspace
and profile configuration, credential values, pending signals, receipts, activity
history and authored instructions. Preserve uncommitted work and inspect fetch
and push destinations before any Git operation. Keep instance publication
separate from upstream maintenance; do not push corpus changes upstream.

## Establish the upstream once

Keep `origin` pointing at the instance's own repository: it remains the push and
PR destination. Add a remote named `scaffold` using the verified upstream URL:
`git remote add scaffold URL` (replace `URL` with that URL). Inspect existing
remotes before adding or changing one. Remote configuration is local and is not
copied when someone clones the instance; each new checkout needs this step.

Fresh copies retaining the scaffold's Git ancestry can use normal merges. If
either repository's history was reset, first have a maintainer verify a specific
scaffold baseline against the instance and establish its ancestry without
discarding instance changes. Do not blindly merge unrelated histories or record
unreviewed scaffold changes as already incorporated. Preserve published scaffold
ancestry once instances track it; rewriting it requires another explicit
migration.

## Apply later updates

Start with a clean instance checkout and preserve any unrelated local work.
Select the intended upstream revision and record its commit before integration.
Choose an unused update branch name. These commands assume the intended revision
is the fetched `scaffold/main` and both verified default branches are `main`;
substitute the selected commit and established names when different. Confirm
the fetched revision before merging:

```bash
git fetch origin
git fetch scaffold
git switch main
git pull --ff-only origin main
git switch -c update/scaffold
git merge --no-ff scaffold/main
```

Use a normal content merge for every subsequent update. Never use the `ours`
merge strategy for upgrades: it would record the update while discarding it.

Review the changes and resolve overlapping edits deliberately. Preserve the
instance's corpus, catalog, private configuration, signal and receipt ignores,
and authored instance instructions. Do not replace entire instance directories
with a scaffold checkout. If generated harness instructions or installation
metadata conflict, resolve their authored sources and regenerate projections
with that repository's owned install/compile/check commands. Do not hand-edit
generated instructions or overwrite them wholesale with upstream copies.

Run the applicable repository checks, inspect the final diff, and push the
update branch to `origin`. Open a PR in the instance repository for human review.
Merge that PR using a method that retains the upstream commits and merge
ancestry. **Do not squash or rebase the scaffold-update PR**: later upgrades need
the recorded common history. If repository policy enforces squash-only or
linear history, resolve that policy mismatch before proceeding.
## Refresh the authored maintenance route

Inspect the instance's existing authored maintainer instruction before installing
the updated skill catalog. Reuse equivalent routing; migrate references to the
former `knowledge-setup/references/scaffold-upgrades.md` owner to the installed
`knowledge-upgrade` skill. Preserve its verified upstream URL/name, instance
publication route and scope. The stable repository wrapper `docs/scaffold-upgrades.md`
can still route maintainers to this skill when present and verified.

Resolve changes in the owning `.apm/instructions/` source and registered manifest,
then regenerate through the instance's commands. Never patch generated
`AGENTS.md`, deployed skills or another dependency's source. Verify the new skill
and its references are deployed and the regenerated route resolves. Setup's
[maintainer procedure](../../knowledge-setup/references/knowledge-instance.md#during-setup-persist-the-central-maintainer-route)
owns the role-specific content; do not apply it to application repositories.

## Refresh installations after integration

A Git merge alone does not refresh Python, the APM catalog or hook bindings.
Continue with [knowledge-upgrade](../SKILL.md) for every in-scope runtime,
consumer and environment. Reuse setup's
[repository-owned integration](../../knowledge-setup/references/existing-repository.md)
and [portable hooks](../../knowledge-setup/references/portable-hooks.md).
Maintain the intended revision across Python and APM resources, preserve profiles,
credentials and automation, and report source, runtime and consumer verification
separately. Normal application work and compounding do not implicitly fetch or
apply upstream upgrades.
