# Dedicated knowledge upgrade skill

Date: 2026-10-07
Baseline: b39762895ce386d988c3b7e85dc04208156444bf
Status: complete and locally verified on `nik/knowledge-upgrade-skill`.

## Contract

Extract a discoverable `knowledge-upgrade` skill without losing existing upgrade
requirements. Cover local and container installations. Keep one owner for each
procedure and reuse setup helpers; do not change runtime behavior, install real
consumers, register automations, publish, or merge as part of this refactor.
Distributed material remains organization-neutral. Existing setup selection,
publication, credential, sandbox and approval boundaries remain authoritative.

## Obligation and ownership map

| Existing authority / obligation | Destination and verification |
| --- | --- |
| Setup `scaffold-upgrades.md`: first adoption, private destination, one checkout/two remotes, exact identity, no overwrite, bootstrap publication | Setup `references/knowledge-instance.md`; preserve adoption/bootstrap sections and incoming links. |
| Setup `scaffold-upgrades.md`: verified instance role, maintained authored route, no generated edits | Setup retains first authoring; new upgrade skill migrates existing authored maintainer routing through the owner's compiler. |
| Setup `scaffold-upgrades.md`: provenance/common history, no guessed baseline or unrelated-history merge | Upgrade `references/scaffold-upgrades.md`; copies without ancestry remain a separate verified migration. |
| Setup `scaffold-upgrades.md`: deliberate content merge, instance content, generated-source resolution, checks and ancestry-preserving PR | Upgrade reference; preserve no-ours/no-squash/no-rebase requirements and existing publication authorization. |
| Runtime vs source vs APM package vs consumer state are separate | Upgrade coordinates explicit target revision and reports each result independently; consumer-only refresh is supported. |
| Setup runtime helper: supported interpreter, install vs existing verification, exact payload, complete package/helper | Setup remains mechanism owner; upgrade calls matching helper and preserves runtime/package alignment. No copied helper. |
| `existing-repository.md`: APM pin, complete target set, local skills, source ownership, prepare/install/compile/bind/final-index checks | Setup reference stays authoritative; upgrade directly routes and coordinates it. |
| `containers.md`: tool/harness location, developer-owned image/user/tools, immutable rebuild or writable install, in-container paths, exact launch integration | Setup reference stays authoritative; upgrade covers both runtime routes, requires actual running image proof and no host-venv reuse. |
| `container-profiles.md` / `profiles.md`: guarded local projection/refresh, relative path bases, preserved defaults/env mappings, blank values and strict activation | Setup references remain authoritative; upgrade preserves selected registry/profile/credential values and routes changed projections through guarded refresh. |
| `portable-hooks.md`: per-environment runtime, portable shared outputs, binding/trust/firing separated, private activation | Setup remains mechanism owner; upgrade preserves mode, rebinds after APM and verifies fresh native sessions. |
| `local-compounding.md`: one shared owner/log, native workers, existing schedule/fallback, activation after final checks, active-run safety | Reused without a new store/trigger; upgrade preserves history, pending inputs and matching agreement, and distinguishes compounding readiness. |
| Launch readiness: receipts/signals, credentials, hooks, mounts/locking and repeat/reuse evidence | Upgrade selects affected acceptance for host/container; missing live proof stays explicit, no sandbox/trust widening. |
| Root/package inventory and incoming maintenance routes | Update authored instruction, docs and package catalog; regenerate APM projections, verify installed sibling links and all three skills. |

## Validation and review

- Focused package/deployment tests verify the new skill and cross-skill links in
  real APM-deployed catalogs, including APM's verified installed-package link
  relocation; do not merely match procedural prose.
- Run skill validation, full native gates, build and isolated fresh-consumer
  installation/compilation/binding checks. This is a guidance/package refactor;
  unchanged live runtime tests do not need another provider/Docker run.
- After implementation, one consolidated independent read-only round assesses
  obligation preservation and realistic local/container upgrade scenarios.
  Resolve justified findings and rerun affected checks; no repeated approval loop.
- Preserve historical proof as historical. New evidence and current checkpoint
  stay here or in the ignored `.cache/knowledge-upgrade/` directory.

## Consolidated review and fixes

One independent read-only round covered original-versus-replacement semantic
preservation, deployment correctness, and forward walkthroughs of host and
immutable/writable-container upgrades. No further review round is planned.

- Semantic/activation review found no lost obligations against the original
  setup/upgrade, container, profile, hook and compounding authorities.
- Deployment review reproduced APM 0.29's legitimate cross-skill link relocation
  into its installed package. The initial new byte-equality and catalog-only
  checks rejected that output. Checks now account only for verified destinations
  while preserving all non-link content, scripts, resource sets and anchors.
- Forward testing found install mode does not perform the exact runtime payload
  comparison promised by the draft. Upgrade now explicitly runs the matching
  helper in `existing`/`prepare` after installation and after later install-mode
  binding. No runtime behavior change is needed.
- Initial full suite: 1,876 passed, one pre-existing fixture expectation failed.
  Baseline's Copilot proof already permits `/usr/bin` for its observed venv
  interpreter, but its exact-directory assertion omitted it. The stale
  assertion was corrected without changing permissions; exact allowlists/denials
  remain enforced. This test-only correction is isolated in commit `c70f115`.
- Source integration examples now explicitly substitute the selected upstream
  commit when it differs from the fetched branch tip.

## Current checkpoint

- Clean isolated worktree created from latest verified `origin/main`.
- Skill extraction and maintained callers are complete; setup mechanisms stay
  in place. All three root harness projections were regenerated with APM 0.29.
- All consolidated findings are fixed. Final full suite: **1,885 passed** in
  110.09 seconds. Focused post-fix suite: **108 passed**. Ruff, formatting, mypy,
  skill frontmatter validation and wheel/sdist build passed.
- Isolated fresh-consumer proof passed all 21 check groups for Codex, Claude and
  Copilot. Before and after reinstall/rebind, each installed/package/native
  catalog has 19 Markdown documents and 66 verified local links/anchors. Resource
  checks cover scripts, stale/missing files, exact owning-package destinations
  and unchanged non-link bytes. Retrieval, receipt/signal lifecycle, guarded
  cleanup, provider fixtures and unrelated hook preservation passed.
- Final evidence: `.cache/knowledge-upgrade/pytest.log`, `fresh-consumer.json`,
  `fresh-consumer.log`, `skill-catalogs.json`, `ruff.log`, `format.log`,
  `mypy.log`, `build.log`, `apm-install.log` and `apm-compile.log`. Initial failed
  logs retain the `-initial` suffix. APM's global-pattern warnings are expected
  for the repository's global instructions.
- No unresolved review findings. Independent forward testing is a read-only
  scenario walkthrough, not live host/container installation proof. Existing
  Docker/native-provider evidence remains historical; unchanged runtime behavior
  did not require rerunning it. Native scheduling tests remain paused.
- No real consumer, automation or credential changes. One durable observation
  about APM cross-skill relocation was recorded through the selected runtime.
  Publication and consumer rollout are outside this request; no push/PR/merge.
