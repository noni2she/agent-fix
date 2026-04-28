"""
Issue Source Adapter 模組

支援的 Adapter：
    - LocalJsonAdapter:    從本地 JSON 檔案讀取（預設）
    - JiraAdapter:         從 Jira REST API v3 取得（需設定環境變數）
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
        config: IssueSourceConfig 實例，或 None（使用預設 local_json）

    Returns:
        IssueSourceAdapter 實例
    """
    if config is None or config.type == "local_json":
        opts = config.options if config and config.options else {}
        return LocalJsonAdapter(
            sources_dir=opts.get("sources_dir", "issues/sources"),
            video_max_frames=int(opts.get("video_max_frames", 8)),
        )

    if config.type == "jira":
        opts = config.options or {}
        return JiraAdapter(
            base_url=opts.get("base_url"),
            user_email=opts.get("user_email"),
            api_token=opts.get("api_token"),
            jql_base=opts.get("jql_base"),
            video_max_frames=int(opts.get("video_max_frames", 8)),
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
        f"Unknown issue source type: '{config.type}'.\n"
        f"Supported types: local_json, jira, google_sheets\n"
        f"For other custom adapters, implement IssueSourceAdapter "
        f"and instantiate it directly."
    )
