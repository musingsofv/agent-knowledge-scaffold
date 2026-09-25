# Agent knowledge CLI examples

**Status:** Current retrieval, authoring and compounding CLI contract, including
exact-session signal discovery. The [fictional fixtures](cli-examples/README.md)
are executable inputs; signal operations require the independent Git origin
described below.

## Setup and command conventions

Imagine the fixture tree installed under `/work/code`: `orders-api/` is a Git checkout, and `commerce-knowledge/` holds the configured catalog, canonical knowledge and a separate ignored signal inbox. The examples use that fictional absolute location consistently. Substitute the real configured location when implementing tests or onboarding a consumer.

The consumer's [workspace file](cli-examples/orders-api/knowledge-workspace.yaml) selects `commerce-knowledge` and explicitly lists `org:example`, `group:commerce`, and `repo:orders-api`. The [catalog](cli-examples/commerce-knowledge/catalog.yaml) registers every identifier used by the successful requests below. Nothing infers a hierarchy from those names.

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json context
```

Global options go before the command. Requests are JSON or YAML. `--request-file -` explicitly reads stdin; `--request-file query.yaml` reads a file relative to the process cwd. Path values inside requests resolve against the configuration directory, while a document reference's `path` resolves inside its named source. Without `--request-file`, operations that accept an empty request use their documented defaults and never wait for stdin.

All methods return JSON by default, including `status: ok|error` and `diagnostics: []` or structured diagnostics. Exit 0 means success, including an empty search; exit 2 means invalid input/configuration/content; exit 3 means a runtime I/O failure. Diagnostics carry `code`, `message` and an actionable `remediation` when available. Text output is a rendering of the same result.

## Every CLI method

| Method | Why an agent calls it | Request keys |
| --- | --- | --- |
| `describe` | Learn the contract and find installed authoring templates. | Optional `schema`, `field`. No config required. |
| `doctor` | Check this process's installation and selected workspace setup. | Optional `mode`, `expected_workspace_id`. |
| `context` | Obtain configured scopes, sources and storage locations. | No request fields; use explicit config. |
| `catalog` | Discover exact IDs or inspect technology-family membership. | Required `dimension`; optional `text`, `ids`, `sources`, `limit`, `continuation`. |
| `search` | Find previews using explicit predicates. | Exact filters, `text`, `sources`, `limit`, `continuation` from the core plan. |
| `inspect` | Preview one known file and explore its outline/links. | Required `document`; optional `expected_fingerprint`, `limit`, `continuation`. |
| `validate` | Check all selected sources or explicit authored files. | Exactly one of `sources`, `documents`, `signal_files`. |
| `signal record` | Persist one already-authored Markdown observation. | Required `file`. Origin is checked against configuration and durable Git identity. |
| `signal list` | Inventory signals for the configured originating workspace. | Optional `include_shared` (false), exact `session_id`, `limit`, `continuation`. |
| `compound` | Read the advisory log, start/finish a run or drain handled signals. | Required `action`; action-specific fields from `describe` and the compounding skill below. |

`document` is `{source, path}`; `documents` is a list of those objects. `signal_files` and `file` are filesystem paths. Catalog dimensions are `scopes`, `entities`, `topics`, `languages`, `technologies`, `technology_families`, and `environments`. A `field` selector requires a `schema`. The default `describe` summarizes every operation, lists supported schemas and reports installed guide/template paths; it does not inject the whole catalog or every template body.

Catalog `text` uses the search phrase shape; `ids` uses exact IDs. If both are supplied, both must match. Catalog aliases can yield several candidates, never a guessed winner. Paged methods use `limit: 10` by default, maximum 100, and opaque snapshot-bound continuations. A subsequent page repeats the original request with the returned continuation; a changed snapshot is an error. Inspect pagination covers outline/link entries ordered by their original line, without fetching linked bodies.

### 1. Learn the contract: `describe`

```bash
agent-knowledge --output json describe
```

Expected: command/input schema summaries, knowledge kinds and explicit OR/AND/`any` behavior. This succeeds without workspace configuration. The response lists all ten available commands, reports no planned commands, and returns the installed guide plus ten template paths.

Inspect a field before composing an unfamiliar filter:

```bash
agent-knowledge --output json describe --request-file - <<'JSON'
{"schema":"knowledge.v1","field":"technologies"}
JSON
```

Expected: a registered list of technology IDs or `family:<id>`, or `[any]` alone on a guidance document. The response explains that query values such as `[any, postgresql, family:relational-database]` use OR and that families are explicit. Catalog values themselves come from `catalog`, not from this schema-only operation.

### 2. Diagnose the actual harness environment: `doctor`

Run this from the harness that will use knowledge:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json doctor
```

