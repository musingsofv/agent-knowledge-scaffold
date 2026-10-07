# Complete multi-repository compounding outcomes

Date: 2026-10-07
Status: implementation validated; publication and coordinated rollout next
Branch: `nik/compound-upgrade-guidance-20261007`
Starting revision: `2c0e7a5533b487b7922c931d683f0f9294e774bf`

## Purpose and semantics

A signal can require independent updates to canonical knowledge and a consumer's
authored skill or instructions. The existing singular publication assertion
cannot establish coverage of those required destinations. Add explicit evidence
per repository while keeping semantic judgement and remote verification with the
agent. The CLI validates declared coverage and protects the selected input; it
does not discover missing obligations, infer authorization or contact a provider.

Compounding completes the selected knowledge or guidance outcome. An accepted
design decision can be recorded as implementation deferred and still be fully
compounded. Product plans retain future implementation work. Genuinely unresolved
knowledge, skill or instruction authoring obligations continue to retain inputs.

## Acceptance

- Replace the singular publication request and global verification boolean with
  `publications`, containing independent repository, status, verification and
  exact published commit evidence; a PR number is optional. Reject duplicate or
  conflicting repository entries and obsolete request fields.
- For write outcomes, resolve every final required owner through its explicit
  repository or configured source publication route. Complete verified coverage
  allows drainage; missing, mismatched, pending or unverified coverage retains
  the affected signal. Unrelated evidence cannot cover another owner.
- Define write-disposition owners as required authoring destinations. Discovery
  candidates, supporting citations and future product changes do not become
  additional write obligations. Never omit a genuinely required owner to pass.
- Confirmed `keep` and `skip` outcomes require their rationale and normal file
  safety checks, without requiring a new PR or publication route.
- Capture optional bounded change patches separately for each repository, with
  distinct tool-selected paths and reported capture results. Patch availability
  does not establish or negate the agent's separate remote-verification claim.
- Preserve immutable archives, complete-byte snapshots, containment and identity
  checks, durable pre-removal intent, configured-route freezing, run coordination
  and retention of changed, new, malformed or uncertain inputs.
- Synchronize the CLI schema, guide, skill, examples and tests. Keep historical
  receipts as historical evidence without adding legacy request aliases.
- Verify complete and partial multi-repository outcomes, source route resolution,
  mixed per-signal coverage, duplicate/conflicting entries, no-write outcomes,
  separate patch artifacts and the existing adversarial cleanup cases.

## Integration and proof

Run the native Python gates, build, and isolated fresh-consumer lifecycle/provider
fixture proof. Report native model delivery separately; this change does not
alter hook transport or authorize live scheduling tests.

Publish the validated source before a dependent installation. Use the existing
upgrade skill and consumer-owned APM workflows for coordinated runtime/resource
refresh, preserving local state and consumer ownership. Reconcile existing
retained signals only through the installed CLI after verifying its selected
profile, readiness, activity, publication evidence and current snapshots.

## Current checkpoint

Runtime, guide, skill, schema, examples and regressions are complete. Independent
source/guidance and regression reviews found no actionable issues. The final
full suite passed 1,949 tests; Ruff, formatting, mypy, wheel/sdist build and
whitespace checks passed. A migrated shared fixture initially made one route
change test a no-op; its override now uses a genuinely different repository and
the complete suite passed after that correction.

The isolated fresh-consumer proof passed all 21 check groups, including resource
parity, all three provider fixtures, portable repeated binding and guarded signal
cleanup. APM 0.29.0 regenerated the deployment lock; compilation left the harness
instructions unchanged, and all 10 local audit checks passed with no drift.
Evidence: `.cache/multi-repository-pytest.log` and
`.cache/multi-repository-fresh-consumer.json`. These are deterministic and
provider-fixture checks, not fresh live-model or scheduler proof.

Earlier upgrade preflight, selected-target inventory and local APM cache handling
changes remain intact. Publish this source before a dependent installation.
Coordinate runtime and installed skills because the request contract changed;
do not replace a live shared runtime while consumers still prescribe the old
request. No live runtime, profile, automation or signal state was changed during
implementation. Historical receipts remain untouched.
