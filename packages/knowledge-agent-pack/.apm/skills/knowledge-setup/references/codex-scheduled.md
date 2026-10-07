# Codex local compounding

Inspect the actual Codex surface. A verified Codex desktop Scheduled task can
provide durable local recurrence. Codex CLI alone does not inherit that app
capability: use the [prompt fallback](local-compounding.md) when no durable
native local schedule is available. Keep existing working local tasks; never
enable an independent fallback for the same signal store alongside one.

For desktop scheduling, search for the exact marker first:

```text
agent-knowledge-compound:<workspace_id>
```

Reuse its task, configure cadence/timezone through the native editor and record
`local-schedule` using the shared trigger procedure. Multiple matching owners
need resolution. Use a short task prompt:

```text
Run the installed knowledge-compound skill using
/work/knowledge/.agent-knowledge-venv/bin/agent-knowledge with
--settings /work/local/profiles.yaml --profile work on every configured call.
Process pending signals using its ownership, publication and guarded-drain
rules. Report meaningful results and retained inputs. Do not merge PRs or
force-push. Preserve exact provider session and automation handles when exposed.
```

Add verified participating-consumer routes from [publication setup](publication.md).
Direct setup can replace the profile selector with an absolute `--config`.
Never depend on the global default. Trigger one supported run-now execution
before claiming schedule readiness, unless that verification is explicitly
paused; report missing proof truthfully. Keep native pause/remove controls in
the setup report. Missing authentication is a readiness problem, not evidence
that changing trigger mode will fix it.

For CLI fallback, bind the installed prompt hook, select `prompt`, and verify
an ordinary `UserPromptSubmit` turn delegates the installed compound skill. The
execution interface is Codex's exposed native subagent tools. Start the worker
task with `[agent-knowledge-compound-worker]` as the shared reference requires;
never use shell-started `codex exec` or another model CLI as the worker. Missing
native subagent tools leave prompt-triggered compounding pending. The
main agent continues user work. The worker atomically rechecks eligibility;
repeat prompts and redundant workers cannot authorize competing compounding.
Report the rolling interval and that no prompts means no run. Pause/remove use
the [shared trigger procedure](local-compounding.md#pause-remove-and-report).

Credentials belong to the chosen local process or the Scheduled task's verified
native credential surface. Codex desktop has no generic profile env-file field
to infer. The setup-generated CLI launcher activates the selected profile for
a new CLI process; a knowledge selector alone does not. Never put values in a
prompt or copy them into hook configuration. Unrelated unfinished mappings stay
visible without blocking local knowledge readiness.