Expected: actual runtime version, executable/interpreter locations, resolved config, workspace ID, and named check results. The configured catalog is parsed/validated; source roots are checked for existence/readability. The default does not scan knowledge bodies. A configured, empty source can be healthy.

| Result area | Healthy default result |
| --- | --- |
| Runtime | Actual package version and paths, not guessed installation locations. |
| Configuration | Selected file resolves to `repo:orders-api`. |
| Catalog | Schema, registered IDs and cross-source consistency are valid. |
| Knowledge source | Configured `commerce-knowledge` root exists and is readable. |
| Signal storage | Configured paths and canonical-root separation are valid. |
| Read readiness | `ready`. |
| Write readiness | `unverified`; no write probe ran. |

Check that the harness selected the intended workspace and explicitly test signal writes:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json doctor --request-file - <<'JSON'
{"mode":"write","expected_workspace_id":"repo:orders-api"}
JSON
```

After validating storage containment, write mode creates and removes one uniquely named temporary probe in the configured signal storage. It reports the probe/cleanup result and `write: ready` only if both succeed. It does not create a signal or modify knowledge. A missing storage directory is reported with setup guidance; this diagnostic does not create a directory tree. Missing optional signal storage is acceptable for read mode, but write mode reports it as not configured and exits 2.

This catches using the wrong valid workspace file:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json doctor --request-file - <<'JSON'
{"expected_workspace_id":"repo:billing-api"}
JSON
```

Expected: exit 2 with `workspace-mismatch`, actual `repo:orders-api` and expected `repo:billing-api`; runtime checks still appear. `expected_workspace_id` is an identity assertion, not an entity filter that must be registered in the selected catalog.

This deliberately checks the missing-configuration case:

```bash
agent-knowledge --output json doctor
```

Expected: exit 2 with `configuration-required`, available runtime details and guidance to provide `--config`. It must not guess another repository's configuration or claim a successful empty source.

If the launcher itself cannot be found, no Python doctor can run. The later APM bootstrap first checks executable availability, using the harness's configured launcher location or a shell availability check such as:

```bash
command -v agent-knowledge
```

If that fails, the bootstrap reports the unavailable launcher and the documented installation/invocation path. A broken interpreter or unavailable import dependency may also fail before doctor starts; report that launch failure rather than fabricating a doctor response. Core installation tests must cover this boundary. An absolute executable path can be configured when the GUI harness has a minimal `PATH`; this is an explicit setup choice, not automatic shell mutation.

No new runtime behavior depends on `launchctl` or organization-specific environment variables. Doctor never dumps the environment/credentials, edits shell startup files, calls `launchctl`, installs packages or repairs configuration. A successful terminal invocation certifies only that invocation. Actual compiled Claude/Codex setup is proven in R6's minimal fresh APM integration, using the same explicit config and installed launcher.

### 3. Obtain workspace context: `context`

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json context
```

Expected: `workspace_id: repo:orders-api`, the three configured applicable scopes, and source/catalog locations resolved from the workspace file. Optional signal-storage configuration is returned separately. This neither enumerates all documents nor proves the knowledge is fresh relative to a remote repository; remote synchronization is outside the core.

### 4. Discover identifiers: `catalog`

The user asks to add a status filter to past orders. The agent does not yet know the feature ID:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json catalog --request-file - <<'YAML'
dimension: entities
text:
  any: [past orders, order history]
limit: 10
YAML
```

