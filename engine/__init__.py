"""
Bugfix Workflow Engine — Phase 1 plugin refactor

剩餘公開 API：
- Config / IssueSource：被 MCP server 與 SDK driver 共用
- Tools：被即將寫的 MCP server import
- Skill loader：暫存（park）狀態，目前無人 import
"""
__version__ = "4.0.0-refactor"

# Config
from .config import ProjectConfig, load_config_from_env, ConfigurationError, IssueSourceConfig

# Issue Source
from .issue_source import (
    IssueSourceAdapter,
    LocalJsonAdapter,
    JiraAdapter,
    IssueNotFoundError,
    IssueSourceError,
    IssueSourceConfigError,
    create_adapter,
)

# Skill Loader (parked — kept for possible Phase 2/3 reuse)
from .skill_loader import load_skill

# Tools (will be imported by mcp_servers/agent_fix_tools/server.py in Step 3c-1)
from .tools import init_tools

__all__ = [
    "ProjectConfig",
    "IssueSourceConfig",
    "load_config_from_env",
    "ConfigurationError",
    "IssueSourceAdapter",
    "LocalJsonAdapter",
    "JiraAdapter",
    "IssueNotFoundError",
    "IssueSourceError",
    "IssueSourceConfigError",
    "create_adapter",
    "load_skill",
    "init_tools",
]
