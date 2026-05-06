# engine/orchestrator.py
"""
BugfixOrchestrator — Stage 5 Orchestrator-Worker 架構

設計原則：
  - Orchestrator 是 LLM Agent（有自己的 session、AGENTS.md、工具）
  - Judge Pattern：Python 執行各 phase，Orchestrator LLM 在每個 gate 做語義判斷
  - 資訊隔離：每個 subagent 只收到完成當前任務所需的最小 context
  - Progressive Disclosure (Gated Context Reveal)：
      Gate REPRODUCE → Step 0（能力前置 + 瀏覽器重現）
      Gate RCA       → Steps 1–5（根源分析 + 報告）
  - Orchestrator 在每個 gate 語義判斷：PROCEED / RETRY / NEED_MORE_INFO / CHECKPOINT
  - Outcome 追蹤：run() 回傳 "fixed" | "failed" | "skipped"
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .agent_runner import (
    create_session,
    run_in_session,
    ANALYZE_IMPLEMENT_TOOLS,
    TEST_TOOLS,
    ORCHESTRATOR_TOOLS,
)
from .config import ProjectConfig
from .tools import init_orchestrator_tools


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

        # Load Orchestrator AGENTS.md
        agents_path = agent_root / "agents" / "issue-fix" / "AGENTS.md"
        self._agents_md = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""

        # Init orchestrator tools context
        init_orchestrator_tools({
            "report_dir": self.report_dir,
            "agent_root": agent_root,
        })

    # ──────────────────────────────────────────
    # Public entry point
    # ──────────────────────────────────────────

    async def run(self, issue_id: str, issue_json: str, images: list | None = None) -> dict:
        print(f"\n{'═'*60}")
        print(f"  🎯 [Orchestrator] Issue: {issue_id}")
        print(f"{'═'*60}")

        # Create Orchestrator Agent session (stateful across all gates)
        _, orch_session = await create_session(ORCHESTRATOR_TOOLS)

        # Prime Orchestrator with AGENTS.md + issue context
        if self._agents_md:
            print("\n🤖 Initializing Orchestrator...")
            init_prompt = (
                f"{self._agents_md}\n\n"
                f"---\n\n"
                f"You are now managing issue **{issue_id}**.\n"
                f"You will be asked to make gate judgments as the fix progresses.\n"
                f"Reports are in: {self.report_dir / issue_id}/\n"
            )
            await run_in_session(orch_session, "orchestrate-init", init_prompt, max_tool_calls=0)

        # ── Analyze phase（Progressive Disclosure）──
        analyze_status = await self._run_analyze(issue_id, issue_json, images, orch_session)

        if analyze_status == "already_fixed":
            print("\n  ✅ Already fixed — no further action.")
            self._accumulate(orch_session)
            return {**self._tokens, "outcome": "skipped"}

        if analyze_status != "confirmed":
            print(f"\n  ⏸  Analyze ended with status={analyze_status}")
            self._accumulate(orch_session)
            return {**self._tokens, "outcome": "skipped"}

        # ── Gate 2: Orchestrator validates analyze.md quality ──
        quality_judgment = await self._judge(
            orch_session, "analyze-quality",
            f"## Gate 2: Analyze Quality\n\n"
            f"Issue: {issue_id}\n\n"
            f"Use `read_artifact` to read `analyze.md`, then judge its quality.\n"
            f"End your response with PROCEED, RETRY, or NEED_MORE_INFO.",
        )
        self._log_gate("analyze→implement", GateResult(
            passed="PROCEED" in quality_judgment.upper(),
            reason=quality_judgment[:200],
        ))
        if "PROCEED" not in quality_judgment.upper():
            print("  ⏸  Implement not spawned.")
            self._accumulate(orch_session)
            return {**self._tokens, "outcome": "skipped"}

        # ── Implement + Test loop ──
        for retry in range(MAX_IMPLEMENT_RETRIES + 1):
            await self._run_implement(issue_id, retry=retry)

            # Gate 3: Orchestrator validates implement alignment
            test_report_name = "test.md" if retry == 0 else f"test-retry-{retry}.md"
            align_judgment = await self._judge(
                orch_session, f"implement-align-{retry}",
                f"## Gate 3: Implement Alignment\n\n"
                f"Issue: {issue_id}, attempt {retry + 1}\n\n"
                f"Use `read_artifact` to read `analyze.md` and `implement.md`, "
                f"then judge alignment.\n"
                f"End your response with PROCEED, RETRY, or CHECKPOINT.",
            )
            self._log_gate("implement→test", GateResult(
                passed="PROCEED" in align_judgment.upper(),
                reason=align_judgment[:200],
            ))

            verdict = await self._run_test(issue_id, retry=retry, orch_session=orch_session)
            print(f"\n  ⚖️  Verdict: {verdict}")

            if verdict == "PASS":
                print(f"\n  ✅ Fix complete! Reports: {self.report_dir / issue_id}/")
                self._accumulate(orch_session)
                return {**self._tokens, "outcome": "fixed"}

            if retry < MAX_IMPLEMENT_RETRIES:
                # Gate 4: Orchestrator decides if retry is worthwhile
                timeout_note = ""
                if verdict == "TIMEOUT":
                    timeout_note = (
                        f"\n⚠️ Note: the test agent timed out before writing `{test_report_name}` "
                        f"(report file does not exist). This is a session timeout, not a test "
                        f"failure. Re-implementing is likely not the right action."
                    )
                retry_judgment = await self._judge(
                    orch_session, f"retry-decision-{retry}",
                    f"## Gate 4: Test Retry Decision\n\n"
                    f"Issue: {issue_id}, retry {retry + 1}/{MAX_IMPLEMENT_RETRIES}\n"
                    f"Test verdict: {verdict}{timeout_note}\n\n"
                    f"Use `read_artifact` to read `{test_report_name}`, then decide.\n"
                    f"End your response with **RETRY** or **NEED_MORE_INFO**.",
                )
                gate4_verdict = self._parse_verdict(retry_judgment, ["RETRY", "NEED_MORE_INFO"])
                if gate4_verdict != "RETRY":
                    print(f"\n  ⏸  Orchestrator: stop retrying — {retry_judgment[:100]}")
                    break
                print(f"\n  🔄 FAIL → re-implement ({retry + 1}/{MAX_IMPLEMENT_RETRIES})")
            else:
                print(f"\n  💀 Max retries ({MAX_IMPLEMENT_RETRIES}) reached.")

        self._accumulate(orch_session)
        return {**self._tokens, "outcome": "failed"}

    # ──────────────────────────────────────────
    # Orchestrator judgment helper
    # ──────────────────────────────────────────

    async def _judge(self, orch_session, gate_name: str, prompt: str) -> str:
        """Ask the Orchestrator LLM to make a semantic gate judgment."""
        return await run_in_session(
            orch_session, f"orchestrate-{gate_name}", prompt, max_tool_calls=3,
        )

    # ──────────────────────────────────────────
    # Analyze — Progressive Disclosure + Orchestrator gates
    # ──────────────────────────────────────────

    async def _run_analyze(
        self,
        issue_id: str,
        issue_json: str,
        images: list | None,
        orch_session,
    ) -> str:
        print(f"\n{'─'*60}")
        print("  [Orchestrator] Phase: analyze (Gated Reveal)")
        print(f"{'─'*60}")

        _, session = await create_session(ANALYZE_IMPLEMENT_TOOLS, mcp_manager=self.mcp_manager)
        screenshot_dir = (
            self.agent_root / "issues" / "screenshots"
            / self.config.get_project_key() / issue_id
        )

        # ── Gate REPRODUCE: Step 0 全部（能力前置 + 瀏覽器重現）──
        last_reproduce_judgment = ""
        for attempt in range(MAX_GATE_RETRIES + 1):
            if attempt == 0:
                prompt = self._build_reproduce_prompt(issue_id, issue_json, screenshot_dir)
                response = await run_in_session(
                    session, "analyze-reproduce", prompt,
                    max_tool_calls=35, images=images,
                    prompt_sources=[
                        "Project Context",
                        "skills/bugfix-analyze/SKILL.md [preamble + GATE: REPRODUCE]",
                        f"Issue: {issue_id}",
                        *(["+ attached image(s)"] if images else []),
                    ],
                )
            else:
                retry_msg = (
                    f"Orchestrator feedback on previous attempt:\n{last_reproduce_judgment}\n\n"
                    "Step 0 is not complete. Address the above feedback and retry Steps 0.2–0.5: "
                    "browser reproduction, screenshot saved to the specified directory."
                )
                response = await run_in_session(
                    session, f"analyze-reproduce-retry-{attempt}", retry_msg,
                    max_tool_calls=35,
                    prompt_sources=[
                        f"Orchestrator feedback (attempt {attempt})",
                        "skills/bugfix-analyze/SKILL.md [GATE: REPRODUCE — retry]",
                    ],
                )

            # Objective check first (no LLM needed for file existence)
            repro_ok = (screenshot_dir / "reproduction.png").exists()
            repro_fail_ok = (screenshot_dir / "reproduction-failed.png").exists()

            if repro_ok or repro_fail_ok:
                names = ", ".join(
                    f for f in ["reproduction.png", "reproduction-failed.png"]
                    if (screenshot_dir / f).exists()
                )
                print(f"\n  ✅ Reproduce gate: screenshot found ({names})")
                break

            # Semantic judgment: ask Orchestrator LLM
            judgment = await self._judge(
                orch_session, f"reproduce-gate-{attempt}",
                f"## Gate 1: REPRODUCE\n\n"
                f"Issue: {issue_id}, attempt {attempt + 1}/{MAX_GATE_RETRIES + 1}\n"
                f"reproduction.png: {'EXISTS' if repro_ok else 'not found'}\n"
                f"reproduction-failed.png: {'EXISTS' if repro_fail_ok else 'not found'}\n\n"
                f"Analyzer Step 0 response (last 1500 chars):\n```\n{response[-1500:]}\n```\n\n"
                f"Did Step 0 complete with concrete observations?\n"
                f"End your response with PROCEED, RETRY, or NEED_MORE_INFO.",
            )

            last_reproduce_judgment = judgment
            if "PROCEED" in judgment.upper():
                print(f"\n  ✅ Reproduce gate: Orchestrator — PROCEED")
                break
            if "NEED_MORE_INFO" in judgment.upper() or attempt >= MAX_GATE_RETRIES:
                print(f"\n  ⏸  Reproduce gate: Orchestrator — {judgment[:100]}")
                self._accumulate(session)
                return "need_more_info"
            print(f"\n  🔄 Reproduce gate: Orchestrator — RETRY ({attempt + 1}/{MAX_GATE_RETRIES})")

        # ── Gate RCA: Steps 1–5 + 報告 ──
        report_path = self.report_dir / issue_id / "analyze.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        rca_response = ""
        for attempt in range(2):
            rca_prompt = self._build_rca_prompt(issue_id, report_path)
            rca_response = await run_in_session(
                session, "analyze-rca", rca_prompt, max_tool_calls=40,
                prompt_sources=[
                    "skills/bugfix-analyze/SKILL.md [GATE: RCA]",
                    f"Issue: {issue_id} (REPRODUCE context carried from same session)",
                    f"→ analyze.md: {report_path}",
                ],
            )
            if report_path.exists():
                break
            if attempt == 0:
                print("\n  ⚠️  analyze.md not written — retrying RCA gate...")

        # Orchestrator judges RCA grounding (replaces Python 0-tool-call heuristic)
        last_tool_calls = getattr(session, "last_turn_tool_calls", -1)
        grounding_judgment = await self._judge(
            orch_session, "rca-grounding",
            f"## RCA Grounding Check\n\n"
            f"Issue: {issue_id}\n"
            f"Tool calls in last RCA turn: {last_tool_calls}\n"
            f"RCA response length: {len(rca_response)} chars\n\n"
            f"Was the RCA grounded (agent actually read code files)?\n"
            f"End your response with GROUNDED or NEEDS_REGROUNDING.",
        )

        if "NEEDS_REGROUNDING" in grounding_judgment.upper():
            print("\n  ⚠️  [Orchestrator] RCA not grounded — re-running with explicit tool instruction...")
            grounded_prompt = (
                "你剛才的 RCA 分析沒有呼叫任何工具。\n"
                "**必須先使用 search_files / read_file 工具實際讀取相關程式碼**，再覆蓋寫入 analyze.md。\n"
                "不要依賴記憶或推斷，直接查看程式碼後再分析。\n\n"
                f"Target project root: {self.project_root}\n"
                f"Write analysis report to: {report_path}\n"
                f"Issue ID: {issue_id}\n"
            )
            await run_in_session(
                session, "analyze-rca-grounded", grounded_prompt, max_tool_calls=30,
                prompt_sources=["Orchestrator grounding feedback (re-run with explicit tool instruction)"],
            )

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
        print(f"  [Orchestrator] Phase: {label}")
        print(f"{'─'*60}")

        analyze_path = self.report_dir / issue_id / "analyze.md"
        implement_path = self.report_dir / issue_id / "implement.md"
        _, session = await create_session(ANALYZE_IMPLEMENT_TOOLS)
        prompt = self._build_implement_prompt(issue_id, retry=retry)
        sources = [
            "Project Context",
            "skills/bugfix-implement/SKILL.md",
            f"← {analyze_path}",
            f"→ {implement_path}",
        ]
        if retry > 0:
            prev_test = "test.md" if retry == 1 else f"test-retry-{retry - 1}.md"
            sources.insert(2, f"← {self.report_dir / issue_id / prev_test} (failure context)")
        await run_in_session(session, label, prompt, max_tool_calls=30, prompt_sources=sources)
        self._accumulate(session)

    # ──────────────────────────────────────────
    # Test phase
    # ──────────────────────────────────────────

    async def _run_test(self, issue_id: str, retry: int = 0, orch_session=None) -> str:
        label = f"test{f'-retry-{retry}' if retry > 0 else ''}"
        report_name = "test.md" if retry == 0 else f"test-retry-{retry}.md"
        print(f"\n{'─'*60}")
        print(f"  [Orchestrator] Phase: {label}")
        print(f"{'─'*60}")

        analyze_path = self.report_dir / issue_id / "analyze.md"
        implement_path = self.report_dir / issue_id / "implement.md"
        _, session = await create_session(TEST_TOOLS)
        prompt = self._build_test_prompt(issue_id, retry=retry)
        await run_in_session(
            session, label, prompt, max_tool_calls=40,
            prompt_sources=[
                "Project Context",
                "skills/bugfix-test/SKILL.md",
                f"← {analyze_path}",
                f"← {implement_path}",
                f"→ {self.report_dir / issue_id / report_name}",
            ],
        )

        verdict = self._read_test_verdict(issue_id, retry)

        # Gate 5: Orchestrator verifies all required phases are documented (only on PASS)
        if verdict == "PASS" and orch_session is not None:
            completeness = await self._judge(
                orch_session, f"test-completeness-{retry}",
                f"## Gate 5: Test Completeness\n\n"
                f"Issue: {issue_id}\n\n"
                f"Use `read_artifact` to read `{report_name}`, then verify that ALL required "
                f"verification phases were completed and their results documented:\n\n"
                f"1. **TypeScript static check** — result must be documented (PASS or FAIL)\n"
                f"2. **ESLint check** — result must be documented (PASS or FAIL)\n"
                f"3. **Behavior validation (Playwright)** — either results are documented, "
                f"OR an explicit SKIPPED with valid reason (config disabled / non-visual fix)\n"
                f"4. **Logic review** — fix strategy compliance must be assessed\n\n"
                f"If any required phase is missing or undocumented, end with INCOMPLETE "
                f"and name the missing phases.\n"
                f"If all required phases are present, end with COMPLETE.",
            )
            if "INCOMPLETE" in completeness.upper():
                print(f"\n  ⚠️  [Orchestrator] Test incomplete — requesting missing phases...")
                followup = (
                    f"Orchestrator review: your verification report is incomplete.\n\n"
                    f"{completeness}\n\n"
                    f"Complete all missing verification phases, update `{report_name}` "
                    f"with the full results, and update the **Verdict** field accordingly."
                )
                await run_in_session(
                    session, f"test-complete-{retry}", followup, max_tool_calls=20,
                    prompt_sources=["Orchestrator completeness feedback (same session — fill missing phases)"],
                )
                verdict = self._read_test_verdict(issue_id, retry)

        self._accumulate(session)
        return verdict

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
    # Report readers (structured Python checks)
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
            # File not written means the test agent was killed mid-run (idle timeout).
            # Return TIMEOUT so the caller can distinguish this from a genuine test failure.
            return "TIMEOUT"
        text = report.read_text(encoding="utf-8")
        m = re.search(r'\*\*Verdict\*\*[:\s]+\**\s*(PASS|FAIL)\**', text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        return "PASS" if "PASS" in text.upper() and "FAIL" not in text.upper() else "FAIL"

    @staticmethod
    def _parse_verdict(response: str, keywords: list[str]) -> str | None:
        """
        Extract the final gate verdict from an LLM response.

        Looks for **Verdict: KEYWORD** or standalone **KEYWORD** bold patterns.
        Using the *last* match avoids false positives from prose that references
        earlier verdict keywords (e.g. "retry 2/3", "make a retry decision").
        Falls back to scanning the last 5 non-empty lines for a bare keyword.
        """
        pattern = r'\*\*(?:Verdict[:\s]+)?(' + '|'.join(re.escape(k) for k in keywords) + r')\*\*'
        matches = re.findall(pattern, response, re.IGNORECASE)
        if matches:
            return matches[-1].upper()

        # Fallback: last 5 non-empty lines, stripped of markdown decoration
        lines = [l.strip() for l in response.strip().split('\n') if l.strip()]
        for line in reversed(lines[-5:]):
            clean = re.sub(r'[*_#>\-]', '', line).strip().upper()
            for kw in keywords:
                if clean == kw.upper():
                    return kw.upper()
        return None

    # ──────────────────────────────────────────
    # SKILL.md gate parser
    # ──────────────────────────────────────────

    @staticmethod
    def _parse_gates(skill_body: str) -> dict:
        """
        Split SKILL.md into sections by <!-- GATE:X --> markers.
        Returns {"preamble": str, "REPRODUCE": str, "RCA": str}.
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

    def _accumulate(self, *sessions) -> None:
        for session in sessions:
            self._tokens["input"] += session.token_usage.get("input", 0)
            self._tokens["output"] += session.token_usage.get("output", 0)

    @staticmethod
    def _log_gate(label: str, gate: GateResult) -> None:
        icon = "✅" if gate.passed else "❌"
        print(f"\n  🚦 [Orchestrator] Gate ({label}): {icon} — {gate.reason}")
