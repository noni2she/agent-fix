"""
Issue Source Adapter 模組

內建 Adapter：
    - LocalJsonAdapter:    從本地 JSON 檔案讀取（預設）
    - JiraAdapter:         從 Jira REST API v3 取得
    - GoogleSheetsAdapter: 從 Google Sheets 批次讀取

自訂 Adapter：
    繼承 IssueSourceAdapter 並實作 fetch() / list_all() 方法，
    再透過 config.issue_source.type 指定使用。
"""
from .base import (
    IssueSourceAdapter,
    IssueNotFoundError,
    IssueSourceError,
    IssueSourceConfigError,
)
from .local_json import LocalJsonAdapter
from .jira import JiraAdapter
from .google_sheets import GoogleSheetsAdapter

__all__ = [
    "IssueSourceAdapter",
    "IssueNotFoundError",
    "IssueSourceError",
    "IssueSourceConfigError",
    "LocalJsonAdapter",
    "JiraAdapter",
    "GoogleSheetsAdapter",
    "create_adapter",
]


def create_adapter(config) -> IssueSourceAdapter:
    """
    根據 IssueSourceConfig 建立對應的 adapter 實例

    Args:
        config: IssueSourceConfig 實例，或 None（使用預設）

    Returns:
        IssueSourceAdapter 實例

    Raises:
        ValueError: 指定的 type 不是內建支援的類型
    """
    if config is None or config.type == "local_json":
        sources_dir = "issues/sources"
        if config and config.options:
            sources_dir = config.options.get("sources_dir", sources_dir)
        return LocalJsonAdapter(sources_dir=sources_dir)

    if config.type == "jira":
        opts = config.options or {}
        return JiraAdapter(
            base_url=opts.get("base_url"),
            user_email=opts.get("user_email"),
            api_token=opts.get("api_token"),
            jql_base=opts.get("jql_base"),
        )

    if config.type == "google_sheets":
        opts = config.options or {}
        return GoogleSheetsAdapter(
            sheet_url=opts.get("sheet_url", ""),
            credentials_file=opts.get("credentials_file"),
            api_key=opts.get("api_key"),
            worksheet=opts.get("worksheet"),
        )

    raise ValueError(
        f"Unknown built-in issue source type: '{config.type}'.\n"
        f"Built-in types: local_json, jira, google_sheets\n"
        f"For custom adapters, implement IssueSourceAdapter and instantiate it directly."
    )
