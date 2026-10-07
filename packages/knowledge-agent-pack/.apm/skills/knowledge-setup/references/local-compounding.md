# Select one local compounding trigger

Setup owns trigger selection; `knowledge-compound` owns all work after a run
starts. Choose for the actual harness surface, not just its provider name.
Prefer a verified durable native local schedule. Otherwise use the installed
prompt fallback in Codex CLI, Claude Code or Copilot CLI. Session-only `/loop`,
`/every` and `/after` timers do not establish durable daily scheduling.
Preserve explicit `disabled` or `manual` choices and an existing working local
schedule. Do not create a daemon, cron/systemd job, remote workflow or hidden
background process. Existing external jobs remain user-owned; inspect possible
conflicts without deleting or silently adopting them.

## Readiness and ownership

Before activating either mode, verify configured `context`, write-mode
`doctor`, installed compound-skill discovery and the consumer's final native
checks. The installed compound skill and its references must match the APM
package that owns the running setup helper. Runtime version equality or a
present `SKILL.md` alone does not prove that resource parity. Use the consumer's
owned APM workflow to refresh incompatible resources; never patch an installed
copy or substitute a private worker skill. Check read, signal-write and receipt readiness separately from external
credentials. Unrelated blank mappings do not block local work, but required
publication access must be available before activating a run known to need it.
The profile selector never activates credentials or changes the parent harness
environment. Preserve pending access visibly; do not borrow an ambient account.

Inspect `compound` with `action: status`, effective `setup.compounding` and any
existing matching local task. Compare physical storage and effective routing
across profile aliases and providers. One shared signal store has one trigger
mode and logical owner; different provider names or container paths do not
create independent owners. Reuse the marker
`agent-knowledge-compound:<workspace_id>` for a new owner, or preserve the
existing exact owner. Incompatible routes or multiple existing tasks require a
specific resolution before activating another trigger.

The workspace or reviewed profile override uses this existing setup extension:

```yaml
setup:
  compounding:
    mode: prompt
    owner: agent-knowledge-compound:workspace:example
    interval_seconds: 86400
    retry_seconds: 3600
```

Preserve the rest of `setup`. Supported modes are `prompt`, `local-schedule`,
`manual` and `disabled`. Absent configuration stays quiet. `prompt` uses a
rolling interval, not a calendar day or timezone boundary; `local-schedule`
uses its native cadence/timezone. Keep equivalent profile aliases consistent.
Writing configuration and binding hooks do not activate a new trigger. The
helper never implicitly calls `configure-trigger`. With compatible installed
compound resources and write readiness, an absent stored agreement is reported
as `pending` with reason `activation-required` and an exact activation command
plus request. The hook can already be bound: until the agreement is recorded,
its due check stays quiet. A matching existing agreement is preserved; an
idempotent rebind does not pause or recreate it.

Run the consumer's final install/compile/bind consistency checks first. Then
execute the returned activation command and request as part of authorized setup;
do not add another approval question for this routine step. Its request is:

```yaml
action: configure-trigger
```

Use the exact reported launcher and selector, rather than reconstructing them.
If the report has no activation command, resolve its reported readiness or
resource issue, rebind and rerun affected consumer checks before activation.
This records the store's selected trigger in its existing
`ai/signals/compound-activity.jsonl`. Do not edit that log or add another
last-run file. Repeat configuration is idempotent. A conflicting stored trigger
is not overwritten implicitly: inspect its current owner, arrange the intended
pause/removal, and pass `expected_trigger` containing the exact prior mapping returned by
status to explicitly replace the agreement. Replacement rejects an active run
and a changed prior mapping. Reconcile aliases before retrying; a failed compare
is not a reason to force the write.

For `local-schedule`, reuse/update the verified local task and record its exact
provider handle. Keep fallback quiet. When moving from a schedule to `prompt`,
pause/remove the former schedule through its supported controls before enabling
fallback. When moving to a schedule, suppress fallback first, then register or
resume the one native task. A pause request must not silently activate another
mode. If native scheduling is unavailable, the prompt fallback is the supported
choice; unavailable authentication still needs its own remediation.

## Prompt fallback behavior and verification

