"""
Jira Issue Source Adapter
從 Jira REST API v3 取得 issue 資料

所需環境變數：
    JIRA_BASE_URL    — Jira base URL（如 https://your-company.atlassian.net）
    JIRA_USER_EMAIL  — Jira 帳號 email
    JIRA_API_TOKEN   — Jira API Token
                       （至 https://id.atlassian.com/manage-profile/security/api-tokens 建立）
"""
import json
import os
from base64 import b64encode
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import (
    IssueSourceAdapter,
    IssueNotFoundError,
    IssueSourceError,
    IssueSourceConfigError,
)


class JiraAdapter(IssueSourceAdapter):
    """
    Jira REST API v3 Adapter

    回傳 Jira raw JSON，不做格式轉換，由 AI agent 直接解讀。
    關鍵欄位：
        fields.summary          — 標題
        fields.description      — 詳細描述（ADF 格式，遞迴提取文字）
        fields.comment.comments — 討論串
        fields.attachment       — 附件（含 content URL）
        fields.issuelinks       — 關聯 issue
        fields.priority / labels / components
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        user_email: Optional[str] = None,
        api_token: Optional[str] = None,
        jql_base: Optional[str] = None,
    ):
        """
        Args:
            base_url:    Jira base URL，若未傳入則從 JIRA_BASE_URL 環境變數讀取
            user_email:  Jira 帳號 email，若未傳入則從 JIRA_USER_EMAIL 讀取
            api_token:   Jira API Token，若未傳入則從 JIRA_API_TOKEN 讀取
        """
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.user_email = user_email or os.getenv("JIRA_USER_EMAIL", "")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self.jql_base = jql_base or ""

    def validate(self) -> None:
        """
        驗證必要的環境變數是否齊全

        Raises:
            IssueSourceConfigError: 缺少必要環境變數
        """
        missing = []
        if not self.base_url:
            missing.append("JIRA_BASE_URL")
        if not self.user_email:
            missing.append("JIRA_USER_EMAIL")
        if not self.api_token:
            missing.append("JIRA_API_TOKEN")

        if missing:
            raise IssueSourceConfigError(
                f"Missing required environment variables for Jira adapter: "
                f"{', '.join(missing)}\n"
                f"Please set them in .env.local or export them before running.\n"
                f"See .env.example for reference."
            )

    def _auth_header(self) -> str:
        return "Basic " + b64encode(
            f"{self.user_email}:{self.api_token}".encode()
        ).decode()

    def _get(self, path: str, params: dict | None = None) -> dict:
        """共用 GET helper，回傳解析後的 JSON dict。"""
        from urllib.parse import urlencode
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={
            "Authorization": self._auth_header(),
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            raise IssueSourceError(
                f"Jira API HTTP {e.code}: {url}\n{body}"
            )
        except URLError as e:
            raise IssueSourceError(
                f"Failed to connect to Jira: {e.reason}\nURL: {url}"
            )

    def list_all(self, filter: str | None = None) -> list[str]:
        """
        透過 JQL 查詢 Jira，回傳符合條件的 issue key 列表。

        最終 JQL = jql_base（config.yaml）AND filter（--filter 參數，可選）

        Args:
            filter: 額外 JQL 條件，與 jql_base AND 串接

        Returns:
            issue key 列表（如 ["MORSE-1", "MORSE-2"]）
        """
        if not self.jql_base and not filter:
            raise IssueSourceError(
                "jira batch 需要 JQL 查詢條件。\n"
                "請在 config.yaml 設定 issue_source.options.jql_base，\n"
                "或使用 --filter 傳入 JQL 條件。"
            )

        parts = [p for p in [self.jql_base, filter] if p]
        jql = " AND ".join(parts)

        print(f"🔍 Jira JQL: {jql}")

        issue_keys: list[str] = []
        start_at = 0
        max_results = 100

        while True:
            data = self._get("/rest/api/3/search", {
                "jql": jql,
                "fields": "key",
                "startAt": start_at,
                "maxResults": max_results,
            })
            issues = data.get("issues", [])
            issue_keys.extend(issue["key"] for issue in issues)

            total = data.get("total", 0)
            start_at += len(issues)
            if start_at >= total or not issues:
                break

        print(f"   ✅ {len(issue_keys)} issues found")
        return issue_keys

    def fetch(self, issue_id: str) -> dict:
        """
        從 Jira REST API v3 取得 issue raw JSON

        Args:
            issue_id: Jira Issue key（如 MORSE-1234）

        Returns:
            Jira API 原始回應（dict），保留完整欄位供 AI agent 解讀

        Raises:
            IssueNotFoundError: Issue 不存在（HTTP 404）
            IssueSourceError:   API 呼叫失敗
        """
        try:
            data = self._get(f"/rest/api/3/issue/{issue_id}")
            data["issue_id"] = issue_id
            return data
        except IssueSourceError as e:
            if "HTTP 404" in str(e):
                raise IssueNotFoundError(
                    f"Issue '{issue_id}' not found on Jira.\n"
                    f"URL: {self.base_url}/rest/api/3/issue/{issue_id}"
                )
            raise
