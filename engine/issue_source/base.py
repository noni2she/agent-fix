"""
Issue Source Adapter 基礎介面
使用者可實作此介面以支援自訂 issue 來源（如 Jira、GitHub Issues、Linear 等）
"""
from abc import ABC, abstractmethod


class IssueSourceAdapter(ABC):
    """
    Issue 來源 Adapter 基礎介面

    使用方式：
        繼承此類別並實作 fetch() 方法，即可接入任意 issue 管理系統。

    範例（自訂 GitHub Issues Adapter）：
        class GitHubIssuesAdapter(IssueSourceAdapter):
            def __init__(self, repo: str, token: str):
                self.repo = repo
                self.token = token

            def fetch(self, issue_id: str) -> dict:
                # 從 GitHub API 取得 issue
                ...
                return { "issue_id": issue_id, "summary": ..., ... }

            def validate(self) -> None:
                if not self.token:
                    raise IssueSourceConfigError("GITHUB_TOKEN is required")
    """

    @abstractmethod
    def fetch(self, issue_id: str) -> dict:
        """
        取得 issue 資料，回傳標準化的 issue dict

        Args:
            issue_id: Issue ID（如 MORSE-1234、BUG-001）

        Returns:
            標準化 issue dict，建議包含以下欄位：
            - issue_id (str): Issue ID
            - summary (str): 問題標題
            - description (str): 問題描述
            - reproduction_steps (list[str], optional): 重現步驟
            - expected (str, optional): 預期行為
            - actual (str, optional): 實際行為
            - module (str, optional): 問題所在模組
            - attachments (list, optional): 附件

        Raises:
            IssueNotFoundError: Issue 不存在
            IssueSourceError: 來源存取失敗（網路錯誤、權限問題等）
        """
        pass

    def validate(self) -> None:
        """
        驗證 adapter 配置是否正確（環境變數、連線資訊等）
        子類別可覆寫此方法加入配置驗證邏輯。

        Raises:
            IssueSourceConfigError: 配置不正確
        """
        pass


class IssueNotFoundError(Exception):
    """Issue 不存在於來源"""
    pass


class IssueSourceError(Exception):
    """Issue 來源存取失敗（網路、權限等）"""
    pass


class IssueSourceConfigError(Exception):
    """Issue 來源配置錯誤（缺少環境變數等）"""
    pass
