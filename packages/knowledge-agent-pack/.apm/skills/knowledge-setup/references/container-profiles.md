# Prepare a profile inside an existing container

Use this after [execution-location checks](containers.md#establish-execution-location-first)
when a registry has host-only paths or a designated credential mount cannot
enforce Linux ownership/mode. It supplements [profiles](profiles.md); preserve
the existing selection, environment mappings and checked registration contract.

## Review container-local paths

Inspect the selected registry/profile and workspace using their supported
schemas. Prepare a complete candidate registry for its final container location.
Resolve inherited workspace paths relative to their original workspace file and
overrides relative to the original registry. Translate workspace/config, source
roots/catalogs, runtime, code root, signal/receipt storage and environment file
using actual mounts. Reuse supported overrides. Never mechanically substitute
host prefixes or copy unrelated profile data into the selected environment.

Preserve existing default, unrelated profiles and comments in the candidate.
Use the checked registry digest for optimistic concurrency; it covers non-secret
registry bytes, never credential values. Keep the candidate outside Git when it
contains machine-local paths. The helper validates schema and selected effective
configuration; the agent must still establish that paths represent the intended
knowledge and shared state. Do not create a new store to avoid a missing mount,
or move only locks away from their writers.

## Reuse or explicitly project the private file

Reuse a valid local private environment file unchanged. For a designated source
mount with unsuitable permissions, prepare a user-owned Linux-backed private
directory (`0700`) outside images, Git, canonical knowledge and shared consumer
source. The projected target is `<private-directory>/<profile>.env` with mode
`0600`. The candidate's selected `environment.file` must name it.
The settings parent and private-directory parent must already be real accessible
directories. The helper creates only the private-directory leaf; it never
recursively creates or changes ownership of ancestors.

Run installed runtime Python with the matching installed skill script:

```sh
/opt/agent-knowledge-venv/bin/python /opt/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/prepare_container_profile.py \
  --operation prepare \
  --settings /home/developer/.config/agent-knowledge/config.yaml \
  --profile work --candidate /tmp/reviewed-container-profiles.yaml \
  --expected-sha256 missing \
  --private-directory /home/developer/.local/share/agent-knowledge/private \
  --source-env-file /mnt/profile-input/work.env
```

`missing` means creation only. For an existing registry supply its just-inspected
SHA256 using the normal checked-profile procedure. Never calculate, print or
persist a credential digest. Omit source/private-directory for ordinary local
file reuse. Derive paths from the existing environment; do not ask developers to
assemble flags or repeat accepted profile choices.

The source must be explicitly designated, regular and safely reachable. Copy
atomically and publish the registry only after preparation. This import route
accommodates a mount that cannot express Unix ownership; it does not establish
the original mount's security or weaken runtime activation guards. Report that
source-side limitation. No ambient profile/token lookup, shell sourcing or value
logging is allowed.

Blank entries stay blank and activation stays pending. Literal parsing remains
the installed parser's contract; shell expressions are never evaluated. Never
insert fake values into the profile. Complete independent knowledge and reminder
setup, retaining environment diagnostics and withholding credential launch.

## Refresh, failure and removal

For an existing projection, use `--operation refresh` with the same explicit
source/private-directory and reviewed candidate, plus the current registry
digest. It checks setup-owned provenance and refreshes under guarded serialization.
Refresh retains the same selected declaration and recorded source. Use `prepare`
for reviewed mapping or explicitly designated source-path changes; it verifies
existing projection ownership before replacement.
Use this as a separate launcher pre-step that must succeed before
`launch_container.py`. A failed refresh must not continue with an old secret
copy; repair and repeat. Do not use `|| true` around it.

After a mapping/file declaration changes, repeat affected profile preparation,
binding and repository checks and start a new harness session. Value rotation
in the same declared source needs guarded refresh and a new credentialed launch,
not an automatic APM reinstall. Existing processes retain their loaded values.

`--operation remove` takes a reviewed candidate removing/rerouting the selected
environment (or removing a non-default selected profile). It removes only verified
setup-owned private artifacts. Host originals, unrelated entries, knowledge,
signal/activity/receipt state and provider sessions remain untouched. Changed or
unsafe ownership requires inspection, not permission to unlink.
Removal validates registry declarations and owned file identities without opening
the knowledge workspace, so an unavailable mount does not prevent revocation.
It does not certify a replacement environment or permit a new launch; run setup
and preflight for any replacement route. Interrupted publication's two journaled
names can be recovered; unknown hard links remain an ownership error.

After preparation, continue the owned runtime/APM/bind sequence and save its new
launch report. Run the [actual-launcher acceptance](containers.md#one-acceptance-sequence-through-that-launcher).
Profile preparation alone certifies neither native credential activation nor
hook trust, sandbox access or compounding/publication readiness.
