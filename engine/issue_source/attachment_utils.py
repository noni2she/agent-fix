"""
Attachment utilities — 圖片與影片附件處理
"""
import base64
import os
import subprocess
import tempfile
from pathlib import Path

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MIME_MAP = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}

DEFAULT_VIDEO_MAX_FRAMES = 8
VIDEO_FRAME_WIDTH = 960   # 縮放寬度（高度等比）
VIDEO_FRAME_QUALITY = 5   # ffmpeg JPEG -q:v，1=最佳/最大，31=最差/最小


def video_to_frames(video_bytes: bytes, max_frames: int = DEFAULT_VIDEO_MAX_FRAMES) -> list[dict]:
    """
    將影片 bytes 拆解為均勻分布的 JPEG frames，回傳標準 _images 格式。

    依賴：系統需安裝 ffmpeg / ffprobe（CLI 工具）。
    若未安裝，回傳空 list 並印出警告。

    Args:
        video_bytes:  影片原始 bytes
        max_frames:   最多截幾張，預設 8

    Returns:
        [{"data": base64, "mime_type": "image/jpeg", "name": "frame_01.jpg"}, ...]
    """
    if not _ffmpeg_available():
        print("  ⚠️  ffmpeg 未安裝，略過影片附件（brew install ffmpeg）")
        return []

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "input.mp4")
        Path(video_path).write_bytes(video_bytes)

        # 取得影片長度（秒）
        duration = _get_duration(video_path)

        # 計算取樣 fps：在 duration 秒內均勻取 max_frames 張
        fps = max_frames / max(duration, 1)
        frame_pattern = os.path.join(tmpdir, "frame_%02d.jpg")

        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"fps={fps:.6f},scale={VIDEO_FRAME_WIDTH}:-1",
                "-frames:v", str(max_frames),
                "-q:v", str(VIDEO_FRAME_QUALITY),
                "-y", frame_pattern,
            ],
            capture_output=True,
            timeout=120,
        )

        images = []
        for i in range(1, max_frames + 1):
            frame_path = os.path.join(tmpdir, f"frame_{i:02d}.jpg")
            if os.path.exists(frame_path):
                data = base64.b64encode(Path(frame_path).read_bytes()).decode("ascii")
                images.append({
                    "data": data,
                    "mime_type": "image/jpeg",
                    "name": f"frame_{i:02d}.jpg",
                })

        return images


def _get_duration(video_path: str) -> float:
    """用 ffprobe 取得影片長度（秒），失敗則回傳 60.0 作為保守估計。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return 60.0


def _ffmpeg_available() -> bool:
    """確認 ffmpeg 是否安裝在系統 PATH。"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
