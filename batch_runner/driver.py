"""
Batch driver — Phase 1 SDK layer

Iterates a list of issues and runs /fix-one-issue <issue_id> for each one
inside an isolated git worktree, by invoking the Claude Code CLI as a subprocess.
This ensures the plugin commands and MCP servers are available.

Usage:
    python -m batch_runner.driver --issues CHATAPP-1,CHATAPP-2
    python -m batch_runner.driver --issues-file issues.txt
    python -m batch_runner.driver --source jira --jql "project = CHATAPP AND status = 'To Do'"

Required env vars:
    PROJECT_CONFIG  — path to project YAML config

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

def _worktree_add(issue_id: str, project_root: Path) -> Path:
    """Create an isolated git worktree of the TARGET project for this issue."""
    branch = f"bugfix/{issue_id}-auto"
    worktree_path = project_root.parent / f"{WORKTREE_PREFIX}-{issue_id}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(worktree_path), "HEAD"],
        cwd=str(project_root),
        check=True,
        capture_output=True,
    )
    return worktree_path


def _worktree_remove(worktree_path: Path, project_root: Path) -> None:
    """Remove worktree (best-effort; does not raise on failure)."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(project_root),
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Per-issue session runner
# ---------------------------------------------------------------------------

def _run_issue(issue_id: str, project_config: str, worktree_path: Path) -> dict:
    """
    Invoke /fix-one-issue <issue_id> via Claude Code CLI inside the given worktree.

    --plugin-dir loads the agent-fix plugin (commands + agents).
    --mcp-config loads the agent-fix MCP server (fetch_issue / quality checks / etc.).
    Both point at the original agent-fix AGENT_ROOT so the Python venv and engine/
    are always available regardless of which worktree we're running in.

    Returns {"status": "done" | "checkpoint" | "error" | "unknown", "detail": str}
    """
    env = {**os.environ, "PROJECT_CONFIG": project_config}
    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--plugin-dir", str(AGENT_ROOT),
        "--mcp-config", str(AGENT_ROOT / ".mcp.json"),
        f"/agent-fix:fix-one-issue {issue_id}",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(worktree_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min ceiling per issue
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "detail": "timed out after 1800s"}

    output = result.stdout
    if result.returncode != 0:
        stderr = (result.stderr or "")[:300]
        return {"status": "error", "detail": f"exit {result.returncode}: {stderr}"}

    if "CHECKPOINT" in output:
        return {"status": "checkpoint", "detail": output[-500:]}
    if "Fix Complete" in output:
        return {"status": "done", "detail": output[-500:]}
    return {"status": "unknown", "detail": output[-500:]}


# ---------------------------------------------------------------------------
# Per-issue dispatcher (with retry + worktree)
# ---------------------------------------------------------------------------

async def _dispatch_issue(
    issue_id: str,
    project_config: str,
    project_root: Path,
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
            worktree_path = _worktree_add(issue_id, project_root)

            t0 = time.perf_counter()
            result = await asyncio.to_thread(_run_issue, issue_id, project_config, worktree_path)
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
                _worktree_remove(worktree_path, project_root)
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
    # Load config to resolve target project root (used for git worktree isolation)
    sys.path.insert(0, str(AGENT_ROOT))
    os.environ["PROJECT_CONFIG"] = project_config
    from engine.config import load_config_from_env
    config = load_config_from_env()
    project_root = config.get_project_root()

    state = _load_state(batch_id)
    state.setdefault("started", datetime.datetime.now().isoformat())
    state.setdefault("project_config", project_config)
    _save_state(batch_id, state)

    print(f"\n🚀 Batch {batch_id} — {len(issue_ids)} issues")
    print(f"   Project: {project_root}")
    print(f"   State: {STATE_DIR / batch_id}.json\n")

    for issue_id in issue_ids:
        await _dispatch_issue(issue_id, project_config, project_root, state, batch_id)

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
