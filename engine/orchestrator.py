# engine/orchestrator.py
"""
BugfixOrchestrator — Stage 5 Orchestrator-Worker 架構

設計原則：
  - 資訊隔離：每個 subagent 只收到完成當前任務所需的最小 context
  - Progressive Disclosure (Gated Reveal)：Analyze 分兩輪揭露 SKILL.md
      Gate REPRODUCE → Step 0（能力前置 + 瀏覽器重現）
      Gate RCA       → Steps 1–5（根源分析 + 報告）
  - Artifact 語義驗證：每次 spawn 前用純 Python 驗證上游 artifact
  - Retry 粒度：Gate 層級重試（非整個 phase 重跑）
  - Outcome 追蹤：run() 回傳 "fixed" | "failed" | "skipped"
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .agent_runner import create_session, run_in_session, ANALYZE_IMPLEMENT_TOOLS, TEST_TOOLS
from .config import ProjectConfig


MAX_IMPLEMENT_RETRIES = 3
MAX_GATE_RETRIES = 2


@dataclass
class GateResult:
    passed: bool
    reason: str


class BugfixOrchestrator:
    def __init__(
        self,
        config: ProjectConfig,
        project_root: Path,
        agent_root: Path,
        mcp_manager,
        skills: dict,
        project_context: str,
    ):
        self.config = config
        self.project_root = project_root
        self.agent_root = agent_root
        self.mcp_manager = mcp_manager
        self.skills = skills
        self.project_context = project_context

        project_key = config.get_project_key()
        self.report_dir = agent_root / "issues" / "reports" / project_key
        self.report_dir.mkdir(parents=True, exist_ok=True)

        self._gates = self._parse_gates(skills["analyze"])
        self._tokens: dict = {"input": 0, "output": 0}

    # ──────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────

    async def run(self, issue_id: str, issue_json: str, images: list | None = None) -> dict:
        print(f"\n{'═'*60}")
        print(f"  🎯 Orchestrator: {issue_id}")
        print(f"{'═'*60}")

        # ── Analyze phase（Progressive Disclosure）──
        analyze_status = await self._run_analyze(issue_id, issue_json, images)

        if analyze_status == "already_fixed":
            print("\n  ✅ Already fixed — no further action.")
            print(f"     Report: {self.report_dir / issue_id / 'analyze.md'}")
            return {**self._tokens, "outcome": "skipped"}

        if analyze_status != "confirmed":
            print(f"\n  ⏸  Analyze ended with status={analyze_status}")
            print(f"     Check: {self.report_dir / issue_id / 'analyze.md'}")
            return {**self._tokens, "outcome": "skipped"}

        # ── Spawn gate：validate analyze.md before implement ──
        gate = self._validate_analyze(issue_id)
        self._log_gate("analyze→implement", gate)
        if not gate.passed:
            print("  ⏸  Implement not spawned.")
            return {**self._tokens, "outcome": "skipped"}

        # ── Implement + Test loop ──
        for retry in range(MAX_IMPLEMENT_RETRIES + 1):
            await self._run_implement(issue_id, retry=retry)

            gate = self._validate_implement(issue_id)
            self._log_gate("implement→test", gate)

            verdict = await self._run_test(issue_id, retry=retry)
            print(f"\n  ⚖️  Verdict: {verdict}")

            if verdict == "PASS":
                print(f"\n  ✅ Fix complete! Reports: {self.report_dir / issue_id}/")
                return {**self._tokens, "outcome": "fixed"}

            if retry < MAX_IMPLEMENT_RETRIES:
                print(f"\n  🔄 FAIL → re-implement ({retry + 1}/{MAX_IMPLEMENT_RETRIES})")
            else:
                print(f"\n  💀 Max retries ({MAX_IMPLEMENT_RETRIES}) reached.")

        return {**self._tokens, "outcome": "failed"}

    # ──────────────────────────────────────────
    # Analyze — Progressive Disclosure
    # ──────────────────────────────────────────

    async def _run_analyze(self, issue_id: str, issue_json: str, images: list | None) -> str:
        print(f"\n{'─'*60}")
        print("  Phase: analyze (Gated Reveal)")
        print(f"{'─'*60}")

        _, session = await create_session(ANALYZE_IMPLEMENT_TOOLS, mcp_manager=self.mcp_manager)
        screenshot_dir = (
            self.agent_root / "issues" / "screenshots"
            / self.config.get_project_key() / issue_id
        )

        # ── Gate REPRODUCE: Step 0 全部（能力前置 + 瀏覽器重現）──
        for attempt in range(MAX_GATE_RETRIES + 1):
            prompt = self._build_reproduce_prompt(issue_id, issue_json, screenshot_dir)
            response = await run_in_session(
                session, "analyze-reproduce", prompt,
                max_tool_calls=35,
                images=images if attempt == 0 else None,
            )
            gate = self._validate_reproduce(response, screenshot_dir)
            if gate.passed:
                break
            if attempt < MAX_GATE_RETRIES:
                print(f"\n  ⚠️  Reproduce gate failed ({gate.reason}), retry {attempt + 1}/{MAX_GATE_RETRIES}")
            else:
                print(f"\n  ⚠️  Reproduce gate: {gate.reason} — proceeding to RCA with available observations")
                break  # non-fatal; RCA gate decides final status via analyze.md

        # ── Gate RCA: Steps 1–5 + 報告 ──
        report_path = self.report_dir / issue_id / "analyze.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            prompt = self._build_rca_prompt(issue_id, report_path)
            await run_in_session(session, "analyze-rca", prompt, max_tool_calls=40)
            if report_path.exists():
                break
            if attempt == 0:
                print("\n  ⚠️  analyze.md not written — retrying RCA gate...")

        # 0 tool calls = AI 可能依賴記憶幻覺分析，強制要求讀程式碼重來
        if getattr(session, 'last_turn_tool_calls', -1) == 0:
            print("\n  ⚠️  RCA gate: 0 tool calls — AI may have hallucinated. Retrying with explicit tool instruction...")
            grounded_prompt = (
                "你剛才的 RCA 分析沒有呼叫任何工具。\n"
                "**必須先使用 search_files / read_file 工具實際讀取相關程式碼**，再覆蓋寫入 analyze.md。\n"
                "不要依賴記憶或推斷，直接查看程式碼後再分析。\n\n"
                f"Target project root: {self.project_root}\n"
                f"Write analysis report to: {report_path}\n"
                f"Issue ID: {issue_id}\n"
            )
            await run_in_session(session, "analyze-rca-grounded", grounded_prompt, max_tool_calls=30)

        self._accumulate(session)
        status = self._read_analyze_status(issue_id)
        print(f"\n  📊 Analyze status: {status}")
        return status

    # ──────────────────────────────────────────
    # Implement phase
    # ──────────────────────────────────────────

    async def _run_implement(self, issue_id: str, retry: int = 0) -> None:
        label = f"implement{f'-retry-{retry}' if retry > 0 else ''}"
        print(f"\n{'─'*60}")
        print(f"  Phase: {label}")
        print(f"{'─'*60}")

        _, session = await create_session(ANALYZE_IMPLEMENT_TOOLS)
        prompt = self._build_implement_prompt(issue_id, retry=retry)
        await run_in_session(session, label, prompt, max_tool_calls=30)
        self._accumulate(session)

    # ──────────────────────────────────────────
    # Test phase
    # ──────────────────────────────────────────

    async def _run_test(self, issue_id: str, retry: int = 0) -> str:
        label = f"test{f'-retry-{retry}' if retry > 0 else ''}"
        print(f"\n{'─'*60}")
        print(f"  Phase: {label}")
        print(f"{'─'*60}")

        _, session = await create_session(TEST_TOOLS)
        prompt = self._build_test_prompt(issue_id, retry=retry)
        await run_in_session(session, label, prompt, max_tool_calls=40)
        self._accumulate(session)

        return self._read_test_verdict(issue_id, retry)

    # ──────────────────────────────────────────
    # Prompt builders — information isolation
    # ──────────────────────────────────────────

    def _build_reproduce_prompt(self, issue_id: str, issue_json: str, screenshot_dir: Path) -> str:
        preamble = self._gates["preamble"]
        reproduce = self._gates["REPRODUCE"]
        return (
            f"{self.project_context}"
            f"{preamble}"
            f"\n\n---\n\n"
            f"## 任務：Step 0 — 重現問題\n\n"
            f"**只執行 Step 0**（能力前置檢查 + 瀏覽器重現），完成後記錄觀察結果，等待進一步指令。"
            f"**不要開始 RCA，不要讀程式碼。**\n\n"
            f"{reproduce}"
            f"\n\n---\n\n"
            f"Issue 資料：\n\n```json\n{issue_json}\n```\n\n"
            f"截圖目錄：{screenshot_dir}/\n"
            f"Issue ID: {issue_id}\n"
        )

    def _build_rca_prompt(self, issue_id: str, report_path: Path) -> str:
        rca = self._gates["RCA"]
        return (
            f"## 任務：Steps 1–5 — RCA 分析並寫入報告\n\n"
            f"Step 0 重現已完成（見上方對話中的觀察記錄）。"
            f"以這些觀察為基礎，執行完整根源分析並寫入報告。\n\n"
            f"**重要：在撰寫任何分析結論前，必須先使用 search_files 或 read_file 工具實際讀取相關程式碼。**\n\n"
            f"{rca}"
            f"\n\n---\n\n"
            f"Target project root: {self.project_root}\n"
            f"Write analysis report to: {report_path}\n"
            f"Issue ID: {issue_id}\n"
        )

    def _build_implement_prompt(self, issue_id: str, retry: int = 0) -> str:
        analyze_path = self.report_dir / issue_id / "analyze.md"
        implement_path = self.report_dir / issue_id / "implement.md"

        retry_section = ""
        if retry > 0:
            prev_test = "test.md" if retry == 1 else f"test-retry-{retry - 1}.md"
            test_path = self.report_dir / issue_id / prev_test
            test_content = (
                test_path.read_text(encoding="utf-8")
                if test_path.exists()
                else f"(test report not found: {prev_test})"
            )
            retry_section = (
                f"\n\n## Previous Test Failure (retry {retry})\n\n"
                f"{test_content}\n\n"
                f"The implementation above did not pass verification. Fix the identified issues.\n"
            )

        return (
            f"{self.project_context}"
            f"{self.skills['implement']}"
            f"{retry_section}"
            f"\n\n---\n\n"
            f"Task: Implement the fix for issue {issue_id}.\n"
            f"Target project root: {self.project_root}\n"
            f"Read analysis from: {analyze_path}\n"
            f"Write implementation report to: {implement_path}\n"
        )

    def _build_test_prompt(self, issue_id: str, retry: int = 0) -> str:
        analyze_path = self.report_dir / issue_id / "analyze.md"
        implement_path = self.report_dir / issue_id / "implement.md"
        report_path = self.report_dir / issue_id / (
            "test.md" if retry == 0 else f"test-retry-{retry}.md"
        )

        return (
            f"{self.project_context}"
            f"{self.skills['test']}"
            f"\n\n---\n\n"
            f"Task: Verify the fix for issue {issue_id}.\n"
            f"Target project root: {self.project_root}\n"
            f"Analysis report: {analyze_path}\n"
            f"Implementation report: {implement_path}\n"
            f"Write verification report to: {report_path}\n"
        )

    # ──────────────────────────────────────────
    # Gate validators (pure Python)
    # ──────────────────────────────────────────

    @staticmethod
    def _validate_reproduce(response: str, screenshot_dir: Path) -> GateResult:
        has_screenshot = screenshot_dir.exists() and any(screenshot_dir.glob("*.png"))
        if has_screenshot:
            return GateResult(passed=True, reason=f"screenshot found in {screenshot_dir.name}/")

        observation_keywords = [
            "重現成功", "reproduction", "actual", "observed", "screenshot",
            "console error", "network", "4xx", "5xx", "already_fixed",
            "重現失敗", "無法重現", "fallback",
        ]
        if any(kw.lower() in response.lower() for kw in observation_keywords):
            return GateResult(passed=True, reason="observation evidence found in response")

        return GateResult(passed=False, reason="no screenshot and no observation evidence")

    # ──────────────────────────────────────────
    # Spawn gate validators (artifact semantic)
    # ──────────────────────────────────────────

    def _validate_analyze(self, issue_id: str) -> GateResult:
        path = self.report_dir / issue_id / "analyze.md"
        if not path.exists():
            return GateResult(passed=False, reason="analyze.md not found")

        text = path.read_text(encoding="utf-8")

        if not re.search(r'\*\*Status\*\*[:\s]+confirmed', text, re.IGNORECASE):
            return GateResult(passed=False, reason="status != confirmed")

        confidence_match = re.search(r'\*\*Confidence Score\*\*[:\s]+([\d.]+)', text)
        if confidence_match:
            try:
                if float(confidence_match.group(1)) < 0.6:
                    return GateResult(passed=False, reason=f"confidence {confidence_match.group(1)} < 0.6")
            except ValueError:
                pass

        if not re.search(r'\*\*Root Cause File\*\*[:\s]+\S', text):
            return GateResult(passed=False, reason="root_cause_file missing or empty")

        return GateResult(passed=True, reason="status=confirmed, confidence≥0.6, root_cause_file present")

    def _validate_implement(self, issue_id: str) -> GateResult:
        impl_path = self.report_dir / issue_id / "implement.md"
        if not impl_path.exists():
            return GateResult(passed=False, reason="implement.md not found")

        analyze_path = self.report_dir / issue_id / "analyze.md"
        if not analyze_path.exists():
            return GateResult(passed=True, reason="no analyze.md to cross-check — proceeding")

        analyze_text = analyze_path.read_text(encoding="utf-8")
        impl_text = impl_path.read_text(encoding="utf-8")

        m = re.search(r'\*\*Root Cause File\*\*[:\s]+(.+)', analyze_text)
        if not m:
            return GateResult(passed=True, reason="no root_cause_file to cross-check — proceeding")

        root_file = Path(m.group(1).strip()).name
        if root_file and root_file not in impl_text:
            return GateResult(
                passed=False,
                reason=f"root_cause_file '{root_file}' not referenced in implement.md",
            )

        return GateResult(passed=True, reason=f"root_cause_file '{root_file}' referenced in implement.md")

    # ──────────────────────────────────────────
    # Report readers
    # ──────────────────────────────────────────

    def _read_analyze_status(self, issue_id: str) -> str:
        report = self.report_dir / issue_id / "analyze.md"
        if not report.exists():
            return "missing"
        text = report.read_text(encoding="utf-8")
        if re.search(r'\*\*Status\*\*[:\s]+already_fixed', text, re.IGNORECASE):
            return "already_fixed"
        if re.search(r'\*\*Status\*\*[:\s]+confirmed', text, re.IGNORECASE):
            return "confirmed"
        return "need_more_info"

    def _read_test_verdict(self, issue_id: str, retry: int = 0) -> str:
        filename = "test.md" if retry == 0 else f"test-retry-{retry}.md"
        report = self.report_dir / issue_id / filename
        if not report.exists():
            return "FAIL"
        text = report.read_text(encoding="utf-8")
        m = re.search(r'\*\*Verdict\*\*[:\s]+\**\s*(PASS|FAIL)\**', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return "PASS" if "PASS" in text.upper() and "FAIL" not in text.upper() else "FAIL"

    # ──────────────────────────────────────────
    # SKILL.md gate parser
    # ──────────────────────────────────────────

    @staticmethod
    def _parse_gates(skill_body: str) -> dict:
        """
        Split SKILL.md into sections by <!-- GATE:X --> markers.
        Returns {"preamble": str, "A": str, "B": str, "C": str}.
        preamble = everything before the first GATE marker.
        """
        parts = skill_body.split("<!-- GATE:")
        preamble = parts[0]
        gates: dict = {"preamble": preamble, "REPRODUCE": "", "RCA": ""}
        for part in parts[1:]:
            key, _, content = part.partition(" -->")
            key = key.strip()
            if key in gates:
                gates[key] = content.lstrip("\n")
        return gates

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _accumulate(self, session) -> None:
        self._tokens["input"] += session.token_usage.get("input", 0)
        self._tokens["output"] += session.token_usage.get("output", 0)

    @staticmethod
    def _log_gate(label: str, gate: GateResult) -> None:
        icon = "✅" if gate.passed else "❌"
        print(f"\n  🚦 Spawn gate ({label}): {icon} — {gate.reason}")
