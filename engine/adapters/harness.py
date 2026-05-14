"""
Harness enforcement utilities — phase-aware tool constraints.

Rules live in `engine/harness_rules.yaml` (declarative).
This module loads them at import time and exposes two functions called by
all three adapters (claude / openai / copilot) at tool dispatch time:

    check_tool_blocked(tool_name, session)   — pre-check; returns blocking
                                                message or None
    apply_tool_result_limits(tool_name, result, session)
                                              — post-process; truncates if needed

The phase is read from `session.harness_phase` (set in agent_runner.py).
Keeping logic here means new constraints are added in YAML and apply
across all adapters.
"""
from pathlib import Path
from typing import Optional

import yaml


_RULES_PATH = Path(__file__).resolve().parent.parent / "harness_rules.yaml"
_rules: dict = {}


def _load_rules() -> dict:
    """Load the YAML rules at import time. Reload by calling explicitly if needed."""
    global _rules
    if not _RULES_PATH.exists():
        _rules = {"phases": {}, "truncation_suffix": ""}
        return _rules
    with _RULES_PATH.open(encoding="utf-8") as f:
        _rules = yaml.safe_load(f) or {}
    _rules.setdefault("phases", {})
    _rules.setdefault("truncation_suffix", "")
    return _rules


_load_rules()


def _phase_for(session) -> Optional[dict]:
    """Return the phase-specific rule dict, matching on substring of harness_phase."""
    phase_name = getattr(session, "harness_phase", "") or ""
    phase_name = phase_name.lower()
    for key, cfg in _rules.get("phases", {}).items():
        if key in phase_name:
            return cfg
    return None


def check_tool_blocked(tool_name: str, session) -> Optional[str]:
    """Returns an error string if the tool should be blocked; None if allowed.

    Increments a per-session counter (`session._tool_counts[tool_name]`); when
    the count reaches the configured limit, returns the blocked message
    (Positive Prompt Injection — tells the LLM what to do next, not just refuses).
    """
    if session is None:
        return None
    phase = _phase_for(session)
    if not phase:
        return None

    limit = (phase.get("tool_limits") or {}).get(tool_name)
    if limit is None:
        return None

    counts = getattr(session, "_tool_counts", None)
    if counts is None:
        counts = {}
        session._tool_counts = counts

    count = counts.get(tool_name, 0)
    counts[tool_name] = count + 1
    if count >= limit:
        msg = (phase.get("blocked_messages") or {}).get(tool_name)
        return msg.strip() if msg else f"❌ {tool_name} exceeded limit ({limit}) in this phase."
    return None


def apply_tool_result_limits(tool_name: str, result: str, session) -> str:
    """Post-processes a tool result; truncates when over the configured cap."""
    if session is None:
        return result
    phase = _phase_for(session)
    if not phase:
        return result

    max_chars = (phase.get("tool_result_limits") or {}).get(tool_name)
    if max_chars is None or len(result) <= max_chars:
        return result

    suffix = _rules.get("truncation_suffix", "") or ""
    return result[:max_chars] + suffix
