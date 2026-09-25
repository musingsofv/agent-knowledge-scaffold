# Business context and initial vocabulary

Use this reference to create or complete a workspace catalog. The developer
confirms business meaning and knowledge boundaries; setup translates those
choices into registered identifiers and explicit paths.

## Discover before proposing

Read the selected workspace configuration and each referenced catalog when
present. Then inspect relevant local instructions, README/product descriptions,
business notes and architecture context. Distinguish current facts from ideas,
past decisions and conflicting statements. A repository name alone establishes
neither an organization nor scope membership. Do not search sibling businesses
or copy another installation's vocabulary without direction.

For a blank workspace, ask only what is missing. A useful short batch is:

- What does the business do, and for whom?
- Which work should agents help with here, such as product development,
  customer research or lead generation?
- What is shared across the business, and what applies only to this workspace?

If the existing context answers these, proceed directly to a proposal. Resolve
material contradictions with a focused question; do not choose the newest file
as truth automatically. Technical readiness checks may continue independently,
but do not register disputed scope, topic or entity meanings.

## Propose the smallest useful catalog

Show the intended configuration path, proposed vocabulary and the evidence for
each meaningful choice. Ask for confirmation or corrections together. Use plain
language first, with IDs shown for transparency; do not ask users to design IDs.
Reuse definitions and aliases that already fit instead of creating synonyms as
separate topics or entities.
Include the default PR publication destination from the canonical knowledge
checkout's verified GitHub remote in the same proposal. Follow
[publication setup](publication.md) for destination/account verification and
existing opt-outs; reuse authorization already given.

| Dimension | Initial choice |
| --- | --- |
| Scopes | Explicit applicability boundaries. A solo business usually needs one business scope; add narrower scopes only when the user describes a real boundary. `parents` describes that hierarchy and does not grant access or implicitly expand searches. |
| Topics | A few reusable subjects justified by intended agent work, with useful descriptions. Marketing can use lead-generation or positioning alongside engineering topics. Keep the list flat; no topic inheritance. |
| Entities | Particular named products, services, features or workflows already identified in context. Give each a label and description; omit speculative entities. |
| Languages/technologies | Register the actual relevant stack from context. Do not convert a proposed vendor into an approved-stack decision. Keep selection guidance in authored knowledge. |
| Technology families | Add a family and explicit membership only when it serves known shared guidance. Membership does not prove that a claim applies to the whole family. |
| Environments | Register environments actually used. Leave the registry empty when irrelevant. `any` is an applicability sentinel, not a catalog record. |
| Sources | Preserve configured locations. For a fresh solo workspace, one empty source and its catalog are enough; the source ID identifies storage, not scope. |

Definitions have labels/descriptions and optional aliases. Cite supporting
documentation in the proposal, not invented `evidence` metadata on catalog
records. Do not add arbitrary catalog fields, new document kinds or a marketing
query engine. `topics` and the existing kinds handle business knowledge through
the same interface as engineering knowledge.

## Create or complete the files

After confirmation, register needed identifiers and use them in workspace
membership. Keep all seven registry keys, even when some are `{}`. A new empty
catalog can be populated this way; ordinary `catalog`/`search` requests never
auto-register unknown identifiers. An intentionally empty `applicable_scopes`
list is reserved for a deliberately local/read-only workspace.

Update only the agreed fields. Preserve existing workspace IDs, unrelated
catalog records, source paths, scope parents, publication/settings and comments
where possible. Reuse configured runtime and signal storage paths. Do not
rewrite whole files merely to impose the example's ordering or IDs. Duplicate
YAML keys or conflicting catalog definitions are validation errors: diagnose
them and resolve the intended meaning rather than accepting a last-value win.
Do not fabricate knowledge to fill an empty source. Existing valid knowledge
and user-owned hooks/instructions must survive repeat setup.

