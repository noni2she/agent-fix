"""
Bugfix Workflow Engine v3.0 — Skill-Based
移除 Pydantic models 和 validators，改用 skill_loader + markdown output
"""
__version__ = "3.0.0"

# Config
from .config import ProjectConfig, load_config_from_env, ConfigurationError
from .project_spec import ProjectSpec

# Agent Runner
from .agent_runner import (
    run_in_session,
    create_copilot_session,
    setup_sdk_error_silencing,
    init_agent_runner,
    ANALYZE_IMPLEMENT_TOOLS,
    TEST_TOOLS,
)

# Skill Loader
from .skill_loader import load_skill

# Tools
from .tools import init_tools, TOOL_MAP

__all__ = [
    # Config
    "ProjectConfig",
    "load_config_from_env",
    "ConfigurationError",
    "ProjectSpec",
    # Agent Runner
    "run_in_session",
    "create_copilot_session",
    "setup_sdk_error_silencing",
    "init_agent_runner",
    "ANALYZE_IMPLEMENT_TOOLS",
    "TEST_TOOLS",
    # Skill Loader
    "load_skill",
    # Tools
    "init_tools",
    "TOOL_MAP",
]