Expected candidates include `feature:order-history`, its description and source provenance. The alias `past orders` helps discovery. The agent now has an exact entity ID to reuse.

After inspecting the service/code and learning that it uses PostgreSQL:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json catalog --request-file - <<'JSON'
{"dimension":"technologies","ids":["postgresql"],"limit":10}
JSON
```

Expected: `postgresql`, label `PostgreSQL`, alias `Postgres`, `technology_families: [relational-database]`, and catalog provenance. This supplies vocabulary; it neither expands future queries nor declares PostgreSQL the approved stack.

### 5. Find selective previews: `search`

Discover the user-visible behavior before reading implementation details:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'YAML'
kind: [feature, workflow]
scope: [org:example, group:commerce, repo:orders-api]
text:
  any: [order history, past orders]
limit: 10
YAML
```

Expected in the fixture: the order-history feature and workflow previews. The agent selects the workflow for behavior and sees the entity IDs in metadata. No body is returned.

Find associated system context without guessing its prose:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'YAML'
kind: [system]
scope: [org:example, group:commerce, repo:orders-api]
entities: [feature:order-history]
limit: 10
YAML
```

Expected: the Orders service preview. Its technology metadata points to PostgreSQL; inspecting/reading the selected system page identifies production consumers and directs the agent to verify current code/migrations.

Once the work involves a TypeScript/PostgreSQL query and possibly an index:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'YAML'
kind: [guidance]
scope: [org:example, group:commerce, repo:orders-api]
topics: [testing, performance, data-design, reliability]
languages: [any, typescript]
technologies: [any, postgresql, family:relational-database]
environments: [any, prod]
limit: 10
YAML
```

Expected matching files are `testing.md`, `index-cost.md` and `postgresql-index.md` in `guidance/`. The MySQL-only and React-only rules fail the technology filter. The family rule remains because the agent explicitly requested `family:relational-database`. The general testing rule remains because the agent explicitly requested `any`. The general rule has no feature entity; adding `entities: [feature:order-history]` here would wrongly exclude it. Separate questions permit different filters.

The tool does not decide that every surviving rule matters. It returns those predicates' matching previews for the agent to assess. It does not pad results or return their bodies. The local search does read source bytes internally to validate documents and evaluate text predicates.

For business work, discover registered topics through their labels or aliases:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml catalog --request-file - <<'YAML'
dimension: topics
text:
  any: [prospecting]
YAML
```

The fictional catalog returns `lead-generation`. Use that exact ID to find
the qualification guidance, without imposing an unrelated technology filter:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml search --request-file - <<'YAML'
kind: [guidance, workflow, runbook]
scope: [org:example]
topics: [lead-generation]
YAML
```

Expected: `guidance/lead-qualification.md`. Its language, technology and
environment applicability are explicitly `[any]`. A broad `kind: [guidance]`
search can find both business and engineering guidance; the topic above excludes
the unrelated engineering files. It is a task-selected query, not a mandatory
marketing search for every task. The same catalog and search contract handles both.

For static-site planning, search guidance before committing to the user's proposed provider:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'YAML'
kind: [guidance]
scope: [org:example, group:commerce, repo:orders-api]
topics: [technology-choice, provisioning]
text:
  any: [static site, static hosting]
limit: 10
YAML
```

Expected: `guidance/static-sites.md`, which describes the example organization's portal/Netlify choice. Deliberately omit a technology filter at this decision point: a `cloudflare-pages` filter would hide guidance recommending Netlify. The agent brings the conflict into planning before provisioning resources. The tool does not resolve policy conflicts.

Two distinct negative outcomes:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'JSON'
{"kind":["limitation"],"entities":["feature:order-history"],"limit":10}
JSON
```

