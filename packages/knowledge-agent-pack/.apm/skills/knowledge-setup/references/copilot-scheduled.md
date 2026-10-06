# GitHub Copilot CLI local compounding

Copilot CLI's `/every` and `/after` commands belong to an interactive session.
They do not provide durable unattended daily compounding. In the previously
verified version, recurring waits resume from reopen and missed recurring runs
are not caught up; check current provider help rather than promising persistence.
See the provider's [scheduled prompts guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/automate-copilot-cli/schedule-prompts).

When no durable native local schedule is available, configure the installed
[prompt fallback](local-compounding.md). Setup binds the portable prompt marker
to native `userPromptTransformed`. Its output preserves the user's prompt and
adds main-agent delegation context only when compounding is due. Prompt-mode repository
hooks require an already trusted working directory; setup does not grant trust.

Verify an ordinary prompt delegates a worker loading the installed compound
skill, with the exact launcher, explicit selector, originating consumer and
available provider/session/worker handles. The worker atomically rechecks due
state before editing, publishing or draining. Redundant workers may spawn and
exit. The main task continues; no qualifying prompt means no run. A later prompt
must remain quiet after a completed run. Treat a missing delegation capability
or unauthenticated model as an explicit proof gap, never a successful fixture.

Native subagent tools are the execution interface. Begin the worker's task with
`[agent-knowledge-compound-worker]` as the shared reference requires. Never use
shell-started `copilot -p` or another model CLI as the worker. Missing native
subagent tools leave prompt-triggered compounding pending.

In a marked child, the hook preserves reflection, omits recursive delegation
and reasserts the setup-bound exact runtime, explicit selector and installed
compound skill. It exposes the child's hook session as `worker_id` and
`session_id`, under this binding's verified mapping to the native `agentId`.
Keep the original `parent_session_id` from the explicit parent
handoff, never from the child's hook session. Missing or conflicting setup
binding/handoff is a visible prerequisite, not permission to use the global
default or another profile. Bound context grants no authorization or ownership:
the worker must still claim an eligible run with `automatic: true`. Follow the
compound skill for parent-owned consumer/publication context and late identity
recording; the hook does not replace that handoff.

If a future installed version exposes durable native local scheduling, inspect
that capability, reuse the matching `agent-knowledge-compound:<workspace_id>`
owner and verify it before selecting `local-schedule`. Never run an independent
fallback alongside it. Existing external jobs remain user-owned; this setup
does not create workflows, cron/systemd jobs or hidden background processes.

Use the setup-generated local CLI launcher when a profile declares external
credentials. It supplies the provider's supported Bash activation and redaction
behavior for that new session. The knowledge selector does not activate or
switch credentials. Keep unrelated blank mappings visible and verify access
required by publication without borrowing another account or exposing values.

The [shared trigger procedure](local-compounding.md#pause-remove-and-report)
owns pause/remove controls, shared-store alias coordination, retries and the
rolling interval. Local execution may publish reviewed GitHub PRs according to
the skill's policy; it never merges automatically.
