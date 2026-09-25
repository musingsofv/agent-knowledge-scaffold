# Guidance Review Checklists

**Date:** 2026-09-21
**Status:** Implemented and verified; approved for main.
**Repo Scope:** agent-knowledge-scaffold
**Primary PR Repo:** agent-knowledge-scaffold

## Table Of Contents

1. [Plan Brief](#1-plan-brief)
2. [Build Contract](#2-build-contract)
3. [Context Used](#3-context-used)

## 1. Plan Brief

### 1.1 Outcome

Agents discover actionable organisational expectations, use checklists where
they help apply or verify those expectations, and report material outcomes
honestly with evidence proportionate to the task.

### 1.2 Feature Shape

#### Today

Guidance already has applicability, requirements and verification sections.
The agent selects documents through ordinary catalog/search/inspect calls and
reads relevant bodies. Compounding maintains existing knowledge and skill
owners from evidence. Neither contract explicitly makes checklists the preferred
form for verifiable requirements or teaches an evidence-backed completion review.

#### Planned Delta

Prefer short checklists when they make supported organisational expectations,
consequential constraints or recurring omissions easier to apply and verify,
across code, infrastructure, marketing or other work. Allow useful judgement
checks without converting all advice into assessments to perform and justify.
Prose remains a valid choice without a special justification. Retain facts,
rationale, history and trade-offs in their natural form.

Teach working agents to apply relevant checks before and during work and review
the final result. Teach compounding to maintain useful checks, their conditions
and ownership, using contrasting examples that also demonstrate when to retain
prose or add no requirement. Final reporting is proportional, with exhaustive
accounting only when requested or warranted by the task's consequences. This is
one instruction/template improvement using existing retrieval, with no checklist
engine. It does not assume checklist formatting improves model performance.

#### Must Preserve

- Existing `kind: guidance`, frontmatter, catalogs, filters, profiles and links.
- Agent-selected queries, progressive body reads and contextual applicability.
- Single instruction owner: the installed guide owns the procedure; package
  bootstrap instructions point to it. Hooks retain their current messages/events.
- Canonical documents hold reusable requirements; task/PR evidence holds outcomes.
- Tool-written receipts remain retrieval/compounding diagnostics, not proof that
  a requirement was followed. No new receipt fields or review artifact schema.
- Existing signal, owner-discovery, publication and guarded-drain contracts.
- Organisation-neutral examples and no bulk conversion of existing knowledge.

### 1.3 Capabilities Delivered

| Status | ID | Capability | Expected Behavior | Important Conditions | Proof Signal |
| --- | --- | --- | --- | --- | --- |
| - [x] | C1 | Author usable review checks | Use conditional checks when they make supported expectations easier to apply or verify | Preserve requirement strength, rationale, exceptions and ordinary metadata; prose needs no special justification | Reviewed technical/business examples; existing validation and installed-template checks |
| - [x] | C2 | Apply and report relevant checks | Agent discovers guidance, applies it and reports material outcomes and verification limits proportionately | Reading is not verification; distinguish failed, unverified and non-applicable outcomes; no false green or edits to shared checkbox state | One bounded live task review against seeded expectations and actual evidence |
| - [x] | C3 | Maintain checks through compounding | Agent chooses useful checks or prose, updates the existing owner, clarifies applicability and avoids duplicates | Distinguish missing knowledge from retrieval/skill failures; no invented policy or rule for every signal | Live compounding of an evidenced correction into the existing owner; retained evidence and valid result |

## 2. Build Contract

### 2.1 Delivery Slices

| Slice | Capabilities Covered | Repo | Base | Existing Surface / Likely Touchpoints | Notes |
| --- | --- | --- | --- | --- | --- |
| S1 | C1-C3 | agent-knowledge-scaffold | Latest main | Guidance template, shared guide, source discovery instruction, compound skill, existing examples and acceptance fixtures | One cohesive slice. Complete the whole change before live proof; no new runtime feature or dependency. |

### 2.2 Implementation

#### Authored guidance and task output

Update `src/agent_knowledge/resources/templates/knowledge/guidance.md` and the
authoring section of `docs/agent-contract.md`:

- Offer a **Review checks** section for prescriptive guidance where it improves
  application or verification. Each item expresses one supported expectation
  and any relevant condition. Indicate useful evidence where appropriate
  without inventing unnecessary verification work. Evidence may be inspected
  code, a document, a test or a reasoned assessment grounded in the task;
  checks need not be mechanically testable.
- Keep short rationale and supported exceptions nearby. Preserve mandatory
  versus recommended wording. Recommendations do not become mandatory policy
  merely because an author expresses them as checkboxes.
- For judgement, describe the considerations that matter. Use a check only when
  it helps assess the decision without imposing a predetermined answer or an
  obligatory essay. Explanatory prose is equally valid. Descriptive product
  facts, concepts and decision history need no checklist conversion.
- Group coherent checks with shared purpose/applicability. Split independently
  useful guidance when those differ, not one file per item or code file.
- Reference existing automated checks/runbooks instead of duplicating their
  internals. Markdown checkboxes are presentation, not parsed runtime state.

For example, the body of fictional input-validation guidance could contain:

```markdown
## Applies when

Adding or changing an untrusted input boundary in a TypeScript service.

## Review checks

- [ ] Validate incoming data with the approved Zod schema before application use.
  Evidence: the boundary passes the parsed result to application code.
- [ ] Verify relevant invalid input produces the documented error response.
  Evidence: focused invalid-input tests for the changed behaviour.

## Rationale

TypeScript types do not validate data arriving at runtime.
```

Keep the ordinary frontmatter on the containing document, using registered
identifiers. Use the contrasting authoring examples below for business and
judgement cases; fictional requirements are example inputs, not scaffold policy.
Adapt `examples/knowledge/guidance/testing.md` for a complete, valid technical
example; do not create a separate checklist directory or catalog kind.

Add **Apply guidance and report review results** to the shared guide. A short
pointer in the package's source discovery instruction makes it discoverable;
do not copy the procedure into hooks, generated instructions or multiple skills.

The working agent:

1. Retrieves applicable general and specialised guidance before consequential
   decisions; searches again if the work reveals a new relevant surface.
2. Assesses conditions using the task, actual changes and their effects. File
   names and diff size alone do not establish applicability or an exemption.
3. Reviews the final state against the selected checks. Reuses existing evidence
   only when it covers that state; a later edit can invalidate an earlier result.
4. Reports material fulfilled constraints, unresolved gaps and verification
   limits in the existing task response, PR or review artifact, with evidence
   where available. Use a checklist when it helps; exhaustive item accounting
   is reserved for requests or tasks that warrant it. Explain non-applicability
   where material, without listing every irrelevant check or repeating detail
   already present in the owning review artifact.

An illustrative task review, separate from canonical knowledge:

```markdown
Reviewed against: Input validation guidance.

- [x] Verified: parsed input reaches application code - boundary code inspected.
- [ ] Failed: malformed input still returns the wrong response - test output.
- [ ] Unverified: deployed behaviour - deployment has not been performed.

Test-factory guidance was not applicable: no test entities were introduced.
```

Only verified checks receive `[x]`. Failed, blocked and unverified requirements
remain visibly unresolved; non-applicable checks are not counted as passes.
For a judgement check, verified means the required assessment was performed and
supported, not that the chosen design is objectively optimal. A bare "considered"
is insufficient. Non-applicability needs task context, not agent preference.
Evidence should reference real paths/results, not repeat these placeholder
phrases. This is a human-readable convention, not a required output schema.
Do not produce an empty checklist for conversational tasks or invent requirements
when no applicable guidance is found. Report material discovery limits honestly.
The CLI does not enforce task completion or independently validate these claims.

#### Compounding and ownership

Extend the existing authoring/owner-selection procedure in
`packages/knowledge-agent-pack/.apm/skills/knowledge-compound/SKILL.md`:

- When creating or updating guidance, consider whether a short checklist would
  make its expectations easier to apply and verify. Prefer checks for supported
  organisational expectations, consequential constraints and recurring omissions.
  A single successful approach does not establish a general requirement.
- Make each check clear about when it applies and what should be true. Indicate
  useful evidence where appropriate without inventing unnecessary verification
  work. Keep requirement strength, rationale and supported exceptions intact;
  a recommendation does not become mandatory because it becomes a checkbox.
- For decisions requiring judgement, describe the considerations that matter.
  Use a check only when it helps assess the decision; retain explanatory prose
  where that communicates better. No special justification for prose is needed.
- Reference existing automated checks instead of reproducing their internals.
  Use the installed template and guide rather than a second specification.
- Search and update the existing owner. Consolidate duplicate checks and retire
  obsolete ones when supported; do not append a check for every signal.
- If a missed expectation already exists, investigate discovery, wording,
  applicability or the skill's review procedure. Fix the responsible owner;
  another knowledge document may not be needed.
- An already-covered observation needs no edit. Do not expand individual guidance
  merely to repeat the installed guide's shared execution or reporting conventions.
- Preserve original strength and supported scope. A task-specific exemption is
  not automatically a permanent exception. Do not convert fictional examples
  into organisational policy or mark canonical boxes with task outcomes.

#### Few-shot authoring examples

Teach these contrasts in a short reference linked from the compound skill's
authoring step. Keep the core instruction above concise; the shared guide owns
general semantics. Examples are fictional and conditional on the stated
evidence. They demonstrate authoring decisions, not policies for consumers to
adopt. First identify the supported expectation and existing owner, then choose
the smallest useful change. Body excerpts retain the containing owner's ordinary
frontmatter.

**1. Test factories: preserve applicability and legitimate exceptions.**

Input: This repository's adopted testing convention uses shared factories for
valid domain objects and allows hand-built malformed inputs for validation tests.

Weak: `- [ ] Always use factories in every test.`

Better:

```markdown
- [ ] When tests need valid domain objects, use the shared factories and override
  fields relevant to the scenario. Intentionally invalid inputs may be
  constructed directly for validation tests.
```

Why: The check captures the actual convention without prohibiting its exception.
Relevant test setup supplies evidence; it needs no separate reporting artifact.

**2. Input validation: describe the property, not a token mention.**

Input: This TypeScript API has adopted Zod at external JSON boundaries. A defect
occurred because code validated the payload but then used the original object.

Weak: `- [ ] Use Zod.`

Better:

```markdown
- [ ] When adding or changing an external JSON boundary, validate the payload
  with its Zod schema before application use, and pass the parsed result onward.
  Check the boundary-to-handler data flow and relevant invalid-input tests.
```

Why: Importing or calling a validator is insufficient. Update the existing
validation owner to capture the demonstrated omission within its supported scope.

**3. Marketing: preserve recommendation strength.**

Input: The campaign owner recommends one primary call to action for acquisition
emails. Existing newsletter guidance explicitly allows several destinations.

Weak: `- [ ] Every marketing email must contain exactly one link.`

Better:

```markdown
- [ ] For acquisition emails, prefer one primary call to action aligned with the
  campaign objective. Supporting links can remain. Apply newsletter guidance
  to newsletters instead.
```

Why: A recommendation stays a recommendation, a call to action is not a link
count, and one campaign format does not determine every marketing format.

**4. Architecture: retain useful trade-offs as prose.**

Input: A recorded design decision keeps a small deployment together because its
owners and release cadence are shared. A separate service might help if those
conditions change; no universal service-size rule was adopted.

Weak: `- [ ] Every new capability must be a separate service.`
Also weak: `- [ ] For every edit, document scalability, cost and every failure mode.`

Better: Update the existing decision's prose: "Keep these components deployed
together while ownership and release cadence are shared. Reconsider separation
if independent deployment becomes necessary; weigh that benefit against added
operational cost and cross-service failure modes."

Why: This records the current choice, rationale and reconsideration condition.
It need not become a required assessment for unrelated work or a checkbox.

**5. Automated enforcement: reference its owner without copying it.**

Input: The repository already documents a required `npm run check:boundaries`
gate which enforces its approved dependency directions. A signal reports a
violation caught by that gate; the relevant skill already runs it.

Weak: Add a second checklist enumerating every allowed import and folder pair.

Better: Record an already-covered disposition naming the gate and its existing
guidance. If discovery was actually deficient, amend that owner to point at the
gate. Do not maintain a prose copy of its rule set.

Why: Tool-enforced policy already has an owner. Routine successful detection
does not establish a need for more guidance.

The same ownership principle applies to shared reporting conventions. If a
signal proposes adding "report unavailable verification as unverified" to a
document that already requires verification before sending, the installed guide
already explains that outcome. Record it as covered unless evidence supports a
distinct domain clarification; do not copy the reporting procedure into the owner.

**6. One successful tactic: do not invent a durable requirement.**

Input: One launch email used a humorous subject line and performed well. There
is no adopted tone policy or evidence that humour caused the result.

Weak: `- [ ] Always use humour in launch-email subject lines.`

Better: Add no guidance check. If the result merits durable campaign history,
retain the observed outcome and uncertainty there. Otherwise use the existing
no-update disposition; archived input and the receipt preserve the observation.

Why: A signal and a successful outcome are not enough to establish a general
rule. Compounding can finish successfully without adding canonical knowledge.

#### Important failure cases

| Situation | Expected behaviour / review evidence |
| --- | --- |
| Check cannot be verified or evidence is stale | Explicit unverified/blocked outcome; no checked box or blanket compliance claim |
| Applicability is unclear or guidance conflicts | Identify the ambiguity/conflict and follow existing instruction precedence; seek clarification when needed, without inventing an exemption |
| Lookup fails or finds no relevant guidance | Distinguish failed discovery from an empty result; no claim that every requirement was covered |
| A signal repeats an existing check | Inspect why it was missed and reuse the owner; do not add redundant guidance |
| User interrupts before final verification | Describe outstanding checks in the existing handoff; do not fabricate completion or a new resume-state store |

#### Validation

| Capability | Level / existing surface | Proof |
| --- | --- | --- |
| C1 | Existing example validation and retrieval walkthrough | Authored Markdown remains valid/searchable/inspectable with unchanged metadata; prose-only guidance remains valid |
| C1-C3 | `tests/integration/apm/test_package_contract.py` and isolated fresh-consumer smoke | Existing skill constraints pass; installed guide/template match source; the updated procedure is reachable through source-owned instructions |
| C2-C3 | Bounded live acceptance using existing disposable-consumer/provider support | Model applies checks with grounded outcomes, then compounds an evidenced wording correction into its existing owner |

Reuse existing tests; add a focused behavioural assertion only where coverage
is missing. Do not create prose-snapshot tests, a checklist parser, a new harness
framework or tests that only require particular wording.

After implementation, run the repository gates (`uv run pytest -q`, Ruff lint
and format checks, and `uv run mypy`), build with `uv build`, and run
`tests/e2e/fresh_consumer_smoke.py` as documented in `docs/r8-harness-proof.md`.
Regenerate affected APM projections from authored sources through normal tooling.

For live proof, use one disposable Claude session after the complete slice:
give it a small fictional marketing task, applicable email checks, an unrelated
technical checklist and evidence with one unmet requirement and one unavailable
verification. It should assess actual conditions, correct what it can, and
report unresolved work without marking it verified. Then provide a supported
signal clarifying an existing check and invoke the installed compound skill.
Inspect the final response, canonical diff and validation output: no duplicate
owner, no canonical completion ticks, and no invented policy. Keep publication
disabled and retain unpublished update signals under the existing drain policy.
Reuse existing E2E helpers (including `final_pass_acceptance.py` where useful).
The existing no-write compounding smoke alone does not prove checklist authoring.

This live run proves the installed flow can work, not that checklist formatting
improves quality or cost. Before making a broader checklist-first policy, compare
the same requirements as ordinary guidance and as conditional checks, evaluating
deliverables independently of the agent's self-report. Compare omissions, false
verification, unnecessary constraints and time/token cost; assess compulsory
final checklist reporting separately. That performance experiment is not a new
framework or a prerequisite for this bounded instruction change.

Retain live evidence under ignored `.cache/` and record a brief outcome in this
plan. Report installed proof separately from live semantic proof; this focused
Claude run does not establish new live behaviour claims for other providers.
No scheduler registration or host-wide configuration changes are part of proof.

#### Build evidence (2026-09-21)

- Updated the guidance template, shared authoring/review guide, fictional testing
  example, compound skill and its linked six-example `guidance-authoring.md`
  reference. The source discovery instruction has one guide pointer; APM
  regenerated the installed projections and lock inventory. No runtime,
  taxonomy, hook event or receipt schema changed.
- `uv run pytest -q`: **1367 passed** on the full rerun. The initial run had
  **1366 passed, 1 failed** in the unchanged concurrent receipt append test
  (`tests/integration/infrastructure/test_usage.py::test_concurrent_appends_preserve_every_complete_record`),
  with an ENOENT acquiring its temporary lock. The focused usage suite then
  passed **10/10** and the full rerun passed; no receipt-code change was made.
- Ruff lint/format, mypy, `uv build`, skill-creator validation, all ten example
  documents and `git diff --check` passed. The final wording correction also
  passed the eight package-contract tests. No prose-snapshot tests were added.
- Fresh consumer installation passed for Codex, Claude and Copilot, including
  installed guide/template byte parity and provider hook fixtures. Final skill
  and reference copies were also compared with authored sources. Evidence:
  `.cache/guidance-checklists-followup/fresh-consumer.json`.
- Initial live Claude Opus 5 session
  `374cb0b6-f14b-4250-b541-435d6db131b6` corrected an unsupported marketing claim,
  preserved required footer links, reported unavailable rendering as unverified,
  and left canonical knowledge unchanged during the task. Compounding read the
  installed example reference and updated the existing owner, but artifact review
  caught redundant shared reporting text. The original evidence is retained in
  `.cache/guidance-checklists/live.json`, including that concern.
- Fixed forward by clarifying that already-covered observations need no edit and
  that shared execution/reporting conventions stay in the guide. A fresh Claude
  Opus 5 session `bea6ba5f-66f4-4945-9ee4-87fad84da0ca` invoked the updated skill
  and amended only the owner-supported CTA clarification. The rendering check,
  prose architecture decision and unrelated technical guidance stayed unchanged;
  metadata and recommendation strength were preserved, with no canonical ticks
  or new knowledge files. It recognised the reporting convention as covered and
  deferred the separate uncertain waiver question without adopting policy.
- Independent file/CLI checks verified valid knowledge, a closed run, correlated
  search/inspect/compounding receipts, both selected inputs retained, and two
  archives with byte-identical input contents. Final evidence:
  `.cache/guidance-checklists-followup/live.json` and `structural-checks.json`
  in that directory. The fresh rerun did not separately read the example
  reference; it used the main skill. Example installation is proven, not
  guaranteed reading on every future run.
- The live run also retained a new follow-up signal about undisclosed
  `publication.status` values after recovering from a rejected guessed value.
  This pre-existing CLI discoverability gap remains outside this slice.
- One reviewer was used only for review. No remote publication or scheduler was
  exercised. This is bounded integration/behavior proof, not a performance
  comparison or new live behavior proof for Codex/Copilot. The fresh run's
  retained uncertain signal does not prove that every hypothetical gap will be
  discarded.

### 2.3 Deployment

Ship the updated guide/template with the normal Python package and the updated
skills/instruction through APM. Refresh consumers through existing installation
and compilation. No configuration migration or corpus rewrite is required;
existing prose guidance remains usable and compounding can improve it when
relevant evidence arrives. Revert the instruction/template commit and reinstall
to roll back. Stop for review after the one slice is implemented and verified.

## 3. Context Used

- User decisions in this discussion: minimal change; actionable guidance with
  useful conditional checks; contextual applicability; honest, proportional task
  reviews. Following critical review, the user approved narrowing the original
  checklist-first policy: prose needs no special justification, not every signal
  becomes a rule, and exhaustive final accounting is not the default. The user
  requested contrasting few-shot examples for compounding.
- `.apm/instructions/scaffold-local.instructions.md`: neutral repository scope,
  authored instruction ownership and repository-native gates. Local scope governs
  over generic planning-skill defaults to consult an organisation's corpus.
- `src/agent_knowledge/resources/templates/knowledge/guidance.md`: existing
  applicability, requirements, rationale and verification structure.
- `docs/agent-contract.md`: agent-selected retrieval, authoring and reflection;
  source file packaged into the installed guide by `pyproject.toml`.
- `packages/knowledge-agent-pack/.apm/skills/knowledge-compound/`: existing owner
  discovery, evidence, applicability and publication/drain boundaries.
- `tests/e2e/fresh_consumer_smoke.py`, `tests/e2e/final_pass_acceptance.py` and
  `docs/r8-harness-proof.md`: reuse installed-resource and live-agent proof.
