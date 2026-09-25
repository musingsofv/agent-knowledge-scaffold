# Neutral examples

This directory is a small fictional workspace used to exercise the standalone
CLI. It is not an organization's default taxonomy or policy. Replace its
catalog identifiers, scopes, sources and publication settings when onboarding a
real workspace.

The workspace contains one example for every initial knowledge kind, plus
service, operational procedure and verification runbooks. Verification reports
belong with the owning repository or CI run, outside the canonical source. Run the following from the
repository root:

```bash
uv run agent-knowledge --config examples/knowledge-workspace.yaml doctor
uv run agent-knowledge --config examples/knowledge-workspace.yaml validate \
  --request-file - <<'JSON'
{"sources":["example-knowledge"]}
JSON
uv run agent-knowledge --config examples/knowledge-workspace.yaml validate \
  --request-file - <<'JSON'
{"signal_files":["observation.md"]}
JSON
```
