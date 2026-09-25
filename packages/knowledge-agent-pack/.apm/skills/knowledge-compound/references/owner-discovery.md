# Find the authoritative owner

Read this before selecting a destination for a compounding batch. Keep discovery
metadata-first and report its boundaries; no single inventory proves exhaustive
semantic coverage.

## Skills and their supporting resources

1. Review the originating workspace's available skill inventory by name,
   description and source/location, including skills the signal author did not
   use. Use the harness inventory and accessible package metadata for identified
   source packages. Reuse it across the batch, refreshing when sources change.
   If the compounding harness cannot access that workspace's inventory, record
   the limitation rather than declaring a skill absent.
2. Select plausible descriptions and read those skill bodies. Follow relevant
   references, templates or scripts to understand where the claimed behavior
   originates. Do not open every skill body or attachment for every signal.
3. Discover knowledge vocabulary with `catalog`, search plausible owners with
   text and canonical filters, inspect previews, then read selected sections.
   Skill inventory and knowledge discovery are complementary: the knowledge CLI
   does not index skills. Do not introduce a skill knowledge kind, catalog
   dimension or signal hint; use the existing signal body and evidence for
   candidate names, source/version references and uncertainty.
4. Compare the actual claim with each candidate using the ownership decision
   below. An already-covered finding names the actual owner and evidence; it
   does not justify another duplicate document.

## Choose the smallest sufficient owner

Choose the smallest authoritative owner that fully addresses the observation.
Canonical knowledge belongs in the configured central scaffold sources. Local
repositories retain their authored skills and instructions; do not create a
repository-local knowledge document to compensate for a skill defect.

- Update the existing skill when the finding corrects its procedure,
  instructions, examples, templates or scripts. A skill-only improvement is a
  complete compounding outcome; it does not require a knowledge document.
- Update central knowledge when the finding establishes a durable fact,
  constraint, decision or procedure useful independently of that skill.
- Update both when there is independently useful knowledge and the skill also
  needs a change to apply it. Keep the fact or procedure in its knowledge owner
  and reference it from the skill where appropriate instead of copying it.
- For an applicable instruction defect, amend its authored source using the
  tracing procedure below. It likewise needs no companion knowledge document
  unless that document serves an independent purpose.

Repository specificity alone does not determine the destination. A repository's
durable constraint may belong in central knowledge with narrow applicability;
a correction to its skill's command may be fully addressed in the skill. Ask
whether the information would still need to be discoverable if the skill did
not exist. Use that question to assess independent usefulness, not as an
automatic test. Explain in the disposition rationale why the selected owner is
sufficient and what independent purpose any additional document serves. Signal
archives and receipts retain the observation and reasoning without requiring a
canonical knowledge entry.

| Observation | Owner |
| --- | --- |
| The repository's testing skill calls the wrong npm script | The local skill or its supporting script |
| The release skill points to the wrong build-output directory | The local skill, template or script that owns the path |
| Adopted product policy requires preserving customer exports for seven years | Central knowledge, with evidence and supported applicability |
| A deployment migration is required for manual and automated releases, and the release skill omits it | The central runbook and the affected skill |

## Trace instructions to their source

For an agent-behavior finding, inspect the originating workspace's active root
and file-scoped instruction sources as well as relevant skills and knowledge.
Trace compiled text using its package/source attribution and installation
metadata. Read the authored rule, its applicability and the guide/skill/knowledge
owners it references. A generated `AGENTS.md`, `CLAUDE.md` or Copilot projection
is not a canonical write target. A knowledge search does not enumerate active
instructions.

This package's always-on owner is:
`knowledge-agent-pack/.apm/instructions/agent-knowledge-discovery.instructions.md`.
The `knowledge-agent-pack/` prefix names the package, not an absolute checkout.
Its section headings identify the individual rules. Resolve the authoritative
checkout through the installation metadata; an installed snapshot is not proof
that its writable upstream source is available.

Within an authorized source, choose whether to amend, remove or narrow a rule,
or move excessive detail into its guide, skill or knowledge owner. Keep one
always-on file per owning package/workspace. Do not merge unrelated dependency
or consumer instructions. Global instructions and patterns applying to all files
are always-on under supported APM semantics; `src/**/*.py` is still scoped.
Do not flatten a scoped rule into a global file and widen its applicability.

Use normal package reinstallation/compilation to refresh projections. Verify
that removed text is absent, replacement text appears once in each applicable
surface, portable source attribution survives, and unrelated consumer rules
and file-scoped applicability are preserved. Independent generated surfaces
can contain the same owned rule; do not author duplicate copies to maintain them.

## Publish the owner that was actually changed

### Standing authorization for consumer PRs

Enabling compounding includes authorization to prepare validated changes, push
an isolated branch and open or update a PR for human review in the configured
knowledge repository and every participating consumer repository. This covers
canonical knowledge and the consumer's authored skills, instructions and their
supporting references, templates or scripts. It does not authorize unrelated
product changes, automatic merging or force-pushing. Preserve an explicit user
opt-out or narrower scope; do not invent a per-repository opt-in or treat an
older agent-authored restriction as a user decision.

Use the participating-consumer routes recorded by setup in the automation
prompt, or the user's explicit context for a manual run. A shared profile or
inbox does not restrict publication to the automation's working directory.
Adding a consumer carries the same compounding PR policy unless the user says
otherwise. Resolve its verified remote, base branch and authored source using
repository instructions and installation metadata; deriving those values is
work for the agent, not another permission request. A repository mentioned only
in a signal or an installed third-party dependency is not automatically a
participating consumer, and token access alone does not establish ownership.

For example, a shared inbox serving a mobile app and a website can produce a
knowledge PR and a website-local skill PR in their respective repositories.
The website correction does not need another publication opt-in. A defect in
an unrelated external package still requires resolving that owner's route.

After publication, report the PR link as **ready for human review**, not blocked
on authorization. Human review/merge remains the approval boundary; verified
PR publication is sufficient for the existing guarded drain procedure, without
waiting for merge. If ownership, access or required validation really is
unavailable, retain the affected input with the exact missing prerequisite and
continue independent work. A local patch awaiting push is not a published PR.

Resolve the authoritative package or repository before any skill/instruction
edit. Preserve a safe source identity and relevant version/evidence reference
in the disposition; a display name or copied local installation alone is
insufficient. Catalog/knowledge validation does not validate a skill or its
package assets. Run the owning package's native skill/APM checks for authorized
changes, and validate linked knowledge changes with the knowledge CLI.

A skill-only update uses the skill repository's authorized publication route
and native checks. Record an update disposition with that repository/path and
its publication evidence; the absence of a central change is not a no-write
outcome. Current drain evidence covers one publication repository per request.
Keep a signal requiring changes across repositories deferred with the relevant
proposals and evidence; one repository's publication cannot complete all owners.

If the source or publication route is unavailable, or an explicit user
restriction excludes the change, keep an actionable deferred signal/proposal
naming the candidate and missing prerequisite. Do not defer a participating
consumer's PR merely to request authorization already supplied by setup.
Finding an external owner is not verified publication and does not justify
draining its unresolved update. Keep agent-reported publication evidence distinct
from independently verified results. Receipts and signal archives are written
by the CLI; never hand-author usage records or move/delete the captured inputs.
