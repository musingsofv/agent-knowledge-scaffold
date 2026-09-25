# Updating a knowledge instance from the scaffold

The scaffold owns reusable runtime, package, skills and hook behavior. A knowledge
instance owns its corpus, catalog, workspace configuration and publication
destination. Put reusable fixes in the scaffold first, then merge them into
instances through a reviewed update branch. Instance-specific content stays in
the instance.

## First adoption: one checkout, two remotes

When the developer adopts a fresh scaffold clone as their knowledge instance,
use that same checkout for the runtime, packages and configured knowledge. A
directory name such as `knowledge` is convenient, but no second pristine
scaffold checkout is required. Preserve an existing directory and configured
paths. This conversion applies to an adopted instance, not to an application
repository or a checkout being used to maintain the upstream scaffold.

Before deriving publication settings:

1. Verify the clone's scaffold provenance and source URL. Propose the intended
   user's or organization's repository, suggesting `knowledge` and **private**
   visibility for a new repository. Include the owner/name in the ordinary setup
   choices; reuse an already authorized destination. A native account alone does
   not establish the intended organization.
2. Create the authorized private GitHub repository, or reuse its verified empty
   repository. For example, `gh repo create OWNER/knowledge --private`, replacing
   `OWNER` with the confirmed owner and using the intended credential route. Do
   not initialize it with a README, license or GitHub template: the local clone
   already has the history to publish. If an existing destination has commits,
   inspect its relationship to the clone and reconcile deliberately; do not
   force-push or overwrite it. Preserve existing visibility and local-only choices.
3. Inspect fetch and push URLs before editing remotes. If `origin` still names
   the verified upstream scaffold and `scaffold` is unused, rename it to
   `scaffold`, then add `origin` for the user's repository. If the two correct
   remotes already exist, reuse them. An existing verified `scaffold` remote
   allows changing `origin` from the upstream to the confirmed instance URL;
   conflicting or ambiguous remotes require resolution, not silent replacement.
   Preserve unrelated remotes and verify that both instance URLs target the
   intended repository, including any explicit push URL.
4. Set the local default push destination to `origin`. Review the initial
   tracked content for publication and keep credentials, local configuration,
   signals and receipts ignored. Push the intended base branch explicitly to
   `origin` with upstream tracking. Renaming a remote also moves branch tracking:
   verify subsequent plain pulls track `origin`, and resolve any branch-specific
   push override still pointing at the scaffold. Do not push knowledge upstream.
5. Verify the new repository identity, visibility, remote branch and default
   branch, and verify that the published commit retains the cloned scaffold
   ancestry. Only then derive PR publication from the instance's `origin` using
   [the publication procedure](publication.md). A failed creation or initial
   push leaves publication pending; independent local setup can continue.

For a verified fresh clone with only the upstream `origin`, an authorized empty
instance repository and base branch `main`, the remote/push steps are:

```bash
git remote rename origin scaffold
git remote add origin https://github.com/OWNER/knowledge.git
git config --local remote.pushDefault origin
git push --set-upstream origin main
```

Substitute the confirmed repository and branch. Do not run the rename/add
commands again on an already configured instance. The result is one checkout
with `origin` for the user's knowledge and PRs, and `scaffold` for fetching
implementation updates. Record those identities in the maintainer route below.

Use a Git clone preserving the scaffold's ancestry for this path. GitHub's
**Use this template**, downloaded source archives and history resets do not
preserve that common history. Existing copies made that way need a separately
verified baseline before ordinary upgrades; setup must not fabricate ancestry
or silently merge unrelated histories.

## During setup: persist the central maintainer route

Resolve each configured canonical source to its owning Git checkout. Apply this
procedure only when repository provenance, shared scaffold ancestry or an
established migration record verifies that checkout is a scaffold-derived
knowledge instance. A directory name, an installed package or the application
consumer's remote does not establish that role. For an arbitrary source or a
separately maintained data-only repository, preserve its existing ownership;
do not add scaffold remotes or maintenance instructions.

For a verified instance, use existing setup authorization to:

1. Verify its upstream repository URL and remote name from its established
   provenance/configuration. Reuse that remote, or configure `scaffold` with the
   verified URL if missing; do not replace a conflicting remote silently. Keep
   `origin` as the instance's own publication destination. If identity or
   ancestry is unresolved, report the maintenance route pending and continue
   independent setup; a history migration needs explicit authorization.
