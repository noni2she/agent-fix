#!/bin/bash
set -e

echo "╔════════════════════════════════════════╗"
echo "║  Agent Fix - 安裝程序                  ║"
echo "╚════════════════════════════════════════╝"
echo ""

# 1. 檢查 uv
if ! command -v uv &> /dev/null; then
    echo "❌ uv 未安裝。請先執行："
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✅ uv: $(uv --version)"

# 2. 檢查 gh CLI
if ! command -v gh &> /dev/null; then
    echo "❌ gh CLI 未安裝。請先執行："
    echo "  brew install gh"
    exit 1
fi
echo "✅ gh CLI: $(gh --version | head -n 1)"

# 3. 檢查 gh-copilot extension
if ! gh extension list | grep -q "gh-copilot"; then
    echo "⚠️  gh-copilot extension 未安裝"
    read -p "是否立即安裝? (y/n) " -n 1 -r; echo
    [[ $REPLY =~ ^[Yy]$ ]] && gh extension install github/gh-copilot || exit 1
fi
echo "✅ gh-copilot extension 已安裝"

# 4. 檢查 GitHub 登入
if ! gh auth status &> /dev/null; then
    echo "⚠️  尚未登入 GitHub"
    read -p "是否立即登入? (y/n) " -n 1 -r; echo
    [[ $REPLY =~ ^[Yy]$ ]] && gh auth login || exit 1
fi
echo "✅ GitHub 已登入"

# 5. 全域安裝（含 Copilot SDK）
echo ""
echo "📥 安裝 agent-fix..."
uv tool install --editable ".[copilot]" "$(pwd)"

echo ""
echo "✅ 安裝完成！"
echo ""
echo "═══════════════════════════════════════════"
echo "初始化專案配置："
echo "  agent-fix init /path/to/project --output ./projects/myproject.yaml"
echo ""
echo "執行 Bug 修復："
echo "  export PROJECT_CONFIG=./projects/myproject.yaml"
echo "  agent-fix run BUG-001"
echo "═══════════════════════════════════════════"