Expected: exit 0, `status: ok`, `results: []`, `total_matches: 0`, `returned: 0`, `truncated: false`, `continuation: null`, and no diagnostics. This means no fixture document matches these predicates, not that the feature has no possible limitations.

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json search --request-file - <<'JSON'
{"entities":["feature:order-histroy"]}
JSON
```

Expected: exit 2 and `unknown-identifier` naming `entities` and the misspelled ID. A suggestion may help, but the tool must not silently correct it or report a successful empty search.

Search returns one flat preview per file: `source`, source-relative `path`, absolute `local_path`, authored metadata, `byte_count`, `line_count`, `frontmatter_range`, `body_range`, content `fingerprint`, `link_count`, and match-location fields. No body excerpt is included. A non-text search sets `metadata_only: null`; a text search sets it to true only when no phrase occurrence is in the body. Files with a contributing metadata hit come first, then remaining files, with source/path order inside each group. This is deterministic ordering, not semantic reranking.

Each `matches` entry identifies `field`, `group` (`any`/`all`), zero-based `phrase_index`, inclusive `start_line`/`end_line`, `precision`, and optional enclosing `section`. Metadata uses `precision: field-range`: folded scalars, lists and YAML alias uses point to their authored field, not a guessed word position. Body matches use `precision: line-range`; a phrase can span adjacent physical lines. A section encloses the entire match span, or is null. Matching normalizes Unicode/case and recognized Markdown syntax; it does not apply regex, stemming or inferred facets.

File pages use the request's `limit` (default 10, maximum 100). Each file separately returns at most 20 locations, with `match_count`, `matches_returned`, `matches_truncated` and `match_continuation`. To retrieve more locations, repeat the original request with that token as `continuation`. The response has `page_channel: matches`, contains just that file, and its top-level continuation pages the remaining locations. Keep the original `page_channel: items` continuation if more files are needed. Never combine or reuse tokens with a different query. For example, after a many-match runbook query:

```python
# Harness pseudocode: request() invokes the installed CLI with this JSON request.
query = {"kind": ["runbook"], "text": {"any": ["index"]}, "limit": 10}
page = request("search", query)
selected = page["results"][0]
if selected["match_continuation"]:
    more_locations = request("search", {
        **query, "continuation": selected["match_continuation"]
    })
```

A successful search reports `scan_status: complete` for the explicit local predicates. Every selected source document is validated, even when a facet would exclude it; an invalid file cannot masquerade as absent knowledge. Hidden Markdown files are included, ignore rules do not hide them, and real `.git` directories are excluded. Source-internal symlinks are errors. Lowercase `.md` is the canonical extension; other files are not knowledge documents. Documents are capped at 8 MiB. Search retains lightweight candidate identities and constructs detailed locations only for the returned page. Cursor calls rescan; there is no persistent index. Inventory/config checks detect changes during a scan and fingerprints invalidate stale pages, but do not lock writers, synchronize remotes or make subsequent harness reads atomic.

### 6. Navigate a selected file: `inspect`

After selecting the index procedure from a preview or explicit related link:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json inspect --request-file - <<'JSON'
{"document":{"source":"commerce-knowledge","path":"runbooks/postgresql-index.md"},"limit":20}
JSON
```

Expected preview/navigation values for the committed [synthetic runbook](cli-examples/commerce-knowledge/knowledge/runbooks/postgresql-index.md), mapped to the fictional installation:

