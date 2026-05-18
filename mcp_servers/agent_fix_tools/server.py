"""
agent_fix_tools MCP Server

Exposes 6 domain tools for the agent-fix Claude Code plugin:
  - set_project_config      (call once per session before other tools)
  - fetch_issue             (extract sub-agent)
  - run_behavior_validation (test sub-agent)
  - run_typescript_check    (implement / test sub-agents)
  - run_eslint              (implement / test sub-agents)
  - record_tech_debt        (test sub-agent)

Startup:
    python -m mcp_servers.agent_fix_tools.server

Optional env var:
    PROJECT_CONFIG  — path to project YAML config (e.g. ./projects/my-app.yaml)
                      If not set, call set_project_config() before using other tools.
"""
import sys
from pathlib import Path

# Make engine importable when running as __main__
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mcp.server.fastmcp import FastMCP

from engine.config import load_config_from_env
from engine.issue_source import create_adapter
import engine.tools as _tools

# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------

mcp = FastMCP("agent_fix_tools")

# Lazy init — won't crash if PROJECT_CONFIG is not set at startup.
# Config can be loaded at runtime via set_project_config().
_config = None
try:
    _config = load_config_from_env()
    _tools.init_tools(_config)
except Exception:
    pass  # set_project_config() must be called before other tools


# ---------------------------------------------------------------------------
# Tool: set_project_config
# ---------------------------------------------------------------------------

@mcp.tool()
def set_project_config(config_path: str) -> str:
    """
    Dynamically load a project config for this session.

    Call once at the start of a session when PROJECT_CONFIG env var is not set,
    or when you want to target a specific project config explicitly.

    Args:
        config_path: Path to the project config YAML file.
                     Relative to the current working directory, or absolute.
                     Example: "projects/morse-webapp/config.yaml"

    Returns confirmation with the loaded project name, or an error message.
    """
    global _config
    try:
        from engine.config import ProjectConfig
        _config = ProjectConfig.from_yaml(config_path)
        _tools.init_tools(_config)
        return f"✅ Config loaded: {_config.project_name} ({config_path})"
    except Exception as e:
        return f"❌ set_project_config failed: {e}"


# ---------------------------------------------------------------------------
# Tool: fetch_issue
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_issue(issue_id: str) -> str:
    """
    Fetch an issue from the configured source (local JSON / Jira / Google Sheets).

    Returns a JSON string with the standard IssueData fields:
      issue_id, summary, description, reproduction_steps, expected, actual,
      module, attachments (and source-specific extras).

    The returned JSON is the canonical exchange format that flows from the
    extract sub-agent into the analyze sub-agent's prompt.
    """
    import json

    if _config is None:
        return "❌ fetch_issue failed: no project config loaded. Call set_project_config(config_path) first."
    try:
        adapter = create_adapter(_config.issue_source)
        data = adapter.fetch(issue_id)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"❌ fetch_issue failed: {e}"


# ---------------------------------------------------------------------------
# Tool: run_behavior_validation
# ---------------------------------------------------------------------------

@mcp.tool()
def run_behavior_validation(issue_id: str, scenario_json: str) -> str:
    """
    Run Playwright behavior validation for a single scenario.

    Args:
        issue_id:      The issue being tested (used for screenshot naming and logs).
        scenario_json: JSON string describing the scenario.
                       Schema:
                         {
                           "url_path": "/path",
                           "actions": [
                             {"type": "goto",        "value": "/path"},
                             {"type": "click",       "selector": "button"},
                             {"type": "wait_for",    "selector": ".el"},
                             {"type": "type",        "selector": "input", "value": "text"},
                             {"type": "set_files",   "selector": "input[type='file']",
                                                     "files": ["/abs/path/file.mp4"]},
                             {"type": "screenshot"}
                           ],
                           "assertions": [...]
                         }

    IMPORTANT: This tool is limited to 3 calls per sub-agent session.
    Use view / bash to confirm selectors and page structure before calling.
    """
    _tools.set_current_issue_id(issue_id)
    return _tools.run_behavior_validation(scenario_json)


# ---------------------------------------------------------------------------
# Tool: run_typescript_check
# ---------------------------------------------------------------------------

@mcp.tool()
def run_typescript_check() -> str:
    """
    Run TypeScript compilation check on the project.

    Returns PASSED / FAILED summary with up to 10 error lines.
    Timeout: 120 s.
    """
    return _tools.run_typescript_check()


# ---------------------------------------------------------------------------
# Tool: run_eslint
# ---------------------------------------------------------------------------

@mcp.tool()
def run_eslint() -> str:
    """
    Run ESLint on the project.

    Returns PASSED (with warning count) or FAILED (with up to 10 error lines).
    Timeout: 120 s.
    """
    return _tools.run_eslint()


# ---------------------------------------------------------------------------
# Tool: record_tech_debt
# ---------------------------------------------------------------------------

@mcp.tool()
def record_tech_debt(issue_id: str, missing_tests: list[str], reason: str) -> str:
    """
    Append a tech-debt entry to tech_debt.json.

    Args:
        issue_id:      The issue this debt is associated with.
        missing_tests: List of test descriptions that are missing / deferred.
        reason:        Why the tests are missing (time constraint, infra limitation, etc.).
    """
    return _tools.record_tech_debt(issue_id, missing_tests, reason)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
