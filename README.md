# Agent Knowledge Scaffold

An organization-neutral repository for shared APM skills/packages and the
knowledge agents need for business and engineering work. Organizational knowledge
belongs in explicitly configured sources; this scaffold contains no organizational corpus.

To adopt it, clone this repository into a durable directory and run the bundled
`knowledge-setup` skill. That checkout becomes your knowledge instance, with
`origin` pointing to your own private repository and `scaffold` pointing upstream
for updates. Setup helps establish both; a second scaffold checkout is unnecessary.
See [first-time setup](docs/fresh-consumer.md#create-your-knowledge-instance).

The installed `agent-knowledge` launcher provides `describe`, `doctor`,
`context`, `catalog`, `search`, `inspect`, `validate`, `signal record`,
`signal list`, `compound`, `usage export` and `profiles list`. The neutral APM package supplies setup and
compounding skills plus discovery/reflection hooks. Current follow-up work is
tracked slice by slice in the final-pass plan below; the master plan retains
the core implementation history and its proof boundaries.

- [Named-profile plan and proof](ai/plans/knowledge-profiles.md)
- [Completed final-pass plan: B1-B5](ai/plans/knowledge-final-pass.md)
- [Master core plan and implementation history](ai/plans/organization-neutral-knowledge-core.md)
- [Planned CLI contracts and realistic examples](ai/plans/knowledge-cli-examples.md)
- [Fictional design fixtures](ai/plans/cli-examples/README.md)
- [Fresh APM consumer setup](docs/fresh-consumer.md)
- [Updating knowledge instances from the scaffold](docs/scaffold-upgrades.md)
- [Harness support and limitations](docs/harness-support.md)
- [R8 harness proof](docs/r8-harness-proof.md)
- [Minimal knowledge-agent-pack](packages/knowledge-agent-pack/README.md)

For personal and work sessions, run `knowledge-setup` to register a profile
label in `~/.config/agent-knowledge/config.yaml`. A profile can name an external
private env file and map its variable names to validated tool-facing names
without storing values in YAML. Configure the label, env-file path and mappings
once, then follow the exact start action reported by setup. Setup owns the
provider differences and reports app limitations only when they apply.
Blank credential entries can remain pending while valid knowledge/runtime and
reminder-hook setup completes; doctor retains its environment diagnostics and
credential activation is withheld until you fill the private file and rerun setup.

For an existing repository with owned APM generation and skill checks,
`knowledge-setup` supports runtime-only `--apm-mode prepare`, repository-owned
installation/compilation, then `--apm-mode bind` and repository checks. Default
`managed` mode retains the complete helper-owned flow. See
[existing-repository integration](packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/existing-repository.md).

Use `agent-knowledge profiles list`, then
`agent-knowledge --profile personal context` or
`agent-knowledge --profile personal doctor`. Add
`--settings /path/to/config.yaml` when using another registry. To change credential profiles, ask or run
`knowledge-setup` for the target profile and then start a new harness session
using its reported action. Passing another `--profile` changes knowledge
selection only, and starting a new Claude session alone does not rebind the
configured credential profile. Direct `--config` is a separate workspace-only
alternative and does not activate a profile environment. The
[installed guide](docs/agent-contract.md#select-a-knowledge-profile-for-this-session)
explains defaults, per-session selection and overrides.

## Develop the core

Use Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). The runtime uses
PyYAML for the shared strict format codec. Dependencies and development tools
are pinned in `uv.lock`; filesystem access currently uses POSIX primitives.

```bash
uv sync --locked
uv run pytest -q tests/unit/domain
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests
uv run mypy
uv build --out-dir .cache/dist
```

## Use the CLI

The following commands run against the committed fictional fixtures. No
organizational setup or knowledge is assumed, and read operations do not create
an inbox:

```bash
uv run agent-knowledge describe
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml doctor
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml context
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml catalog --request-file - <<'YAML'
dimension: technologies
ids: [postgresql]
YAML
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml search --request-file - <<'YAML'
kind: [feature, workflow]
text:
  any: [order history, past orders]
YAML
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml inspect --request-file - <<'JSON'
{"document":{"source":"commerce-knowledge","path":"runbooks/postgresql-index.md"},"limit":20}
JSON
uv run agent-knowledge --config ai/plans/cli-examples/orders-api/knowledge-workspace.yaml validate --request-file - <<'JSON'
{"sources":["commerce-knowledge"]}
JSON
```

For use outside this checkout, install the built wheel into a dedicated Python
environment and invoke its `bin/agent-knowledge` launcher. Use `--profile` (and
optional `--settings`) for a registered profile, or supply `--config` for a
direct workspace with no profile environment. Catalog/source paths resolve from
the selected workspace config's directory; request-file paths resolve from the
current directory. Explicit config/request aliases resolve before guarded
access. Source-relative document paths cannot traverse symlinks. No
shell-variable or `~` expansion occurs inside configuration values.

Global `--profile`, `--settings`, `--config` and `--output json|text` options
precede the command.
`--request-file -` explicitly reads stdin; omitting it never waits for input.
JSON is the default output. Exit 0 means success, including an empty catalog
result; exit 2 means invalid input/configuration/content; exit 3 means runtime
I/O failure or interruption. Catalog results page in ID order with truthful
totals and an opaque cursor bound to the request and config/catalog snapshot.

`search` validates every Markdown document in the selected sources and applies
only the explicit filters and text predicates. It scans local files without a
persistent index, returning metadata, fingerprints, physical line ranges and up
to 20 match locations per file. It never returns body excerpts. Metadata matches
point to the authored YAML field range; body matches point to contributing lines
and their enclosing section when available. Full details are built only for the
returned page. Use a result's `match_continuation` in the same search request's
`continuation` field for further locations; the top-level continuation pages files.
Both cursor types are bound to the request and scanned source snapshot.

`inspect` returns one selected file's preview and pageable headings/links. The
agent then uses ordinary file tools to read the whole file or a chosen line range.
Linked bodies are never fetched automatically. A resolved file link means the
file exists, not that its content is valid; other-file anchors remain unverified
until that file is inspected. External, missing, unsafe and unresolved links
remain visible. The scanner supports ATX headings, fences and common Markdown
links; it is not a complete CommonMark or HTML renderer. Full syntax and paging
limits are documented in the CLI examples.

`doctor` reports this invocation's runtime, explicit config, catalog and source
access, with separate read, signal-write and receipt-storage readiness. It does
not scan knowledge bodies. Optional `mode: write` creates and removes one unique
probe in each **existing** validated signal and usage directory. It never creates directory trees or repairs setup;
failed cleanup is reported explicitly. A terminal invocation does not prove a
compiled harness sees the same executable/config. Use the fresh-consumer proof
for that integration.

Use `describe --request-file -` with
`{"schema":"knowledge.v1","field":"technologies"}` to inspect a field.
`describe` reports the installed guide and ten authoring templates. All ten
available methods have fuller examples in the
[CLI contract](ai/plans/knowledge-cli-examples.md).

`signal record` captures one authored `.md` observation with
`knowledge-signal.v1` frontmatter. Its `file` request path resolves from the
explicit workspace config, and the input stays in place. The command validates
registered hints, evidence structure and origin, then writes the exact bytes to
a unique file in the configured scaffold's `ai/signals/` inbox. It creates only
needed inbox directories and never overwrites a completed signal. Repeated
recording creates separate files; it is not an idempotent upsert.

Project origins come from the config's Git checkout, with linked producer
worktrees mapped to their durable primary checkout relative to `code_root`.
An explicit `origin.project_path: null` captures a non-project signal in
`shared/`. The scaffold destination must exist and be durable: a temporary linked
worktree is rejected, while a directory-only scaffold is supported. Git is used
locally for identity checks; capture does not call GitHub. Separate Git-directory,
bare and submodule layouts are not supported for project association.

`signal list` returns metadata, complete-byte fingerprints and body line ranges
for the configured workspace; ordinary file tools read the selected claims.
It pages the exact project bucket, optionally adding `shared/` with
`include_shared: true`. A configuration without a Git project must explicitly
request shared signals. It never creates an inbox or removes entries. Invalid
selected entries identify the file and field; other workspace entries are
counted without validating their hints against the wrong catalog.

Use the [signal CLI examples](ai/plans/knowledge-cli-examples.md) with a real
originating checkout and explicit durable storage. The fixture directory inside
this repository is not itself that independent checkout. This scaffold already
ignores `ai/signals/`; when configuring another destination, set its ignore rule
at setup. Capture does not edit ignore files or enforce an organization's Git
policy. A failed or uncertain publication retains the authoring input; inspect
the reported stored path before retrying. Neither command compounds, publishes
a PR or drains signals.

Root checks cover the new `src/` and `tests/` trees. Domain unit tests use
in-memory inputs; the separate architecture guard inspects source imports.
Unit and integration tests mirror the implementation's responsibility folders;
integration tests cover operations that need temporary files, configuration or Git.
APM package checks remain separate. Repository maintainers can run the neutral
package and fresh-consumer proof with `tests/e2e/fresh-consumer-smoke`; new
consumers should use the installed CLI's `doctor` command instead.

## Python contract

`domain` accepts already-decoded mappings and returns immutable typed values.
It performs no file, environment, network, Git, clock or receipt operations.
Use `parse_catalogs`, `parse_knowledge`, `parse_query` and `parse_signal` at
untrusted input boundaries. Direct model constructors accept trusted, validated
internal values. A `ValidationError` exposes a stable `code`, input `path` and
`message`; invalid input is not a successful search with no matches.

This complete in-memory example selects a general testing rule while explicitly
including TypeScript applicability:

```python
from agent_knowledge.domain.catalog import parse_catalogs
from agent_knowledge.domain.matching import prepare_query
from agent_knowledge.domain.models import KnowledgeDocument
from agent_knowledge.domain.schema import parse_knowledge, parse_query

catalog = parse_catalogs({
    "team-knowledge": {
        "schema_version": "knowledge-catalog.v1",
        "scopes": {"org:example": {"label": "Example organization"}},
        "entities": {},
        "topics": {"testing": {"label": "Testing"}},
        "languages": {"typescript": {"label": "TypeScript"}},
        "technologies": {},
        "technology_families": {},
        "environments": {},
    },
})
metadata = parse_knowledge({
    "schema_version": "knowledge.v1",
    "kind": "guidance",
    "title": "Test observable behavior",
    "description": "Use when changing behavior or designing regression tests.",
    "scope": ["org:example"],
    "topics": ["testing"],
    "languages": ["any"],
    "technologies": ["any"],
    "environments": ["any"],
}, catalog)
query = parse_query({
    "kind": ["guidance"],
    "scope": ["org:example"],
    "topics": ["testing"],
    "languages": ["any", "typescript"],
}, catalog)
prepared = prepare_query(query, catalog)
assert prepared.matches(KnowledgeDocument("team-knowledge", metadata))
```

Prepare each query once and reuse it across candidate documents. Same-field
values use OR; different fields use AND. Missing metadata does not equal `any`.
Callers explicitly include applicable scopes, general values and
`family:<identifier>` technology values. Registered scope `parents` and the
explicit `catalog.scope_ancestors()` helper describe hierarchy without changing
search filters or assigning precedence.

Text predicates match normalized literal token sequences with direct catalog
label/alias alternatives. They do not infer filters or plan searches. The caller
supplies body text when available. R2's `parse_document` preserves exact body
text and physical frontmatter/body ranges; heading/link navigation belongs to
R3. The matcher does not order or page
results, even though query validation already accepts pagination fields.

## APM packages and repository layout

APM distribution is a permanent part of this repository. The minimal neutral
`packages/knowledge-agent-pack` installs the discovery instruction used by a
fresh consumer, along with setup and compounding skills; the Python package
owns the CLI guide and templates. This is the only distributed APM package.
Broader skill ports will include their templates, references and scripts in
separately reviewed work.

```text
src/agent_knowledge/
  __init__.py
  py.typed
  domain/                       # Pure models, validation, catalogs and matching
  application/                  # Coordinate explicit operations
    discovery.py                # Workspace context and catalog discovery
    retrieval.py                # Search and inspect
    signals.py                  # Signal capture and listing
    doctor.py                   # Readiness checks and optional write probe
    pagination.py               # Request/snapshot-bound cursors
    diagnostics.py              # Shared operation diagnostics
  entrypoints/
    cli/
      main.py                   # Arguments, dispatch, rendering and exit codes
      contracts.py              # CLI schema descriptions
  infrastructure/               # Markdown/YAML, configuration, files and Git
tests/
  unit/
    domain/                     # Fast semantic cases over in-memory values
    infrastructure/             # In-memory format codec tests
    entrypoints/cli/            # CLI schema-description tests
  integration/
    application/                # Discovery, retrieval, signals and doctor
    infrastructure/             # Configuration, corpus, links and signal storage
    entrypoints/cli/            # Command behavior
  test_domain_boundary.py       # Cross-cutting architecture/import guard
pyproject.toml                   # Python package and quality gates
uv.lock                          # Pinned development environment
apm.yml                          # Existing APM composition manifest
.apm/                            # Repository-local APM primitives
packages/                        # Permanent distributable APM packages
ai/plans/                        # Tracked contracts and fictional fixtures
docs/                            # Current setup, contract and verification guides
```

`domain` decides whether a document matches. `application` coordinates loading
configuration and candidates, applying the domain rules, and assembling results.
`entrypoints/cli` translates commands into those operations and renders their
outcomes; `infrastructure` contains the concrete file and Git adapters. The
application's doctor still owns its runtime and write-probe I/O directly; this
folder refactor does not extract those probes into a new abstraction. These are
ordinary functions and modules, with no service-class or dependency-injection
framework requirement. CLI commands and search semantics are unchanged.

Knowledge and signals use Markdown with YAML frontmatter; catalogs and workspace
configuration use YAML. The shared strict codec accepts UTF-8, requires `---`
as the first line and closing frontmatter delimiter, and preserves body bytes
through decoding/encoding and physical line ranges (including CRLF). It rejects
duplicate/nonstring/merge keys, unknown tags, alias cycles and malformed inputs.
Only true/false resolve as booleans; timestamps and yes/no/on/off remain strings.
Numeric scalars use decimal, `0o`/`0x` integers and finite decimal floats.

Limits are 1 MiB for config/catalog/request files and 8 MiB for Markdown
documents, with at most 64 YAML collection levels and 20,000 parsed/expanded
nodes. Valid empty source directories and catalogs work. Canonical sources
remain configurable and empty until a consumer adds their own knowledge.

R7 also ships the neutral knowledge-setup and knowledge-compound APM skills.
The setup skill inspects the business context and existing configuration, asks
only about missing or conflicting facts, and proposes a small catalog for
confirmation. Users confirm scopes/topics in business language and the config
location; setup generates the IDs. It derives or scaffolds the workspace ID,
source/catalog paths, producer root, `ai/signals` inbox and
`<scaffold>/.agent-knowledge-venv`, compiles all three supported APM targets in managed mode,
ensures the signal inbox and runtime are ignored, and uses a daily local-time
cadence. Fresh setup defaults to GitHub PR publication: it proposes the canonical
knowledge checkout's verified remote and default branch, uses prefix `knowledge/`,
and writes explicit source settings. Existing choices and an explicit local-only
opt-out are preserved; missing destination/access is reported as pending. Raw
configurations without a publication block still disable publication. Missing or unauthenticated
providers are reported individually rather than prompting for a subset.
The compounding skill processes signals with validated dispositions and guarded
draining; scheduling remains a harness responsibility.
