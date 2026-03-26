# Commit Changes

Prepare a clean commit for the current working tree.

Guardrails:
- inspect `git status` before staging anything
- stage only files that belong to the requested change
- never amend an existing commit unless the user explicitly requests it
- do not push unless the user explicitly asks for push
- if unrelated changes are present, avoid staging them and call that out in the result

Workflow:
1. Review the current diff and decide the intended change boundary.
2. Stage only the relevant files.
3. Write a concise commit message in imperative mood.
4. Create the commit and report the exact message used.

Requested commit context:
{args}
