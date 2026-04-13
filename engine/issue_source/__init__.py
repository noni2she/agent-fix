"""
Issue Source Adapter 模組

內建 Adapter：
    - LocalJsonAdapter: 從本地 JSON 檔案讀取（預設）

自訂 Adapter：
    繼承 IssueSourceAdapter 並實作 fetch() 方法，
    再透過 config.issue_source.type 指定使用。
"""
from .base import (
    IssueSourceAdapter,
    IssueNotFoundError,
    IssueSourceError,
    IssueSourceConfigError,
)
from .local_json import LocalJsonAdapter

__all__ = [
    "IssueSourceAdapter",
    "IssueNotFoundError",
    "IssueSourceError",
    "IssueSourceConfigError",
    "LocalJsonAdapter",
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
                   （自訂 adapter 請直接實例化後傳入，不經由此函式）
    """
    if config is None or config.type == "local_json":
        sources_dir = "issues/sources"
        if config and config.options:
            sources_dir = config.options.get("sources_dir", sources_dir)
        return LocalJsonAdapter(sources_dir=sources_dir)

    raise ValueError(
        f"Unknown built-in issue source type: '{config.type}'.\n"
        f"Built-in types: local_json\n"
        f"For custom adapters (e.g. Jira, GitHub Issues), implement "
        f"IssueSourceAdapter and instantiate it directly."
    )
