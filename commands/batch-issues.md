---
description: 批次修復多個 issue。每個 issue 在獨立 worktree 中平行執行，完成後交叉比對修改檔案，標記潛在 merge conflict。
argument-hint: <ISSUE-IDs> [config-path]
---

# Batch Issues

You are the **Batch Fix Coordinator**. You run fix-one-issue for each issue **in parallel** (each in its own isolated worktree), then produce a conflict-aware summary.

**Arguments**: `$ARGUMENTS`

Parse:
- First token = comma-separated issue IDs (e.g. `CHATAPP-5339,CHATAPP-5340,CHATAPP-5341`)
- Remaining tokens (optional) = `CONFIG_PATH` (e.g. `projects/morse-webapp/config.yaml`)

---

## Pre-flight

**1. Parse issue IDs:**

Split first token by comma, trim whitespace → `ISSUE_LIST`.

If empty → output:
```
❌ No issue IDs provided.
Usage: /agent-fix:batch-issues CHATAPP-5339,CHATAPP-5340 [config-path]
```
Stop.

**2. Load config (if provided):**

If `CONFIG_PATH` present → call `mcp__agent-fix-tools__set_project_config` with that path.
If result starts with `❌` → output `❌ Config error: <error>` and stop.

**3. Announce:**
```
🚀 Batch Fix — <N> issues (parallel, worktree-isolated)
   Issues: <ISSUE_LIST joined by ", ">
   Config: <CONFIG_PATH or "from env / previous set_project_config">
```

---

## Parallel Execution

Spawn **all** fix-one-issue Tasks simultaneously — do not wait for one to finish before starting the next:

```
results = await [
  Task("fix-one-issue", "<ISSUE_ID_1> [CONFIG_PATH]"),
  Task("fix-one-issue", "<ISSUE_ID_2> [CONFIG_PATH]"),
  ...
]
```

> Each Task runs the `agents/fix-one-issue.md` agent with `isolation: worktree`.
> Every issue gets its own git branch and worktree — no file-level conflicts during execution.
> Do NOT pass CONFIG_PATH to sub-tasks if config was already loaded via env var; only pass it
> if CONFIG_PATH was explicitly provided in the arguments to this command.

Wait for all Tasks to complete before proceeding to the summary.

---

## Conflict Detection

For each completed Task, parse the `RESULT:` line to extract modified files:

```
RESULT: DONE CHATAPP-5339 | files: apps/main/src/Upload.tsx,apps/main/src/hooks/useUpload.ts
RESULT: DONE CHATAPP-5340 | files: apps/main/src/Upload.tsx,apps/main/src/lib/api.ts
```

Build a file → [issue_ids] index:
```
apps/main/src/Upload.tsx        → [CHATAPP-5339, CHATAPP-5340]  ← CONFLICT
apps/main/src/hooks/useUpload.ts → [CHATAPP-5339]
apps/main/src/lib/api.ts        → [CHATAPP-5340]
```

A file is a **conflict** if 2 or more issues modified it.

---

## Final Summary

```
═══════════════════════════════════════════════════════════════
Batch Fix Summary — <TOTAL> issues

Results:
  ✅ CHATAPP-5339 — DONE
  ✅ CHATAPP-5340 — DONE
  ⚠️ CHATAPP-5341 — CHECKPOINT: cannot reproduce (confidence 0.2)

Stats: <N> done, <N> checkpoint

──────────────────────────────────────────────────────────────
Merge Conflict Warnings:                (omit section if none)

  ⚡ apps/main/src/Upload.tsx
     Modified by: CHATAPP-5339, CHATAPP-5340
     → Review both branches before merging. One fix may overwrite the other.

──────────────────────────────────────────────────────────────
Next Steps:

  DONE issues   → open PRs from each issue's worktree branch
  CHECKPOINT    → review artifacts in issues/reports/<id>/ and fix manually
  CONFLICTS     → merge CHATAPP-5339 first, then rebase CHATAPP-5340 on top
═══════════════════════════════════════════════════════════════
```
