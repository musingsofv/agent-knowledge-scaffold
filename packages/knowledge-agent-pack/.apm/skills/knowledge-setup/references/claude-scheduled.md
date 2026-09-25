# Claude Code recurring task

Use the Claude Code native recurring-task command exposed by the installed
version. On versions that support loop syntax, a daily task can be created
with:

~~~text
/loop 1d Run the installed knowledge-compound skill using /work/knowledge/.agent-knowledge-venv/bin/agent-knowledge with --settings /work/local/profiles.yaml --profile work on every configured call. Process pending signals, follow its publication and drain policy, and report retained/drained inputs. Do not merge PRs or force-push. Marker: agent-knowledge-compound:workspace:example
~~~

Some installations expose the same feature as /every; use the provider syntax
shown by its own help. Keep the marker exact, set the timezone in the native
task configuration and leave the pause/remove controls visible.

Before creating a task, list existing recurring tasks and update the one with
the marker. Multiple matches require a developer decision. A task must invoke
the installed knowledge-compound skill with the absolute launcher and pinned
registry/profile selector (or direct configuration path). It must not compile
APM on every run or depend on a shell-startup variable.

Trigger one immediate run and confirm that configured doctor and the activity
log are reached. If the installed Claude Code version lacks recurring tasks or
authentication, stop and report its remediation. Do not substitute a daemon,
cron loop, launchctl mutation or hidden background process.

Pin the absolute launcher, registry and explicit profile as shown above;
never depend on the global default. Direct setup can substitute an absolute
`--config` selector. Follow [profile setup](profiles.md) for alias/store ownership
and conflict checks before creating or updating a task.

For operations that require external credentials, the scheduled session must
use the intended credential profile through Claude's native environment/secret
surface or the consumer's bound SessionStart hook. Unrelated unfinished
mappings do not block local compounding; required publication authentication
does. Pending setup binds reminders without credential activation. The profile in the task prompt selects
knowledge; it does not select credentials. One consumer hook binds one profile
for all new local Claude sessions, so use a separate consumer/project
configuration or provider-native cloud environment when simultaneous tasks need
different profiles. Never copy a credential value into the task prompt. A task
cannot change credential profiles midway through a run.
