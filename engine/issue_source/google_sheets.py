"""
Google Sheets Adapter — 從 Google Sheets 批次讀取 Issues
直接讀取試算表並以記憶體快取，不寫入本地 JSON。

Config 範例 (config.yaml):
    issue_source:
      type: google_sheets
      options:
        sheet_url: "https://docs.google.com/spreadsheets/d/SHEET_ID/..."
        credentials_file: "./service_account.json"   # service account 認證
        worksheet: "Sheet1"                           # 可選，預設第一個工作表

欄位對應（試算表標題列）：
    必要：issue_id（或 id / ID）
    可選：summary, description, reproduction_steps, expected, actual, module
          status（skip rows where status == "done" / "closed" / "fixed"）

環境變數（service account 替代方案）：
    GOOGLE_CREDENTIALS_FILE=./service_account.json
    GOOGLE_API_KEY=AIza...   # 僅限公開試算表的讀取
"""
import os
from .base import IssueSourceAdapter, IssueNotFoundError, IssueSourceError, IssueSourceConfigError


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
    "Expected": "expected",
    "Actual": "actual",
    "Module": "module",
}

_SKIP_STATUSES = {"done", "closed", "fixed", "resolved", "完成", "已關閉"}


class GoogleSheetsAdapter(IssueSourceAdapter):
    """
    Google Sheets Adapter（純記憶體快取，不寫入本地檔案）

    list_all() 讀取試算表並快取所有列，fetch() 直接從快取回傳。
    """

    def __init__(
        self,
        sheet_url: str,
        credentials_file: str | None = None,
        api_key: str | None = None,
        worksheet: str | None = None,
    ):
        self.sheet_url = sheet_url
        self.credentials_file = credentials_file or os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.worksheet_name = worksheet
        self._cache: dict[str, dict] = {}

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
                "  Install with: uv tool install --editable '.[copilot,sheets]'"
            )

    def _open_worksheet(self):
        import gspread
        if self.credentials_file:
            gc = gspread.service_account(filename=self.credentials_file)
        else:
            gc = gspread.api_key(self.api_key)
        spreadsheet = gc.open_by_url(self.sheet_url)
        return spreadsheet.worksheet(self.worksheet_name) if self.worksheet_name else spreadsheet.sheet1

    def _normalize_row(self, headers: list[str], row: list[str]) -> dict:
        data = {}
        for header, value in zip(headers, row):
            key = _COLUMN_ALIASES.get(header, header.lower().replace(" ", "_"))
            if key == "reproduction_steps" and isinstance(value, str) and value:
                data[key] = [s.strip() for s in value.split("\n") if s.strip()] or [value]
            else:
                data[key] = value
        return data

    def _load(self) -> None:
        """從試算表讀取所有列，填入 self._cache。"""
        try:
            ws = self._open_worksheet()
            records = ws.get_all_values()
        except Exception as e:
            raise IssueSourceError(f"google_sheets: failed to read worksheet: {e}") from e

        if not records:
            return

        headers = records[0]
        for row_values in records[1:]:
            if not any(row_values):
                continue
            data = self._normalize_row(headers, row_values)
            status = str(data.get("status", "")).strip().lower()
            if status in _SKIP_STATUSES:
                continue
            issue_id = str(data.get("issue_id", "")).strip()
            if not issue_id:
                continue
            data["issue_id"] = issue_id
            self._cache[issue_id] = data

    def list_all(self, filter: str | None = None) -> list[str]:
        """讀取試算表、快取所有 issues，回傳 issue ID 列表。
        filter 參數由呼叫端（command_batch）做 fnmatch 處理，此處忽略。"""
        print("📊 Reading issues from Google Sheets...")
        self._cache.clear()
        self._load()
        print(f"   ✅ {len(self._cache)} issues loaded")
        return sorted(self._cache.keys())

    def fetch(self, issue_id: str) -> dict:
        """從記憶體快取回傳 issue，若快取為空先載入一次。"""
        if not self._cache:
            self._load()
        if issue_id not in self._cache:
            raise IssueNotFoundError(
                f"Issue '{issue_id}' not found in Google Sheets.\n"
                f"Sheet URL: {self.sheet_url}"
            )
        return self._cache[issue_id]
