# GitHub Copilot compounding schedule

Copilot CLI 1.0.86 exposes experimental `/every` and `/after` commands, but
they belong to the current interactive session. An `/every` schedule triggers
only while that session is running. Resuming restores it and starts the next
recurring wait from reopen; missed recurring runs are not caught up. An
overdue `/after` schedule runs immediately when the session is reopened. These
commands are useful for attended session work, but they are not a durable
unattended daily compounding automation.

Do not report `/every 1d` as completed automation setup. For durable work, use
an explicitly authorized external scheduler that invokes `copilot -p`, such as
a GitHub Actions scheduled workflow, or use a Copilot cloud automation with
the repository's Agents secrets and variables. Follow the provider's current
documentation:

<https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/schedule-prompts>

Creating a repository workflow or cloud automation mutates remote state. Show
the exact proposed cadence, repository, credential surface, working directory
and prompt, then obtain the developer's confirmation before creating or
updating it. Search for this exact marker first and keep one owner per signal
store:

~~~text
agent-knowledge-compound:<workspace_id>
~~~

The scheduled invocation must start `copilot -p` in the intended repository
and direct it to the installed `knowledge-compound` skill with the absolute
launcher plus pinned registry/profile or direct config selector. Keep the
prompt short and stable:

~~~text
Run the installed knowledge-compound skill using
/work/knowledge/.agent-knowledge-venv/bin/agent-knowledge with
--settings /work/local/profiles.yaml --profile work on every configured call.
Process pending signals, follow its publication and drain policy, and report
the run, dispositions and retained/drained inputs. Do not merge PRs or
force-push. Marker: agent-knowledge-compound:workspace:example
~~~

Pin credentials required by the scheduled work through the chosen durable
provider surface. Unrelated unfinished profile mappings do not block local
compounding; required publication authentication does. GitHub Actions
can map Actions secrets or an Actions environment; Copilot cloud automation
uses repository or organization Agents secrets and variables. Never copy a
credential value into the prompt. A knowledge profile selects routing and does
not change credentials already loaded into a running harness.

Run the exact invocation once before enabling recurrence. Verify configured
`doctor`, installed skill discovery, the activity record and the retained or
drained inputs. Keep native pause/remove controls visible. If no durable surface
is authorized, report Copilot automation as `provider-limited` and leave the
workspace and signals unchanged. Do not silently create cron, launchctl, a
daemon or a shell-startup mutation.
