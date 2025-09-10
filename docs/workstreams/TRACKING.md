# Tracking: Issues, PRs, and Project Board

## Labels (create in GitHub)
- `workstream:orchestrator`
- `workstream:agents_llm`
- `workstream:tools`
- `workstream:api_config`
- `workstream:observability`
- `workstream:frontend_ui`
- `workstream:devops_github`
- `workstream:security`
- `type:bug`, `type:task`, `type:feature`

## Issue Conventions
- Title: concise action (e.g., "Orchestrator: define Instruction schema")
- Body: context, acceptance criteria, test plan
- Labels: pick one `workstream:*` and one `type:*`
- Link: reference docs or ADRs as needed

## PR Conventions
- Reference issues with `Fixes #123` or `Closes #123`
- Keep PRs focused; include tests and docs changes
- Include screenshots/trace IDs if relevant

## Project Board
- Columns: Todo, In Progress, In Review, Done
- Automation: PRs auto-link to issues; Done when merged

## Cadence
- Open issues from the checklists in each workstream doc
- Use milestones per phase (POC, M1, M2, etc.)
