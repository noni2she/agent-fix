# Agent Fix — TODO

## v3.2 — Batch Issue Processing

- [ ] **Google Sheets adapter** (`engine/issue_source/google_sheets.py`)
  - [x] `GoogleSheetsAdapter.list_all()` — read sheet → write `issues/sources/<id>.json` → return IDs
  - [x] `GoogleSheetsAdapter.fetch()` — read from local JSON (written by list_all)
  - [ ] Column mapping: support custom `column_map` in options
  - [ ] Auth: support API key (public sheets) in addition to service account

- [ ] **Jira adapter** (`engine/issue_source/jira.py`)
  - [ ] `JiraAdapter.fetch()` — fetch single issue via REST API
  - [ ] `JiraAdapter.list_all()` — JQL query → list of issue IDs
  - [ ] Env vars: `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, `JIRA_API_TOKEN`

## v3.3 — Parallel Execution (Git Worktree)

- [ ] **Git worktree parallel execution**
  - For each issue, create a separate git worktree in a temp branch
  - Run `_execute_workflow()` concurrently (asyncio.gather or semaphore)
  - Merge worktrees back after PASS; discard on FAIL
  - Requires: git worktree support in target project, configurable max_workers
  - Config: `batch.parallel: true`, `batch.max_workers: 3`
