"""
Google Sheets Adapter — 從 Google Sheets 批次讀取 Issues
將試算表每一列轉換成 issues/sources/<issue_id>.json，再交由 LocalJsonAdapter 讀取。

Config 範例 (config.yaml):
    issue_source:
      type: google_sheets
      options:
        sheet_url: "https://docs.google.com/spreadsheets/d/SHEET_ID/..."
        credentials_file: "./service_account.json"   # service account 認證
        worksheet: "Sheet1"                           # 可選，預設第一個工作表
        sources_dir: "issues/sources"                 # 可選，輸出目錄

欄位對應（試算表標題列）：
    必要：issue_id（或 id / ID）
    可選：summary, description, reproduction_steps, expected, actual, module
          status（skip rows where status == "done" or "closed"）

環境變數（service account 替代方案）：
    GOOGLE_CREDENTIALS_FILE=./service_account.json
    GOOGLE_API_KEY=AIza...   # 僅限公開試算表的讀取
"""
import json
import os
from pathlib import Path

from .base import IssueSourceAdapter, IssueNotFoundError, IssueSourceError, IssueSourceConfigError
from .local_json import LocalJsonAdapter


# 試算表欄位 → issue schema 的欄位別名
_COLUMN_ALIASES: dict[str, str] = {
    "id": "issue_id",
    "ID": "issue_id",
    "issue id": "issue_id",
    "Issue ID": "issue_id",
    "title": "summary",
    "Title": "summary",
    "Summary": "summary",
    "desc": "description",
    "Description": "description",
    "steps": "reproduction_steps",
    "reproduction steps": "reproduction_steps",
    "Reproduction Steps": "reproduction_steps",
    "expected": "expected",
    "Expected": "expected",
    "actual": "actual",
    "Actual": "actual",
    "module": "module",
    "Module": "module",
}

_SKIP_STATUSES = {"done", "closed", "fixed", "resolved", "完成", "已關閉"}


class GoogleSheetsAdapter(IssueSourceAdapter):
    """
    Google Sheets Adapter

    將試算表每一列轉換成 local JSON 檔案後，透過 LocalJsonAdapter 讀取。
    list_all() 執行同步（下載+寫檔），fetch() 直接讀本地 JSON。
    """

    def __init__(
        self,
        sheet_url: str,
        credentials_file: str | None = None,
        api_key: str | None = None,
        worksheet: str | None = None,
        sources_dir: str = "issues/sources",
    ):
        """
        Args:
            sheet_url:        Google Sheets URL（含 /d/SHEET_ID/）
            credentials_file: service account JSON 路徑（優先於 api_key）
            api_key:          Google API key（公開試算表唯讀）
            worksheet:        工作表名稱（None = 第一個）
            sources_dir:      local JSON 輸出目錄
        """
        self.sheet_url = sheet_url
        self.credentials_file = credentials_file or os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.worksheet_name = worksheet
        self.sources_dir = Path(sources_dir)
        self._local = LocalJsonAdapter(sources_dir=sources_dir)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        if not self.sheet_url:
            raise IssueSourceConfigError("google_sheets: sheet_url is required")
        if not self.credentials_file and not self.api_key:
            raise IssueSourceConfigError(
                "google_sheets: either credentials_file or GOOGLE_API_KEY is required.\n"
                "  Service account: set credentials_file in config.yaml\n"
                "  API key (public sheets): export GOOGLE_API_KEY=AIza..."
            )
        try:
            import gspread  # noqa: F401
        except ImportError:
            raise IssueSourceConfigError(
                "google_sheets: gspread is not installed.\n"
                "  Install with: pip install 'agent-fix[sheets]'"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_worksheet(self):
        """連線並回傳 gspread Worksheet。"""
        import gspread

        if self.credentials_file:
            gc = gspread.service_account(filename=self.credentials_file)
        else:
            gc = gspread.api_key(self.api_key)

        spreadsheet = gc.open_by_url(self.sheet_url)
        if self.worksheet_name:
            return spreadsheet.worksheet(self.worksheet_name)
        return spreadsheet.sheet1

    def _normalize_row(self, headers: list[str], row: list[str]) -> dict:
        """將一列資料轉成 issue dict（套用欄位別名對映）。"""
        data = {}
        for header, value in zip(headers, row):
            key = _COLUMN_ALIASES.get(header, header.lower().replace(" ", "_"))
            # reproduction_steps: 若為逗號分隔字串則轉成 list
            if key == "reproduction_steps" and isinstance(value, str) and value:
                data[key] = [s.strip() for s in value.split("\n") if s.strip()] or [value]
            else:
                data[key] = value
        return data

    def _sync_to_local(self) -> list[str]:
        """
        從試算表讀取所有列，寫入 issues/sources/<issue_id>.json。
        回傳已寫入的 issue ID 列表。
        """
        self.sources_dir.mkdir(parents=True, exist_ok=True)

        try:
            ws = self._open_worksheet()
            records = ws.get_all_values()
        except Exception as e:
            raise IssueSourceError(f"google_sheets: failed to read worksheet: {e}") from e

        if not records:
            return []

        headers = records[0]
        issue_ids: list[str] = []

        for row_values in records[1:]:
            if not any(row_values):
                continue

            data = self._normalize_row(headers, row_values)

            # skip 已完成的 issue
            status = str(data.get("status", "")).strip().lower()
            if status in _SKIP_STATUSES:
                continue

            issue_id = str(data.get("issue_id", "")).strip()
            if not issue_id:
                continue

            data["issue_id"] = issue_id
            out_file = self.sources_dir / f"{issue_id}.json"
            out_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            issue_ids.append(issue_id)

        return issue_ids

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_all(self) -> list[str]:
        """
        同步試算表 → 寫入 local JSON → 回傳 issue ID 列表。
        已存在的 JSON 會被覆寫（以試算表為主）。
        """
        print("📊 Syncing issues from Google Sheets...")
        ids = self._sync_to_local()
        print(f"   ✅ {len(ids)} issues synced to {self.sources_dir}/")
        return sorted(ids)

    def fetch(self, issue_id: str) -> dict:
        """
        讀取 list_all() 已寫入的 local JSON。
        若檔案不存在，先嘗試同步一次。
        """
        try:
            return self._local.fetch(issue_id)
        except IssueNotFoundError:
            # 可能未執行 list_all()，嘗試同步後再讀
            self._sync_to_local()
            return self._local.fetch(issue_id)