| Field | Value |
| --- | --- |
| Source / path | `commerce-knowledge` / `runbooks/postgresql-index.md` |
| Resolved local path | `/work/code/commerce-knowledge/knowledge/runbooks/postgresql-index.md` |
| Bytes / physical lines | 1381 / 41 |
| Frontmatter / body range | 1-11 / 12-41, inclusive |
| Fingerprint | `sha256:e42ea49518e4cb3757909739b03e5497f754c920d66fc0bb263b367df60f12bd` |
| Prerequisites section | 15-20 |
| Adding a status index section | 21-32, including its Verification subsection |
| Recovery section | 33-37 |
| Related Knowledge section | 38-41 |
| Explicit prerequisite link | Line 23, same file, anchor `prerequisites`, resolved |
| Related principle | Line 40, `guidance/index-cost.md`, resolved |
| Related service | Line 41, `systems/orders.md`, resolved |

Inspect returns metadata, outline entries and labelled references, not the procedure body. The agent reads a relevant range using its ordinary tools:

```bash
sed -n '15,32p' /work/code/commerce-knowledge/knowledge/runbooks/postgresql-index.md
```

For this small 41-line fixture, reading the entire file is also reasonable:

```bash
cat /work/code/commerce-knowledge/knowledge/runbooks/postgresql-index.md
```

For a much longer real runbook, use its actual returned ranges and references. Size and outline guide that judgment; no automatic size threshold is required. An agent must read prerequisites/recovery when they matter, not just the matching sentence. A search matching only frontmatter does not claim a body location; the agent can inspect the outline or grep the selected file.

To verify a previously returned file identity before continuing:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json inspect --request-file - <<'JSON'
{"document":{"source":"commerce-knowledge","path":"runbooks/postgresql-index.md"},"expected_fingerprint":"sha256:e42ea49518e4cb3757909739b03e5497f754c920d66fc0bb263b367df60f12bd","limit":20}
JSON
```

If bytes changed, expect a `stale-document` error and refresh the preview. This check cannot make a subsequent external file read atomic. To explore the linked principle, call `inspect` again with `path: guidance/index-cost.md`; its links become available then. Cycles do not trigger recursion. Knowledge links are navigation, not inferred runtime dependencies.

Navigation entries are ordered by physical start line (headings before links on ties). Links have separate `status` and `anchor_status` fields. `resolved` means a regular eligible Markdown file exists in a configured source; `missing`, `unsafe` and `unresolved` retain diagnostic reasons. `external` covers external evidence, including URLs, non-canonical extensions and Git metadata; nothing external is fetched. Same-file anchors are checked against the selected outline (`resolved`/`missing`), while other-file anchors stay `unverified` and links without anchors use `not-present`. A malformed linked document does not prevent inspecting its source: linked bodies are not read or validated until explicitly selected.

The pure scanner supports ATX headings, nested/duplicate heading anchors, fenced/indented code shielding, inline links/images, single-line reference definitions, explicit full/collapsed references, known shortcut references and angle HTTP(S)/mailto links. Unknown explicit references remain unresolved. Standalone HTML comments cannot create headings or links; recognizable raw HTML blocks remain literal. Setext headings and nested list/quote containers are not sections. Literal code remains searchable but its Markdown-like contents do not become navigation. LF, CRLF and CR line positions are preserved. Use ordinary file tools for syntax beyond this documented subset.

### 7. Check authored knowledge and signals: `validate`

Before a knowledge update is published, validate its whole configured source, including registered metadata and links:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json validate --request-file - <<'JSON'
{"sources":["commerce-knowledge"]}
JSON
```

Expected: the ten fixture knowledge documents pass structural validation. Doctor checks setup; this explicitly scans documents. Neither check certifies the claims' truth or the source's remote freshness.

For an authoring iteration on just the existing owner:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json validate --request-file - <<'JSON'
{"documents":[{"source":"commerce-knowledge","path":"runbooks/postgresql-index.md"}]}
JSON
```

Before capturing an observation, validate its Markdown signal input:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json validate --request-file - <<'JSON'
{"signal_files":["index-observation.md"]}
JSON
```

That path resolves beside the consumer configuration, not beside a request file. The [complete signal example](cli-examples/orders-api/index-observation.md) contains `knowledge-signal.v1` frontmatter and its claim in the Markdown body. Validation does not write/move it, publish it, or certify evidence it has not checked. A missing language on a guidance document, an unknown family, or a broken canonical reference is an explicit diagnostic, not successful validation with silently dropped fields.

