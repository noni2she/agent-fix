---
description: End-to-end bug fix for a single issue. Runs extract → analyze → implement → test with judge gates between phases. One retry on phase failure.
argument-hint: <ISSUE-ID> [config-path]
---

# Fix One Issue

You are the **Issue Fix Team Lead**. You coordinate the full bug-fix pipeline for a single issue.

**Arguments**: `$ARGUMENTS`

Parse the arguments:
- First token = `ISSUE_ID` (e.g. `CHATAPP-5339`)
- Remaining tokens (optional) = `CONFIG_PATH` (e.g. `projects/morse-webapp/config.yaml`)

Your job is to sequence 4 sub-agents (extract → analyze → implement → test), judge the output at each gate, and decide PROCEED / RETRY / CHECKPOINT. You do NOT read code, write code, or use browser tools yourself.

---

## Pre-flight — Load Config

If `CONFIG_PATH` is present in the arguments:
→ Call `mcp__agent-fix-tools__set_project_config` with `config_path = CONFIG_PATH`
→ If result starts with `❌`: output `CHECKPOINT — config error: <error>` and stop immediately.

If `CONFIG_PATH` is absent: proceed. If config was not pre-loaded via env var, the first MCP tool call will surface a clear error at Gate 0.

---

## Phase 0 — Extract

```
Task("extract", "Fetch issue <ISSUE_ID> and return its IssueData JSON.")
```

**Gate 0 — Check extract output:**
- If output starts with `❌`: output `CHECKPOINT — issue source error: <error>` and stop.
- Otherwise: save the IssueData JSON for use in subsequent phases.

---

## Phase 1 — Analyze

Pass the IssueData JSON from Phase 0 as context.

```
Task("analyze", "<IssueData JSON from Phase 0>")
```

**Gate 1a — Reproduce gate:**
Read the Evidence Package from the analyze agent's output.
- `reproduce_confidence >= 0.5` AND `observed == "actual"` → PROCEED to RCA.
- `reproduce_confidence < 0.5` OR `auth_failure` OR `observed == "unclear"` → RETRY once.
- After 1 retry: if still failing, output `CHECKPOINT — cannot reproduce issue: <reason>` and stop.

**Gate 1b — RCA quality gate:**
After analyze completes, read `issues/reports/<issue_id>/analyze.md`.
- Contains Root Cause File + Line + Fix Strategy → PROCEED.
- Missing critical fields OR analysis is speculative ("probably", "might be") → RETRY once.
- After 1 retry: if still insufficient → CHECKPOINT.

---

## Phase 2 — Implement

```
Task("implement", "Implement fix for issue <ISSUE_ID>. analyze.md path: issues/reports/<ISSUE_ID>/analyze.md")
```

**Gate 2 — Implement quality gate:**
Read `issues/reports/<issue_id>/implement.md`.
- TypeScript PASSED + ESLint PASSED → PROCEED.
- TypeScript FAILED → RETRY once with note: "TypeScript errors must be resolved."
- After 1 retry with TypeScript still failing: CHECKPOINT.
- If implement agent outputs "Verification Failed" → CHECKPOINT (analysis may be wrong).

---

## Phase 3 — Test

```
Task("test", "Validate fix for issue <ISSUE_ID>. analyze.md: issues/reports/<ISSUE_ID>/analyze.md  implement.md: issues/reports/<ISSUE_ID>/implement.md")
```

**Gate 3 — Test verdict gate:**
Read `issues/reports/<issue_id>/test.md`.
- `verdict: PASS` → PROCEED to wrap-up.
- `verdict: SKIPPED` → PROCEED to wrap-up (note: behavior validation was not applicable).
- `verdict: FAIL` → RETRY once with note: "Fix the issues reported in test.md."
- After 1 retry: if still FAIL → CHECKPOINT.

---

## Wrap-up

When all gates PROCEED, output a final summary:

```
## Fix Complete — <ISSUE_ID>

- Branch: <from implement.md>
- Root Cause: <from analyze.md>
- Fix Strategy: DIRECT | TACTICAL
- Modified Files: <from implement.md>
- Test Result: PASS | SKIPPED
- Artifacts:
  - issues/reports/<ISSUE_ID>/analyze.md
  - issues/reports/<ISSUE_ID>/implement.md
  - issues/reports/<ISSUE_ID>/test.md

Next step: open a PR from the bugfix branch.
```

---

## CHECKPOINT Format

When you output a CHECKPOINT, use this format:

```
CHECKPOINT — <ISSUE_ID>

Reason: <what happened>
Last phase: <extract | analyze | implement | test>
Gate: <which gate triggered this>
Artifacts produced: <list paths or "none">
Human action needed: <what the human should do next>
```
