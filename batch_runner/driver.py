"""
Batch driver — Phase 1 SDK layer

Iterates a list of issues and runs /fix-one-issue <issue_id> for each one
inside an isolated git worktree, using the Claude Agent SDK.

Usage:
    python -m batch_runner.driver --issues CHATAPP-1,CHATAPP-2
    python -m batch_runner.driver --issues-file issues.txt
    python -m batch_runner.driver --source jira --jql "project = CHATAPP AND status = 'To Do'"

Required env vars:
    PROJECT_CONFIG  — path to project YAML config
    ANTHROPIC_API_KEY

State file:
    batch_runner/state/<batch_id>.json
    Tracks per-issue status so interrupted runs can be resumed.

Concurrency:
    Sequential only (--parallel N is stubbed, will arrive in Phase 1.5 via Agent Teams).
"""
import argparse
import asyncio
import datetime
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional SDK import — fail gracefully so engine/ tests still import
# ---------------------------------------------------------------------------
try:
    import anthropic
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_ROOT = Path(__file__).parent.parent.resolve()
STATE_DIR = AGENT_ROOT / "batch_runner" / "state"
MAX_RETRIES = 1          # one retry per issue on session failure
WORKTREE_PREFIX = "batch-fix"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _load_state(batch_id: str) -> dict:
    path = STATE_DIR / f"{batch_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"batch_id": batch_id, "issues": {}}