### 8. Capture one durable observation: `signal record`

The engineer learned a reusable migration-runner constraint. The agent authors `index-observation.md`, as above, rather than sending a raw task transcript:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json signal record --request-file - <<'JSON'
{"file":"index-observation.md"}
JSON
```

The command validates the shared Markdown envelope and signal schema, verifies configured origin and durable checkout identity, then stores a unique file under:

```text
/work/code/commerce-knowledge/ai/signals/projects/orders-api/<timestamp>-<unique-id>.md
```

Expected: captured signal ID, actual stored path and complete-byte fingerprint. The source authoring file is retained. Existing inbox entries are never overwritten; collisions produce a unique safe placement or an explicit error. A linked temporary Git worktree maps to the same durable `orders-api` origin. The example requires the independent consumer Git checkout described in the fixture README; running it from the enclosing scaffold is not a valid origin test.

The returned record is a flat preview with `id`, `created_at`, `kind_hint`, `origin`, optional hint arrays, `evidence`, `local_path`, byte/line counts, frontmatter/body ranges and `fingerprint`. The stored file is byte-for-byte identical to the authored input, including line endings and body. The generated filename uses capture time and a unique ID; authored `id` and `created_at` are preserved. A repeated record creates another distinct file; callers inspect an uncertain outcome before retrying instead of assuming an upsert.

The fixture is a manual observation and omits provider provenance. For a
harness-origin observation, set `origin.harness` and copy the exact hook-provided
handle into `origin.session_id`; the latter is required whenever `harness` is
present. Never invent a handle or use an automation ID in its place.
`origin.automation_id` is independently optional. Before recording, follow the
same-session discovery example below and inspect likely equivalent observations.

`origin.workspace_id` must equal the explicit configuration. Origin scope/source ID sets must match that configuration (order is irrelevant); scopes may be an explicit empty list when the workspace has no assigned scopes. Registered hint validation remains unchanged. For a project signal, `origin.project_path` must match the verified primary checkout's full path relative to `code_root`. Config location determines Git context, independent of process cwd and inherited `GIT_DIR`/worktree settings. Linked producers may be outside `code_root`; their durable primary must be a strict descendant. Missing/ambiguous identity, bare repositories, separate Git directories and submodules produce explicit errors instead of a guessed bucket.

Set `origin.project_path: null` deliberately for a non-project observation; it goes to `ai/signals/shared/`, retaining its workspace/scopes/sources. Capture skips producer-project association in that case, but still uses local Git to verify the scaffold destination. A directory-only scaffold is valid. A scaffold inside a temporary linked worktree is rejected without remapping; configure its durable primary destination. The scaffold directory must exist. Capture may create `ai/signals` and the necessary project/shared parents; it does not create canonical roots, alter the input, synchronize a remote, edit ignore rules or fetch evidence. This scaffold ignores its inbox already; external configured destinations need an ignore rule as part of setup.

Only complete synced bytes are exposed under the final `.md` name, using exclusive temporary creation and no-overwrite hard-link publication. Collisions fail without overwriting; ordinary write failures clean only this invocation's identifiable temporary file. Post-publication verification/sync failure reports `signal-publication-uncertain` and preserves the published path. Such a result is not a confirmed failed write or permission to blindly retry. Guards detect symlinks and replacements, including canonical overlap when roots are absent; they do not lock filesystem writers or prevent later intentional file edits. Inputs containing standalone legacy YAML, empty claims, unregistered hints or signals authored inside canonical roots fail explicitly.

Origin scopes are capture context, not automatic applicability for a future canonical rule. Recording does not search every possible owner, broaden a technology to its family, open a PR or drain another signal. Missing/invalid evidence references can be diagnosed structurally; the CLI does not establish that a human's claim is true.

### 9. Discover pending observations: `signal list`

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml --output json signal list --request-file - <<'JSON'
{"include_shared":false,"limit":10}
JSON
```