2. Persist one brief instruction in the **instance's authored APM source**,
   using its registered layout and preserving other rules. Reuse an equivalent
   instruction; do not append duplicates on repeat setup. Include the verified
   upstream URL/name and a resolvable route to this reference, for example:

   ```text
   This checkout is a central knowledge instance derived from the scaffold.
   Before runtime/package maintenance or scaffold upgrades, follow the installed
   knowledge-setup skill's references/scaffold-upgrades.md. Its upstream remote
   is scaffold at VERIFIED_URL; origin remains this instance's publication repo.
   Reusable fixes belong upstream. Preserve instance knowledge/private settings
   and upstream ancestry. Ordinary compounding does not upgrade the runtime.
   ```

   Replace `VERIFIED_URL` and the remote name with verified values. Keep the
   routing reference discoverable through the installed skill; a verified
   checkout-relative `docs/scaffold-upgrades.md` wrapper is also suitable. Do
   not copy the full upgrade procedure into always-on instructions.
   Reconcile an inherited "no organizational corpus" role statement within the
   adopted instance: allow its configured canonical sources while keeping core
   code and distributed packages neutral. Do not change the upstream template.
3. Regenerate the instance's harness outputs using its owned APM commands, then
   inspect each selected output and verify the reference resolves there. Run
   its consistency checks and report the authored source, verified outputs and
   upstream route. Missing/deferred generation leaves this step pending; runtime
   helper success alone does not prove it. Never hand-edit generated files.

This is separate from the application consumer's profile recommendation. Do not
add the central-maintainer instruction to application hooks or generic consumer
instructions. Git remotes remain local configuration, so future instance clones
need the recorded upstream configured again. Setup establishes the route; it
does not automatically fetch and merge upgrades.

## Finish adoption: publish the instance bootstrap

After setup authors the catalog and maintainer route and verifies its generated
outputs, review the diff and commit the non-secret instance files to its own
repository. Include the initial catalog, authored instructions, ignore rules
and repository-owned tracked projections/lockfile. Preserve the repository's
configuration policy: machine-local workspace/profile files and credentials
stay ignored; include a portable configuration example when needed for another
clone to reproduce the setup. Do not stage unrelated work or use a blanket add.

For the new private repository, finish the authorized bootstrap push to
`origin`. If its policy requires a PR, publish through that workflow and report
adoption pending until the bootstrap reaches the base branch; do not bypass
protection or merge without authorization. Verify the remote commit contains
the initial catalog and maintainer route before declaring shared setup ready.
The earlier push established the repository, but did not publish files authored
afterward. A future clone still reruns setup for local remotes, paths and runtime.

## Establish the upstream once

Keep `origin` pointing at the instance's own repository: it remains the push and
PR destination. Add a remote named `scaffold` using the verified template URL:
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
Choose an unused update branch name. These commands assume both verified
default branches are `main` and the upstream remote is `scaffold`; substitute
the established names when different:

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

## Refresh installed consumers

Preserve the chosen hook binding mode. Shared checkouts use
[portable hooks](portable-hooks.md): update the runtime in each environment,
refresh APM through its owning commands, then bind with `--portable-hooks` and
the existing profile name. Do not replace portable commands with local absolute
paths on upgrade. Per-environment registry and credential files remain local.

A Git merge does not refresh an installed Python runtime, APM package, skills or
hooks. After relevant updates, follow
[`knowledge-setup`](../SKILL.md)
for each affected installation. Keep the runtime and installed package aligned
with the intended revision. For repositories with owned APM generation, use the
[existing-repository procedure](existing-repository.md):
prepare, owned installation/compilation, bind, then owned checks. Preserve the
existing profiles, credentials and automation; verify `describe`, `context`,
`doctor` and the relevant hook integration before declaring the update ready.

## Which agents need this contract?

- Scaffold maintainers own reusable changes and stable upstream history.
- Knowledge-instance maintainers own upgrade PRs, conflict resolution and
  preserving instance content; route reusable fixes back to the scaffold.
- Application-repository agents use installed skills and the selected profile.
  They refresh their integration when requested, but do not maintain the
  instance's upstream relationship.
- Normal compounding maintains knowledge and its owning local instructions or
  skills. It does not fetch scaffold updates or upgrade the runtime implicitly.
