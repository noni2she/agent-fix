"""
Local JSON Adapter — 內建預設 Issue 來源
從 issues/sources/<issue_id>.json 讀取本地 JSON 檔案
"""
import base64
import json
from pathlib import Path

from .base import IssueSourceAdapter, IssueNotFoundError, IssueSourceError
from .attachment_utils import (
    video_to_frames,
    DEFAULT_VIDEO_MAX_FRAMES,
    _IMAGE_EXTENSIONS,
    _VIDEO_EXTENSIONS,
    _MIME_MAP,
)


def _load_local_attachments(attachments: list, base_dir: Path,
                             max_video_frames: int = DEFAULT_VIDEO_MAX_FRAMES) -> list[dict]:
    """attachments 欄位中的圖片/影片讀成 base64，回傳標準 _images 格式。"""
    images = []
    for att in attachments:
        path_str = att.get("path", "")
        if not path_str:
            continue
        p = Path(path_str)
        if not p.is_absolute():
            p = base_dir / p
        if not p.exists():
            continue
        ext = p.suffix.lower()
        try:
            if ext in _IMAGE_EXTENSIONS:
                data = base64.b64encode(p.read_bytes()).decode("ascii")
                images.append({
                    "data": data,
                    "mime_type": _MIME_MAP.get(ext, "image/png"),
                    "name": p.name,
                })
            elif ext in _VIDEO_EXTENSIONS:
                frames = video_to_frames(p.read_bytes(), max_frames=max_video_frames)
                if frames:
                    print(f"   🎬 影片 {p.name}：截取 {len(frames)} frames")
                images.extend(frames)
        except Exception:
            pass
    return images


class LocalJsonAdapter(IssueSourceAdapter):
    """
    本地 JSON 檔案 Adapter（內建預設）

    從 issues/sources/<issue_id>.json 讀取 issue 資料。
    不依賴任何外部服務，適合手動建立 issue 或作為其他 adapter 的 fallback。

    JSON 格式參考 issues/TEMPLATE.json。
    """

    def __init__(self, sources_dir: str = "issues/sources",
                 video_max_frames: int = DEFAULT_VIDEO_MAX_FRAMES):
        """
        Args:
            sources_dir: issue JSON 檔案所在目錄（相對於執行位置）
        """
        self.sources_dir = Path(sources_dir)
        self.video_max_frames = video_max_frames

    def fetch(self, issue_id: str) -> dict:
        """
        從本地 JSON 檔案載入 issue

        Args:
            issue_id: Issue ID（檔名為 <issue_id>.json）

        Returns:
            issue dict

        Raises:
            IssueNotFoundError: 對應的 JSON 檔案不存在
            IssueSourceError: JSON 格式錯誤
        """
        issue_file = self.sources_dir / f"{issue_id}.json"

        if not issue_file.exists():
            raise IssueNotFoundError(
                f"Issue file not found: {issue_file}\n"
                f"Please create the file using the template in issues/TEMPLATE.json"
            )

        try:
            with open(issue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise IssueSourceError(
                f"Invalid JSON format in {issue_file}: {e}"
            )

        # 確保 issue_id 欄位存在
        if 'issue_id' not in data:
            data['issue_id'] = issue_id

        # 讀取圖片/影片附件 → 標準 _images 格式
        attachments = data.get("attachments", [])
        if attachments:
            imgs = _load_local_attachments(attachments, issue_file.parent,
                                           max_video_frames=self.video_max_frames)
            if imgs:
                data["_images"] = imgs

        return data

    def list_all(self, filter: str | None = None) -> list[str]:
        """
        掃描 sources_dir，回傳所有 issue ID（*.json 檔名去掉副檔名）。
        filter 參數由呼叫端（command_batch）做 fnmatch 處理，此處忽略。

        Returns:
            issue ID 列表（依檔名排序）
        """
        if not self.sources_dir.exists():
            return []
        return sorted(
            p.stem for p in self.sources_dir.glob("*.json")
        )