Expected after capture: inventory of the configured workspace's pending signals, including ID, origin, advisory hints, evidence references, resolved file path, body line range, byte count and current complete-byte fingerprint. Claim bodies are read through ordinary file tools when selected. With `include_shared: true`, also include the deliberately non-project `shared/` inbox; this is not a canonical scope named `shared`.

An absent inbox is an empty listing, while an unreadable or malformed existing inbox/file is diagnosed. Listing never creates directories, edits signals, marks them compounded, or deletes them. Catalog and origin validation errors remain visible. R7's on-demand compounding skill uses context, catalog, search, inspect and validate to find/update the right owner, then follows the agreed publication/draining process.

Listing selects only direct files in the exact durable project bucket; it does not recurse into another project nested beneath that path. `include_shared: true` adds direct files in the shared bucket. With no Git project association, the default reports `project-origin-required`; explicitly include shared signals to list that origin context.

The response contains `results`, `total_matches`, `returned`, `truncated`, `continuation`, snapshot `fingerprint` and `other_workspaces`. Each result has the same flat preview shape as capture. Entries are ordered by stored path, and pages bind the request, resolved configuration/storage and complete bytes/stat inventory of the selected buckets. Edited/new/deleted signals invalidate an old continuation. No body excerpts are returned.

Shared storage can contain observations from several workspaces. The codec and minimal signal envelope identify their originating workspace first; `other_workspaces` counts entries for other workspace IDs. Their catalog-specific hints and claims are not validated against this workspace's catalog, and they are not returned as its pending signals. Select their actual originating configuration to process them. Selected records receive complete schema, catalog and exact-origin validation. Unreadable/malformed envelopes remain errors; selected metadata diagnostics name both file and field. Unknown legacy `.yaml`/`.yml` files in a selected bucket are diagnosed and retained; unrelated runtime files are not claim entries. Listing never treats signals as canonical truth or a completed disposition.

#### Before recording: inspect candidates from this session

Suppose the hook delivered `claude-session-123` and the current task has two
pending observations: `index-runner-constraint` about transaction-wrapped index
creation and `index-progress-monitoring` about checking rollout progress. Use
the actual delivered handle in this request:

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml signal list \
  --request-file - <<'YAML'
include_shared: true
session_id: "claude-session-123"
limit: 50
YAML
```

Expected for this scenario: two previews with those IDs and the exact
`origin.session_id`, each carrying its actual `local_path`, `body_range` and
fingerprint. No claim body is returned. A different session is excluded, even
if its wording matches. The filter is literal and case-sensitive; continuation
requests must retain the same filter. These two observations illustrate a
session workflow; they are not pre-recorded by the manual fixture above.

If the new observation concerns the migration runner, select
`index-runner-constraint` from the previews. Use its returned path and body
range with ordinary file tools, for example `sed -n '24,34p'` if that preview
reports lines 24-34. Inspect `index-progress-monitoring` too if its metadata
suggests overlap. When the first body already records the same constraint,
record nothing new. When the evidence supports a distinct useful observation,
author it from the installed template and call `signal record` with that file.
When the work revealed no useful gap, no signal is needed.

A scheduled compounder uses the unfiltered initial inventory above, optionally
with `include_shared: true`, so it can process observations from all authoring
sessions. It must not filter that inventory to its own newly started session.

### 10. Coordinate explicit compounding: `compound`

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml compound \
  --request-file - <<'YAML'
action: status
YAML
```

Expected: the activity-log path, recorded events and any unfinished runs. This
read-only action does not select or drain signals. Use `describe` with
`schema: compound` to discover the fields, then follow the installed
[`knowledge-compound` skill](../../packages/knowledge-agent-pack/.apm/skills/knowledge-compound/SKILL.md)
for its `start`, `drain` and `finish` requests. That skill owns the complete
publication and disposition workflow. Drain accepts selected current-workspace
signal snapshots and explicit outcomes; it does not make those decisions or
publish knowledge itself.