For the fresh-workspace default, `knowledge-workspace.yaml` and `catalog.yaml`
are siblings at the scaffold root, while canonical documents live under the
separate `knowledge/` directory. In that default shape the source therefore
uses `root: knowledge` and `catalog: catalog.yaml`; do not place the catalog
inside `knowledge/` unless the developer explicitly confirms a different
layout. Harness hooks are bound for all default targets independently of
automation, unless the user or consumer explicitly selects a narrower target.
For a repository-owned APM installation, use `--apm-mode prepare` and then
`bind` as described in [existing-repository integration](existing-repository.md).
Pausing or omitting scheduled automation never means passing an empty
`--targets` value to setup.

The following paired example assumes the developer confirmed a fictional solo
business called Studio that builds a client-intake product and wants agent help
with lead qualification and software testing. No stack or environment was
specified, so those registries are empty. Its canonical knowledge checkout was
verified against `studio/knowledge` with default branch `main`, and that PR
destination was included in the approved proposal. These are examples, not
defaults for every business.

### catalog.yaml

```yaml
schema_version: knowledge-catalog.v1
scopes:
  org:studio:
    label: Studio
    description: Knowledge shared across this solo business.
entities:
  product:client-intake:
    label: Client intake
    description: The business's product for collecting client requirements.
topics:
  lead-generation:
    label: Lead generation
    description: Identifying and qualifying prospective customers for outreach.
    aliases: [prospecting]
  testing:
    label: Testing
    description: Checking observable product behavior and preventing regressions.
languages: {}
technologies: {}
technology_families: {}
environments: {}
```

### knowledge-workspace.yaml

```yaml
schema_version: knowledge-workspace.v1
workspace_id: workspace:studio
applicable_scopes: [org:studio]
sources:
  - id: business-knowledge
    root: knowledge
    catalog: catalog.yaml
    publication:
      repository: studio/knowledge
      base_branch: main
      branch_prefix: knowledge/
signal_storage:
  scaffold_root: .
  code_root: ..
receipts:
  enabled: true
  directory: ./ai/usage
  retention_days: 30
```

Here the config lives in the durable scaffold itself. If the config lives in a
different producer checkout, source/catalog paths and `scaffold_root` must
instead point to that actual durable scaffold. The `receipts.directory` must
likewise point to its `ai/usage` location, outside knowledge and signal roots. Paths resolve from the config
file, not the request file or shell directory. Create the empty `knowledge/`
directory and ignored `ai/signals/` and `ai/usage/` storage there. Diagnostic
collection can be disabled without disabling mandatory compounding archives
and drain evidence. Preserve an existing usage policy on repeat setup. Optional `setup` preferences retain
the runtime, harness and daily local-time defaults from the skill. Fresh setup
writes explicit publication settings by default so compounding can propose PRs
for human review. Omit the block for an explicit local-only choice; the CLI
still treats absence as disabled. An unresolved destination or authentication
is reported as pending, never silently accepted as complete. Never store
provider credentials or session/task handles in these files.

## Validate the actual installation

Use the existing `setup_runtime.py` helper to install/verify the selected
runtime and APM consumer. Before runtime installation, this paired example
provides the bootstrap shape; afterward the installed `describe` output and
guide own the detailed schema and filter semantics.

Run the resulting absolute launcher with the explicit config path:

```bash
agent-knowledge describe --request-file - <<'YAML'
schema: knowledge-catalog.v1
YAML
agent-knowledge --config /work/studio/knowledge-workspace.yaml context
agent-knowledge --config /work/studio/knowledge-workspace.yaml doctor
agent-knowledge --config /work/studio/knowledge-workspace.yaml catalog --request-file - <<'YAML'
dimension: topics
YAML
```

Check that the returned context and definitions match the confirmed proposal.
Validate existing or newly authored knowledge with `validate`; an empty source
is a valid result, not missing setup. Unknown identifiers, missing directories
and conflicting definitions remain explicit failures. Do not mark setup ready
based only on syntactically valid YAML. Report what was configured, what was
preserved and any provider readiness limits separately.
