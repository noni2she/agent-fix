"""Dev Server 管理器

支援兩種啟動模式：
1. 提供 dev_command（直接執行，優先使用）
2. 提供 workspace（使用 yarn workspace <ws> dev，向後相容）
3. 兩者都不提供且 server 未運行 → 警告並跳過
"""
import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests


class DevServerManager:
    """Dev Server 生命週期管理"""

    def __init__(
        self,
        port: int,
        project_root: Path,
        dev_command: Optional[list[str]] = None,
        workspace: Optional[str] = None,
    ):
        self.port = port
        self.project_root = project_root
        self.dev_command = dev_command      # 優先使用（來自 config.dev_server.command）
        self.workspace = workspace          # fallback：yarn workspace <ws> dev
        self.base_url = f"http://localhost:{port}"
        self.process: Optional[subprocess.Popen] = None

    def _resolve_command(self) -> Optional[list[str]]:
        """解析實際要執行的啟動命令"""
        if self.dev_command:
            return self.dev_command
        if self.workspace:
            return ["yarn", "workspace", self.workspace, "dev"]
        return None

    async def start(self) -> bool:
        """啟動並等待就緒。回傳是否成功。"""
        if self._health_check():
            print(f"  ✅ Dev server 已在執行: {self.base_url}")
            return True

        cmd = self._resolve_command()
        if not cmd:
            print(f"  ⚠️  未設定 dev server 命令，跳過啟動")
            print(f"     請在 config.yaml 設定 dev_server.command 或 behavior_validation.workspace")
            return False

        print(f"  🚀 啟動 dev server (port {self.port}): {' '.join(cmd)}")
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.project_root),
                env={**os.environ, "PORT": str(self.port)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return await self._wait_ready(timeout=60)
        except Exception as e:
            print(f"  ❌ Dev server 啟動失敗: {e}")
            return False

    async def _wait_ready(self, timeout: int) -> bool:
        """輪詢等待 HTTP 就緒"""
        start = time.time()
        while time.time() - start < timeout:
            if self.process and self.process.poll() is not None:
                print(f"  ❌ Dev server 已提前結束（exit code {self.process.returncode}）")
                return False
            if self._health_check():
                print(f"  ✅ Dev server 就緒: {self.base_url}")
                return True
            await asyncio.sleep(2)
        print(f"  ❌ Dev server 啟動超時（>{timeout}s）")
        return False

    def _health_check(self) -> bool:
        """HTTP 健康檢查"""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code < 500
        except Exception:
            return False

    async def stop(self):
        """優雅停止 server"""
        if not self.process:
            return
        print(f"  🛑 停止 dev server (pid={self.process.pid})...")
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None
