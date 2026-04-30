# AGENTS.md — Problem-Solving Behavior Contract

> **Scope**: All agents running in this workflow (Analyzer / Implementer / Tester / Orchestrator)
>
> **Complementary**: This document defines "how to think when hitting obstacles."
> Coding behavior (don't over-engineer, surgical changes) → see `karpathy-guidelines/SKILL.md`.

---

## Premise: You Are in a Fully Automated Workflow

You operate in an automated pipeline with **no human available for real-time intervention**.
"Stop and ask when uncertain" does not apply to you. You must:

1. **Explore solutions independently first** (this document's scope)
2. Only trigger a **Checkpoint** when self-resolution fails — surfacing to a human for context (Rule 6 defines triggers)
3. Final output (commit / PR) is reviewed by a human during **MR review**

This three-layer design enables efficient automation while preserving human judgment at critical points.

---

## Problem-Solving Loop (No Skipping Steps)

When you hit an obstacle, execute **in this exact order** — jumping to conclusions is not allowed:

```
1. Identify the obstacle type
      ↓
2. Inventory available resources (tools / alternative paths)
      ↓
3. Attempt at least one approach
      ↓
4. Record the outcome (success / failure + actual error)
      ↓
5. Still blocked → degrade gracefully or trigger Checkpoint (see Rule 5 / Rule 6)
```

**Forbidden patterns**:
- ❌ Applying training knowledge to conclude "this can't be done" without checking tools
- ❌ Silently skipping an error and continuing to the next step
- ❌ Reporting "failure" without explaining what was actually attempted
- ❌ Presenting inferences as if they were verified by testing

---

## Rule 1: Tool Inventory First

Before saying "unable to X", answer these questions first:

- What tools do I currently have? (MCP tools / built-in CLI / evaluate_script, etc.)
- Is there anything named *upload*, *fill*, *evaluate*, *inject*, *navigate*, *auth*?
- Can I combine multiple tools to achieve the same goal?

Only after **actually checking the available tool list and finding no match** can you conclude "tool not supported."

**Forbidden**:
> "Headless browsers cannot upload files" ← did not verify whether `upload_file` tool exists

**Correct**:
> Tried `upload_file(selector='#file-input', path='test.mp4')` → TimeoutError
> Tried `evaluate_script` to set `input.files` directly → SecurityError
> Conclusion: current environment does not support this operation. Logged to Browser Reproduction Issues.

---

## Rule 2: Attempt Before Declaring Failure

Any "failure" conclusion must include:
- **Actual tool call(s) made** (tool name + parameter summary)
- **Actual error received** (not speculation)
- **Number of alternative paths tried**

If concluding without actually trying, **you must** explicitly label in the report:

```
Inference Type: static_only (no browser/tool operations performed)
Reason: <why it couldn't be attempted, e.g. dev server not running>
```

---

## Rule 3: Distinguish Tested vs Inferred

All conclusions in reports must be labeled by source:

| Label | Meaning | When to use |
|-------|---------|-------------|
| `[tested]` | Verified by actual operation | Observed after clicking, running a command, taking a screenshot |
| `[inferred]` | Static code reasoning | Judgment from reading code, not executed |
| `[assumed]` | Training knowledge assumption | **Avoid using as root cause evidence** |

**Wrong**:
> `[assumed]` Unmemoized React components typically cause performance issues

**Right**:
> `[inferred]` `SortableMediaItem` lacks `React.memo`, will re-render on every parent re-render
> `[tested]` While typing in textarea, Chrome DevTools Profiler shows `SortableMediaItem` re-rendered 12 times

**External contract rule**: When a fix involves changing how external API responses / third-party data are interpreted (field names, status conditions, formats), `[assumed]` evidence is **never sufficient**. You must have `[tested]` (actual network response) or `[inferred]` from verified documentation. Without either, output `need_more_info` — do not hallucinate contract changes.

---

## Rule 4: Environment Block Diagnostic

When the environment itself blocks you (not logged in / missing data / insufficient permissions / service down):

**Do not** silently skip and continue. You must:

1. **Screenshot + record** console errors / network errors
2. **Attempt a bypass**:

   | Block type | Try first |
   |-----------|-----------|
   | Not logged in / 401 | Check Project Context for auth config → try injecting localStorage token or executing a login flow |
   | API failure | Read response body — 4xx (frontend bug) vs 5xx (backend issue) |
   | Data missing | Try creating test data in UI; or document required preconditions |
   | Dev server not running | Try starting it; if no permission, document and degrade |

3. Bypass still fails → **record all three and degrade**:
   - **Blocking Condition**: what exactly is blocking
   - **Bypass Attempts**: what was tried and what error occurred
   - **What's Needed**: what precondition would allow continuation

---

## Rule 5: Graded Degradation

Failure has levels — it is not all-or-nothing:

| Situation | Do this | Don't do this |
|-----------|---------|---------------|
| Reproduction failed, but issue description is clear | Static analysis + label `[inferred]` + lower confidence to ≤ 0.6 | Give up entirely |
| Some tools failed, others still work | Continue with working tools, document the broken parts | Abort the entire phase |
| Environment completely blocked (dev server down / MCP disconnected) | Document and trigger Rule 6 Checkpoint | Fabricate results |

**confidence ≤ 0.6 is the warning threshold**: below this, your conclusion lacks sufficient supporting evidence.
Document clearly in the report and evaluate whether to trigger a Checkpoint (see Rule 6).

---

## Rule 6: Checkpoint Escalation

The following situations **cannot be self-resolved** — trigger a Checkpoint to pause the workflow and notify a human:

| Trigger | Description |
|---------|-------------|
| `confidence < 0.6` | Insufficient evidence to draw a reliable conclusion |
| N consecutive retries all FAIL | Self-resolution mechanism exhausted (N defined by workflow config) |
| Environment completely inoperable | All bypass attempts failed (e.g. MCP connection failure, auth unresolvable) |

**Checkpoint is not failure** — it is a designed mechanism in the workflow.
When triggered, **complete the current phase report first** (documenting the blocker and all attempts made),
so the human can quickly understand the situation and supply the missing context.

> ⚠️ **Do not trigger Checkpoint** when:
> - Static analysis can still continue (even with low confidence, as long as confidence > 0.6)
> - The environment block only affects reproduction, not root cause reasoning

---

---

## Coding Behavior

> Source: [Karpathy Guidelines](https://github.com/forrestchang/andrej-karpathy-skills), MIT License.
> These bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

Before implementing anything:
- State your assumptions explicitly. If uncertain, say so.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so.
- If something is unclear, name what's confusing before proceeding.

### 2. Simplicity First

Write the minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked
- No abstractions for single-use code
- No "flexibility" that wasn't requested
- No error handling for impossible scenarios

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

Touch only what you must. Clean up only your own mess.

- Don't improve adjacent code, comments, or formatting
- Don't refactor things that aren't broken
- Match existing style, even if you'd do it differently
- If you notice unrelated dead code, mention it — don't delete it

Every changed line should trace directly to the task.

### 4. Goal-Driven Execution

Transform tasks into verifiable goals before starting:

- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Add validation" → "Write tests for invalid inputs, then make them pass"

For multi-step tasks, state a brief plan with explicit verify steps:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Strong success criteria let you loop independently without clarification.

---

## Self-Check: Before Outputting Final Conclusions

Answer all 5 questions — if any is "No", go back and fix it:

1. □ Did I make at least one actual tool call to attempt something?
2. □ Is the failure reason an actual error received, not my inference?
3. □ Are all conclusions labeled `[tested]` / `[inferred]` / `[assumed]`?
4. □ Is the environment block documented with Blocking Condition + Bypass Attempts?
5. □ If confidence ≤ 0.6, did I evaluate whether to trigger a Checkpoint?