Bind through the normal setup helper and repository-owned APM workflow. No
second private hook or scheduler is needed. The existing package-owned prompt
hook asks the installed runtime for advisory `action: due`. It performs bounded
metadata checks only; it does not read signal bodies, call a model, access the
network or wait for a busy lifecycle lock. Compounding readiness, missing/stale
resources and trigger conflicts are reported separately: when the base runtime
and package are usable, setup still binds discovery/reflection. It omits the
conditional binding when compounding prerequisites are unsafe, rather than
turning optional compounding into a prerequisite for ordinary reminders.
Corrupt or ambiguous coordination
state is not permission to work. A truncated inbox probe is inconclusive, never
proof of an empty inbox. Discovery/reflection survives due-check failure.

When due, the provider delivers a concise instruction to delegate a worker that
loads the installed compound skill with the same explicit selector and runtime.
For prompt-triggered compounding, native subagents are the execution interface;
the prompt hook is the scheduling fallback. Delegate and reuse workers only
through the active harness's native subagent tools. Never shell-spawn
`codex exec`, `claude -p`, `copilot -p` or another model CLI as a worker. Shell
tools may run the knowledge CLI and native repository checks. If native
subagent tools are unavailable, report that prerequisite and leave this mode
pending without substituting a model subprocess.

Start the native worker's task with `[agent-knowledge-compound-worker]` exactly.
The marker tells inherited prompt hooks to preserve reflection while omitting
another delegation reminder. It does not authorize compounding, acquire a lock
or replace the worker's atomic start check. Pass the original parent handle
separately; the worker's own hook session is not its parent's identity.
The [Copilot binding](copilot-scheduled.md) also reasserts the selected runtime,
selector and installed skill in a marked child and exposes its native worker
identity. Missing or conflicting binding/handoff remains a visible prerequisite,
without falling back to a default or another profile. This context does not
grant authorization or run ownership; the compound skill owns its use.

Prompt fallback has no native automation handle: its logical trigger owner is
not an `automation_id`. Preserve exact worker/session handles only when the
provider exposes them, following the compound skill's parent/worker handoff.
If the native worker handle arrives later, associate it with the exact recorded
run using `record-worker`, even after finish. This metadata update does not
start another run or advance the next due time.
The worker must recheck with `automatic: true` at start. Concurrent reminders
may create redundant workers; only an eligible winner may modify owners,
publish or drain. The parent continues its normal task. No qualifying prompt
means no run, and missed clock times are not backfilled.

Verify one ordinary prompt reaches the fallback, passes the selected route to a
real worker and records its terminal result. Then verify a later prompt remains
quiet. Separate installed fixture proof from actual harness execution; missing
provider access leaves live proof pending. Repeating an advisory due check does
not finish a run. An empty inbox does not delay signals arriving later. Failed
attempts use the retry interval; fully evaluated completed/deferred runs use the
main interval, even when a specific signal must remain pending. A failed retry
does not shorten an earlier completion interval: the next attempt waits for
both applicable deadlines. A later completed/deferred run supersedes earlier
failure attempts. Active runs
never expire by age. See the installed compound skill for truthful recovery and
exact worker/session provenance.

## Pause, remove and report

To pause automatic work while preserving manual compounding, set `mode: manual`
and reconcile the stored trigger through `configure-trigger`; also pause the
native local task if one owns the store. `disabled` keeps the automatic path
quiet as an explicit disabled choice. Preserve activity history and signals.
To remove native recurrence, use the provider's remove control. To remove the
package, follow the consumer's APM uninstall procedure, preserving unrelated
hooks and skills. Do not delete shared state as part of disabling or uninstall.
Reinstallation must rebind and verify readiness before resuming the selected
mode; it must not create a second owner.

Report selected mode/owner, shared-store path, cadence or rolling interval,
last observed readiness, exact selector, and the concrete pause/remove action.
Include any pending activation command, resource mismatch, trigger conflict or
write-readiness diagnostic separately from the base hook result. A helper
`status: ok` or model-visible reminder is not proof of trigger activation or
actual subagent execution.
Record verified consumer publication routes once in the native task prompt or
the consumer's existing authored setup context for worker handoff; do not add
unsupported routing keys to YAML. Keep the hook generic and publication under
the installed compound skill's ownership/review/drain rules. Local execution
may create reviewed GitHub PRs; it never grants automatic merge permission.
