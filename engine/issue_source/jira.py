"""
Jira Issue Source Adapter
支援 Jira Cloud（Basic Auth）與 Jira Server 自建版（Session Auth）

所需環境變數：
    JIRA_BASE_URL      — Jira base URL
                         Cloud: https://your-company.atlassian.net
                         Server: https://jira.your-company.com
    JIRA_USER_EMAIL    — Jira 帳號
                         Cloud: email（如 user@company.com）
                         Server: username（如 bryce_ni）
    JIRA_API_TOKEN     — 認證憑證
                         Cloud: API Token（至 https://id.atlassian.com/manage-profile/security/api-tokens 建立）
                         Server: LDAP/AD 登入密碼（Jira Server 不支援 API Token）

選用環境變數：
    JIRA_AUTH_MODE     — 認證模式（預設: basic）
                         basic   → Basic Auth，適用 Jira Cloud
                         session → Session Auth，適用 Jira Server（LDAP/AD）
    JIRA_SSL_VERIFY    — SSL 憑證驗證（預設: true）
                         false → 停用驗證，適用自簽憑證的內部 Jira Server
"""
import json
import os
import ssl
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
    Jira Adapter — 同時支援 Jira Cloud 與 Jira Server 自建版。

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
        auth_mode: Optional[str] = None,
    ):
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.user_email = user_email or os.getenv("JIRA_USER_EMAIL", "")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self.jql_base = jql_base or ""
        self.auth_mode = (auth_mode or os.getenv("JIRA_AUTH_MODE", "basic")).lower()
        self._session_cookie: str | None = None

    def validate(self) -> None:
        """
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

        if self.auth_mode not in ("basic", "session"):
            raise IssueSourceConfigError(
                f"Invalid JIRA_AUTH_MODE='{self.auth_mode}'. Must be 'basic' or 'session'."
            )

    def _ssl_context(self):
        if os.getenv("JIRA_SSL_VERIFY", "true").lower() == "false":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return None

    def _login(self) -> str:
        """POST /rest/auth/1/session 換取 JSESSIONID（Session Auth，適用 Jira Server）。"""
        import json as _json
        url = f"{self.base_url}/rest/auth/1/session"
        body = _json.dumps({"username": self.user_email, "password": self.api_token}).encode()
        request = Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",
        })
        try:
            with urlopen(request, timeout=30, context=self._ssl_context()) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                session = data.get("session", {})
                return f"{session['name']}={session['value']}"
        except HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")
            except Exception:
                pass
            raise IssueSourceConfigError(
                f"Jira session login failed (HTTP {e.code}). "
                f"Check JIRA_USER_EMAIL and JIRA_API_TOKEN.\n{body_text}"
            )

    def _get(self, path: str, params: dict | None = None) -> dict:
        """共用 GET helper，根據 JIRA_AUTH_MODE 選擇 Basic Auth 或 Session Auth。"""
        from urllib.parse import urlencode
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urlencode(params)

        if self.auth_mode == "session":
            if self._session_cookie is None:
                self._session_cookie = self._login()
            headers = {
                "Cookie": self._session_cookie,
                "Accept": "application/json",
            }
        else:
            headers = {
                "Authorization": "Basic " + b64encode(
                    f"{self.user_email}:{self.api_token}".encode()
                ).decode(),
                "Accept": "application/json",
            }

        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30, context=self._ssl_context()) as resp:
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
            issue key 列表（如 ["PROJ-1", "PROJ-2"]）
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
            data = self._get("/rest/api/2/search", {
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

    @staticmethod
    def _strip_fields(obj):
        """遞迴移除 null 值，以及無意義的 customfield（全 null 或純噪音）。"""
        _NOISE_FIELDS = {
            "expand", "self",
            "customfield_10000",   # dev summary（超長 Java toString 字串）
            "customfield_10818",   # HTML button（複製按鈕）
            "customfield_10819",   # HTML button（複製時間）
        }
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if v is None:
                    continue
                if k in _NOISE_FIELDS:
                    continue
                stripped = JiraAdapter._strip_fields(v)
                if stripped == {} or stripped == []:
                    continue
                result[k] = stripped
            return result
        if isinstance(obj, list):
            return [JiraAdapter._strip_fields(i) for i in obj if i is not None]
        return obj

    def fetch(self, issue_id: str) -> dict:
        """
        從 Jira REST API 取得 issue raw JSON，自動過濾 null 欄位與噪音。

        Args:
            issue_id: Jira Issue key（如 PROJ-1234）

        Returns:
            Jira API 回應（dict），null 欄位已移除，保留有效欄位供 AI agent 解讀

        Raises:
            IssueNotFoundError: Issue 不存在（HTTP 404）
            IssueSourceError:   API 呼叫失敗
        """
        try:
            data = self._get(f"/rest/api/2/issue/{issue_id}")
            data = self._strip_fields(data)
            data["issue_id"] = issue_id
            return data
        except IssueSourceError as e:
            if "HTTP 404" in str(e):
                raise IssueNotFoundError(
                    f"Issue '{issue_id}' not found on Jira.\n"
                    f"URL: {self.base_url}/rest/api/2/issue/{issue_id}"
                )
            raise
