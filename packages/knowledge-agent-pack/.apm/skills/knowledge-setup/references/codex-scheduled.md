# Codex Scheduled

Use the Codex Scheduled task surface for recurring compounding. Create or
update one visible task whose name or metadata contains:

~~~text
agent-knowledge-compound:<workspace_id>
~~~

Example task prompt:

~~~text
Run the installed knowledge-compound skill using
/work/knowledge/.agent-knowledge-venv/bin/agent-knowledge with
--settings /work/local/profiles.yaml --profile work on every configured call. Process pending signals for this
workspace, follow its publication and drain policy, and report the run,
dispositions and retained/drained inputs. Do not merge PRs or force-push.
~~~

Set the requested cadence and timezone in the native task editor. If a task
with the marker already exists, update it instead of creating another one.
Multiple matching tasks are an ownership conflict that needs developer input.
The task's native pause and remove controls must remain visible.

When the task runs, pass the harness name and the provider's opaque session or
automation handle to the skill when available. The signal retains those values
as provenance; they are not credentials and do not change canonical
applicability. A run with no resumable originating session still proceeds from
the self-contained signal.

Run once immediately from the task's run-now control. Confirm the installed
launcher and explicit doctor command are reached and inspect the activity
record. If Scheduled is unavailable or authentication is missing, stop and
show the Codex setup remediation. Do not replace it with a daemon, cron,
launchctl change or shell-startup edit.

Pin the absolute launcher, registry and explicit profile as shown above;
never depend on the global default. Direct setup can substitute an absolute
`--config` selector. Follow [profile setup](profiles.md) for alias/store ownership
and conflict checks before creating or updating a task.

For operations that require external credentials, pin the corresponding
profile's credentials in the Scheduled task's supported native environment or
service store. Unrelated unfinished mappings do not block local compounding;
required publication authentication does. Codex has
no generic profile env-file field to infer here. Never put values in the prompt;
the knowledge selector does not switch credentials inside a running task.