### 11. Find references to a document: `inspect` incoming view

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml inspect \
  --request-file - <<'YAML'
document:
  source: commerce-knowledge
  path: product/features/order-history.md
view: incoming
sources: [commerce-knowledge]
limit: 10
YAML
```

This returns authored references, each with a referring file preview, link label,
physical lines and target anchor status. Multiple links from a file count
separately. Omit sources to scan every configured source. A missing old Markdown
path is accepted in this view, so rename/retirement checks can still find dangling
references; ordinary navigation requires an existing file. Scan status, sources,
bytes, elapsed time and diagnostics state the coverage. Unselected sources and
catalog entity documents references are outside incoming Markdown coverage.
Check the catalog separately when moving an owner. Reuse the request and returned
continuation to page; edits invalidate stale snapshots. No bodies or inferred
reciprocal links are returned.

### 12. Export usage for review: `usage export`

```bash
agent-knowledge --config /work/code/orders-api/knowledge-workspace.yaml usage export \
  --request-file - <<'YAML'
since: "2026-09-08T00:00:00Z"
until: "2026-09-14T00:00:00Z"
destination: /work/reviews/commerce-usage-september-8-13
YAML
```

The UTC range includes since and excludes until. Use a fresh destination outside
configured storage. The local export includes this workspace's retained terminal
responses, relevant earlier run context, exact signal archives, available bounded
change patches, catalog descriptors and a checksum manifest. Coverage diagnostics
expose absent session IDs, unavailable versions, expired/missing evidence and
partial records. Originals are preserved; nothing is uploaded.

Receipts are collected by the CLI automatically. Carry `--harness claude
--session-id <exact-hook-handle>` as global arguments before catalog/search/inspect.
During compounding use `--compound-run-id <returned-start-id>` before those commands
and validate; the recorded workspace run supplies consistent provenance defaults.
The hook does not write receipts, and ordinary body reads remain unknown.

## End-to-end agent behavior

For the order-history extension, the harness checks readiness/context, discovers the feature, selects behavior and system previews, then reads those files. Once it knows the change touches PostgreSQL, it can issue independent guidance/procedure searches in parallel. It inspects the index procedure, reads the relevant procedure and prerequisites, and checks current code/migrations before deciding what to implement. It validates behavior against the workflow and records a signal only if the work uncovers a durable knowledge gap.

For static-site planning, the agent begins with the capability and technology-choice topic, reads the selected portal guidance, and resolves the proposed provider conflict before narrowing subsequent implementation queries. Different task stages change the questions the agent chooses; they do not activate a hidden deterministic pass planner.

For on-demand compounding, ask the installed `knowledge-compound` skill to process pending signals for the explicit orders workspace. It reads the advisory activity log, lists/selects signals and loads their originating context. For this fixture, it searches the existing PostgreSQL procedure, uses the adapted runbook template as an authoring reference, and validates the updated owner. The source's optional publication configuration identifies the fictional knowledge repository and `knowledge/` PR branch prefix. The skill reuses the current user's eligible open knowledge PR or creates one, merges current main normally, verifies publication, and drains only confirmed unchanged selected inputs. Tests simulate that remote and PR state; the fictional `example/commerce-knowledge` coordinate is never a real test destination. Other existing engineering skills are not prerequisites for this workflow.

These fixtures are small contract examples, not a benchmark. R5's historical
proof covered the nine commands available at that slice. Later compounding and
provider verification is recorded in the [core plan](organization-neutral-knowledge-core.md)
and [harness proof](../../docs/r8-harness-proof.md). Those checkpoints distinguish
deterministic checks, installed-consumer proof and authenticated model workflows;
no enterprise-scale retrieval-quality or document-consumption claim is made here.
