# Claude Code local compounding

Inspect the installed Claude Code version and actual local task surface. A
session-only `/loop` or `/every` is an attended convenience, not durable daily
scheduling. Unless a verified durable native local schedule is available, use
[the prompt fallback](local-compounding.md). Preserve an existing working local
schedule and its single shared-store owner; do not activate both modes.

Bind the package-owned `UserPromptSubmit` hook through setup, configure mode
`prompt`, and verify an ordinary prompt delegates a worker loading the installed
`knowledge-compound` skill. Hand off the exact launcher, profile and registry
(or explicit config), originating consumer and available provider/session/worker
handles. The worker rechecks eligibility atomically before edits, publication or
drain; duplicate workers exit. The main task can continue. No qualifying prompt
means no run; the rolling interval is not a calendar daily guarantee.

Native subagent tools are the execution interface. Begin the worker's task with
`[agent-knowledge-compound-worker]` as the shared reference requires. Never use
shell-started `claude -p` or another model CLI as the worker. Missing native
subagent tools leave prompt-triggered compounding pending.

If the actual local installation offers a durable native task, inspect and
reuse the exact `agent-knowledge-compound:<workspace_id>` marker, configure
`local-schedule` through the shared procedure and keep its pause/remove controls
visible. Pin the installed skill, absolute launcher and selector in the task;
include the verified consumer publication routes. Verify its run-now behavior
before claiming readiness, subject to any explicit verification pause. Do not
substitute a daemon, cron/systemd job or shell-startup mutation.

The session must activate the intended credential profile through the consumer's
bound `SessionStart` hook or an established local provider credential surface.
The profile in a reminder/task selects knowledge only. One consumer hook binds
one profile for new local Claude sessions; use separate consumer configurations
and local sessions for simultaneous different credential profiles. Unrelated
unfinished mappings do not block local knowledge work; missing credentials
required for publication remain pending. Never copy values into a task prompt.

Use the [shared trigger procedure](local-compounding.md#pause-remove-and-report)
for pause, removal, interval, retry and readiness reporting. A stored worker
handle is provenance and possible reuse information, not a promise that Claude
can resume that worker indefinitely.
