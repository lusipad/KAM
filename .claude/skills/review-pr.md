# Review PR

Review the current branch or staged diff as an engineer doing final code review.

Goals:
- identify bugs, regressions, risky assumptions, and missing tests
- keep findings ordered by severity
- cite concrete files, symbols, and line ranges when possible
- do not edit code unless the user explicitly asks for fixes

Workflow:
1. Inspect `git status`, `git diff`, and any changed tests.
2. Read the touched files carefully before forming conclusions.
3. Produce findings first.
4. If there are no findings, state that explicitly and mention residual risks or gaps.

Review focus:
- correctness and regressions
- data loss or destructive behavior
- concurrency / async hazards
- security-sensitive changes
- missing validation or error handling
- tests that should exist but do not

Requested review scope:
{args}
