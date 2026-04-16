"""
engine.behavior_validation
==========================

Playwright-based behavior validation for agent-fix bugfix-test phase.

Public API
----------
- BehaviorValidator   — top-level entry point (executor.py)
- ValidationReport    — result model
- ScenarioResult      — per-scenario result model

Usage (called from engine/tools.py)
------------------------------------
    validator = BehaviorValidator(
        project_root=Path("../my-app"),
        port=3000,
        workspace="web",        # optional, monorepo only
        headless=True,          # True in agent/CI, False for local debug
        dev_command=["yarn", "workspace", "web", "dev"],  # overrides workspace
    )
    report = await validator.validate(
        issue_id="BUG-1234",
        dynamic_scenario={
            "url_path": "/upload",
            "actions": [...],
            "assertions": [...],
        }
    )
    print(report.verdict)  # "PASS" | "FAIL" | "SKIPPED"
"""
from .executor import BehaviorValidator, ValidationReport, ScenarioResult
from .scenarios import TestScenario, ActionStep, Assertion, create_scenario_from_dict

__all__ = [
    "BehaviorValidator",
    "ValidationReport",
    "ScenarioResult",
    "TestScenario",
    "ActionStep",
    "Assertion",
    "create_scenario_from_dict",
]
