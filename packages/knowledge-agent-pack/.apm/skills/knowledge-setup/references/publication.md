# Configure reviewed knowledge publication

Fresh onboarding defaults to GitHub pull requests so proposed knowledge changes
are visible for human review. Setup authors an explicit publication block for
each intended writable knowledge source. The CLI does not infer a repository:
omitting `publication` still disables publication for that source.

## Establish the destination

For first adoption of a scaffold clone, complete
[one checkout, two remotes](scaffold-upgrades.md#first-adoption-one-checkout-two-remotes)
before deriving the destination. Its initial `origin` may still be the reusable
upstream. Never select that upstream for organizational knowledge PRs, even if
the current account can write to it. After conversion, use the verified
instance `origin`; `scaffold` is only the update source.

1. Resolve the canonical source root and catalog from the selected configuration.
   Find their owning Git checkout and inspect its remotes. Derive the proposed
   `owner/repository` only from the verified GitHub remote of that knowledge
   checkout. The application producing signals and the reusable runtime/package
   checkout are not publication destinations merely because setup uses them.
2. Verify the repository identity and its default branch through GitHub or the
   remote's advertised HEAD. Propose that verified default as `base_branch` and
   `knowledge/` as `branch_prefix`. Do not assume `main`: use it only when remote
   evidence identifies it as the default or the developer deliberately selects
   and verifies it. Preserve an existing approved base and prefix.
3. Include the destination once in the meaningful setup proposal: for example,
   "Compounding will propose changes to Studio's private knowledge repository,
   targeting its main branch; you review and merge the PRs." Existing explicit
   authorization carries forward. Do not ask again for an unchanged, already
   authorized destination or request a separate publication opt-in by default.
4. Verify the selected account can read the repository and has permission to
   push a branch and open PRs. Use the profile's declared GitHub credential route
   where configured; otherwise verify the intended native GitHub account. Never
   print tokens, borrow an unrelated account or create an empty probe PR.

If the source has no GitHub remote, has ambiguous remotes, or the intended
account is unavailable, report **publication pending** with the precise missing
prerequisite. Ask only for the unresolved repository choice or authentication.
Continue independent runtime/retrieval setup, but do not claim publication or
its dependent automation is ready. Do not invent a repository or silently
convert the intended default into local-only operation.

## Write explicit configuration

This fictional source assumes its checkout's remote was verified as
`studio/knowledge` with default branch `main`; substitute verified values:

```yaml
sources:
  - id: business-knowledge
    root: knowledge
    catalog: catalog.yaml
    publication:
      repository: studio/knowledge
      base_branch: main
      branch_prefix: knowledge/
```

Validate the complete workspace with the installed runtime and inspect `context`
to confirm the effective source settings, including profile overrides. Do not
write credential values, full authenticated URLs or publication readiness
fields into workspace YAML. The helper's successful runtime/hook result does
not verify remote publication permissions; report that result separately.

Preserve explicit existing choices, including local-only operation. A user can
opt out by leaving the source's publication block absent; explain that updates
needing publication will remain deferred with their signals retained. For an
older configuration with no block and no known opt-out, omission is unknown
intent: explain the recommended PR destination in the setup proposal before
adding it. Do not treat either inferred opt-out or inferred approval as fact.

## Publication behavior

Setup configures the route; `knowledge-compound` owns publication. It reuses an
eligible current-user PR or opens one only when validated changes exist, and
verifies the remote commit and PR head. A human merges or closes it. No changes
means no empty PR. Missing permissions, unresolved ownership and uncertain
publication retain affected signals; an explicit supported no-write disposition
can still finish without a PR. A default publication route never authorizes
automatic merging or unrelated repository changes.
