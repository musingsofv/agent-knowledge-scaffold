# Author useful guidance

Read this when compounding an observation into guidance. The installed guide's
"Author canonical knowledge" section owns body semantics. First identify the
supported expectation and existing owner, then choose the smallest useful
change. A checklist, prose update, discovery repair or no update can each be a
successful outcome.

These examples are fictional. Their expectations apply only when supported by
the stated evidence; do not adopt them as policy for another workspace. Body
excerpts retain the containing owner's ordinary frontmatter.

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