def _save_state(batch_id: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{batch_id}.json"
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _mark(state: dict, issue_id: str, status: str, detail: str = "") -> None:
    state["issues"][issue_id] = {
        "status": status,
        "detail": detail,
        "updated": datetime.datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Worktree lifecycle
# ---------------------------------------------------------------------------

def _worktree_add(issue_id: str) -> Path:
    """Create an isolated git worktree for this issue."""
    branch = f"bugfix/{issue_id}-auto"
    worktree_path = AGENT_ROOT.parent / f"{WORKTREE_PREFIX}-{issue_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), "main"],
        cwd=str(AGENT_ROOT),
        check=True,
        capture_output=True,
    )
    return worktree_path


def _worktree_remove(worktree_path: Path) -> None:
    """Remove worktree (best-effort; does not raise on failure)."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(AGENT_ROOT),
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Per-issue session runner
# ---------------------------------------------------------------------------

async def _run_issue(issue_id: str, project_config: str) -> dict:
    """
    Run /fix-one-issue <issue_id> for one issue via the Claude Agent SDK.

    Returns {"status": "done" | "checkpoint" | "error", "detail": str}
    """
    if not _SDK_AVAILABLE:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    client = anthropic.Anthropic()

    # System prompt: inform Claude Code that this is an automated session
    system = (
        f"You are running as an automated batch agent fixing issue {issue_id}.\n"
        f"PROJECT_CONFIG={project_config}\n"
        "Do not ask clarifying questions. Execute /fix-one-issue and stop."
    )
    user_message = f"/fix-one-issue {issue_id}"

    # Simple single-turn invocation — the /fix-one-issue command orchestrates
    # multi-phase work via Task tool internally, so we run one agentic loop.
    messages = [{"role": "user", "content": user_message}]
    full_response = []

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full_response.append(text)

    result_text = "".join(full_response)

    if "CHECKPOINT" in result_text:
        return {"status": "checkpoint", "detail": result_text[:500]}
    if "Fix Complete" in result_text:
        return {"status": "done", "detail": result_text[:500]}
    return {"status": "unknown", "detail": result_text[:500]}


# ---------------------------------------------------------------------------
# Per-issue dispatcher (with retry + worktree)
# ---------------------------------------------------------------------------

async def _dispatch_issue(
    issue_id: str,
    project_config: str,
    state: dict,
    batch_id: str,
) -> None:
    """Run one issue: worktree isolation + one retry on failure."""
    if state["issues"].get(issue_id, {}).get("status") in ("done",):
        print(f"  [{issue_id}] already done, skipping")
        return

    worktree_path: Path | None = None
    attempt = 0

    while attempt <= MAX_RETRIES:
        try:
            print(f"  [{issue_id}] attempt {attempt + 1}/{MAX_RETRIES + 1} — creating worktree")
            worktree_path = _worktree_add(issue_id)

            t0 = time.perf_counter()
            result = await _run_issue(issue_id, project_config)
            elapsed = time.perf_counter() - t0

            status = result["status"]
            detail = result["detail"]
            print(f"  [{issue_id}] {status} ({elapsed:.0f}s)")

            _mark(state, issue_id, status, detail)
            _save_state(batch_id, state)

            if status in ("done", "checkpoint"):
                return  # don't retry done or human-checkpoint issues

            # unknown / error → retry
            attempt += 1

        except subprocess.CalledProcessError as e:
            print(f"  [{issue_id}] worktree error: {e.stderr.decode()[:200]}")
            _mark(state, issue_id, "error", f"worktree: {e.stderr.decode()[:200]}")
            _save_state(batch_id, state)
            attempt += 1

        except Exception as e:
            print(f"  [{issue_id}] session error: {e}")
            _mark(state, issue_id, "error", str(e)[:300])
            _save_state(batch_id, state)
            attempt += 1

        finally:
            if worktree_path:
                _worktree_remove(worktree_path)
                worktree_path = None

    # Exhausted retries
    if state["issues"].get(issue_id, {}).get("status") not in ("done", "checkpoint"):
        _mark(state, issue_id, "checkpoint", f"exhausted {MAX_RETRIES + 1} attempts — human review required")
        _save_state(batch_id, state)
        print(f"  [{issue_id}] CHECKPOINT (retries exhausted)")


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

async def run_batch(issue_ids: list[str], project_config: str, batch_id: str) -> None:
    state = _load_state(batch_id)
    state.setdefault("started", datetime.datetime.now().isoformat())
    state.setdefault("project_config", project_config)
    _save_state(batch_id, state)

    print(f"\n🚀 Batch {batch_id} — {len(issue_ids)} issues")
    print(f"   State: {STATE_DIR / batch_id}.json\n")

    for issue_id in issue_ids:
        await _dispatch_issue(issue_id, project_config, state, batch_id)

    # Summary
    counts: dict[str, int] = {}
    for v in state["issues"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1

    print(f"\n📊 Batch complete — {counts}")
    print(f"   State file: {STATE_DIR / batch_id}.json")


# ---------------------------------------------------------------------------
# Issue list resolvers
# ---------------------------------------------------------------------------

def _issues_from_csv(csv: str) -> list[str]:
    return [i.strip() for i in csv.split(",") if i.strip()]


def _issues_from_file(path: str) -> list[str]:
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def _issues_from_jira(jql: str, project_config: str) -> list[str]:
    sys.path.insert(0, str(AGENT_ROOT))
    from engine.config import load_config_from_env
    from engine.issue_source import create_adapter

    os.environ["PROJECT_CONFIG"] = project_config
    config = load_config_from_env()
    adapter = create_adapter(config.issue_source)
    return adapter.list_all(filter=jql)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="agent-fix batch runner")
    parser.add_argument("--issues", help="Comma-separated issue IDs")
    parser.add_argument("--issues-file", help="Path to file with one issue ID per line")
    parser.add_argument("--source", choices=["jira"], help="Fetch issue list from source")
    parser.add_argument("--jql", help="JQL filter (used with --source jira)")
    parser.add_argument("--batch-id", help="Resume an existing batch (default: new UUID)")
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="[Phase 1.5] Number of parallel issues (currently only 1 is supported)"
    )
    args = parser.parse_args()

    if args.parallel != 1:
        print("ERROR: --parallel N > 1 is not yet supported (arrives in Phase 1.5 via Agent Teams)")
        sys.exit(1)

    project_config = os.environ.get("PROJECT_CONFIG", "")
    if not project_config:
        print("ERROR: PROJECT_CONFIG environment variable is required")
        sys.exit(1)

    # Resolve issue list
    if args.issues:
        issue_ids = _issues_from_csv(args.issues)
    elif args.issues_file:
        issue_ids = _issues_from_file(args.issues_file)
    elif args.source == "jira":
        if not args.jql:
            print("ERROR: --jql is required with --source jira")
            sys.exit(1)
        issue_ids = _issues_from_jira(args.jql, project_config)
    else:
        parser.print_help()
        sys.exit(1)

    if not issue_ids:
        print("No issues to process.")
        sys.exit(0)

    batch_id = args.batch_id or datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    asyncio.run(run_batch(issue_ids, project_config, batch_id))


if __name__ == "__main__":
    main()
