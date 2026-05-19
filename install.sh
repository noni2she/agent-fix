#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════╗"
echo "║  Agent Fix — 開發者安裝程序                          ║"
echo "║  一般使用者請改用 claude plugin install agent-fix    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 確認在正確目錄 ──────────────────────────────────────────────────
if [ ! -f "pyproject.toml" ]; then
    echo "❌ 請在 agent-fix 根目錄執行此腳本"
    exit 1
fi

# ── 1. 確認 uv ──────────────────────────────────────────────────────
if ! command -v uv &> /dev/null; then
    echo "❌ uv 未安裝。請先執行："
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✅ uv $(uv --version)"

# ── 2. 確認 claude CLI ──────────────────────────────────────────────
if ! command -v claude &> /dev/null; then
    echo "❌ claude CLI 未安裝。請先執行："
    echo "   curl -fsSL https://claude.ai/install.sh | bash"
    echo "   或: brew install --cask claude-code"
    exit 1
fi
echo "✅ claude $(claude --version 2>/dev/null | head -1)"

# ── 3. 安裝 Python 依賴（本地 venv）────────────────────────────────
echo ""
echo "📥 安裝 Python 依賴..."
uv sync
echo "✅ Python 依賴安裝完成"

# ── 4. 安裝全域 agent-fix 指令（batch driver）──────────────────────
echo ""
echo "📥 安裝 agent-fix 全域指令..."
uv tool install --editable .
echo "✅ agent-fix 指令已安裝"

# ── 5. 安裝 Claude Code plugin（本地開發版）────────────────────────
echo ""
echo "📥 安裝 Claude Code plugin（本地開發版）..."
claude plugin install .
echo "✅ Plugin 安裝完成"

# ── 6. 安裝 Playwright Chromium ─────────────────────────────────────
echo ""
echo "📥 安裝 Playwright Chromium（行為驗證用）..."
uv run playwright install chromium
echo "✅ Playwright Chromium 安裝完成"

# ── 完成 ─────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ 開發環境安裝完成！"
echo ""
echo "設定步驟："
echo ""
echo "  1. 複製並填寫專案配置："
echo "     cp config-template.yaml projects/<slug>/config.yaml"
echo ""
echo "  2. （Jira 用戶）設定環境變數（可寫入 .env）："
echo "     JIRA_BASE_URL=https://your-company.atlassian.net"
echo "     JIRA_USER_EMAIL=your@email.com"
echo "     JIRA_API_TOKEN=..."
echo ""
echo "  3. （行為驗證用戶）設定測試帳號："
echo "     TEST_USERNAME=..."
echo "     TEST_PASSWORD=..."
echo ""
echo "使用方式："
echo ""
echo "  Plugin mode（在 Claude Code 裡）："
echo "    /agent-fix:fix-one-issue CHATAPP-5339 projects/<slug>/config.yaml"
echo "    ↑ 第一次帶 config path，同 session 後續不需要再帶"
echo ""
echo "  Batch mode（Terminal）："
echo "    export PROJECT_CONFIG=./projects/<slug>/config.yaml"
echo "    agent-fix --issues CHATAPP-5339"
echo "    agent-fix --issues CHATAPP-5339,CHATAPP-5340,CHATAPP-5341"
echo "    agent-fix --issues-file issues.txt"
echo "    agent-fix --source jira --jql \"project = CHATAPP AND status = 'To Do'\""
echo ""
echo "⚠️  注意：這是開發者安裝版（本地 clone）。"
echo "   一般使用者請改用 PyPI 套件版（待發布）："
echo "   claude plugin install agent-fix@noni2she/agent-fix"
echo "═══════════════════════════════════════════════════════════════"
