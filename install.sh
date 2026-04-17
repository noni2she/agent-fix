#!/bin/bash
set -e

echo "╔════════════════════════════════════════╗"
echo "║  Agent Fix - 安裝程序                  ║"
echo "╚════════════════════════════════════════╝"
echo ""

# ── 確認在正確目錄 ──────────────────────────────
if [ ! -f "pyproject.toml" ]; then
    echo "❌ 請在 agent-fix 根目錄執行此腳本"
    exit 1
fi

# ── 1. 檢查 uv ──────────────────────────────────
if ! command -v uv &> /dev/null; then
    echo "❌ uv 未安裝。請先執行："
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✅ uv: $(uv --version)"

# ── 2. 選擇 SDK ─────────────────────────────────
echo ""
echo "請選擇要使用的 AI SDK："
echo "  1) GitHub Copilot（推薦，需 gh CLI）"
echo "  2) Anthropic Claude（需 ANTHROPIC_API_KEY）"
echo "  3) OpenAI Agents（需 OPENAI_API_KEY）"
echo ""
read -p "請輸入選項 [1/2/3]（預設 1）: " SDK_CHOICE
SDK_CHOICE="${SDK_CHOICE:-1}"

case "$SDK_CHOICE" in
    1)
        SDK_EXTRA="copilot"
        SDK_NAME="GitHub Copilot"
        ;;
    2)
        SDK_EXTRA="claude"
        SDK_NAME="Anthropic Claude"
        ;;
    3)
        SDK_EXTRA="openai"
        SDK_NAME="OpenAI Agents"
        ;;
    *)
        echo "❌ 無效選項: $SDK_CHOICE"
        exit 1
        ;;
esac

echo "✅ 選擇 SDK: $SDK_NAME"

# ── 3. Copilot 專屬：gh CLI 驗證 ────────────────
if [ "$SDK_EXTRA" = "copilot" ]; then
    echo ""

    if ! command -v gh &> /dev/null; then
        echo "❌ gh CLI 未安裝。請先執行："
        echo "  brew install gh          # macOS"
        echo "  winget install GitHub.cli  # Windows"
        exit 1
    fi
    echo "✅ gh CLI: $(gh --version | head -n 1)"

    if ! gh extension list 2>/dev/null | grep -q "gh-copilot"; then
        echo "⚠️  gh-copilot extension 未安裝"
        read -p "是否立即安裝? (y/n) " -n 1 -r; echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gh extension install github/gh-copilot
            echo "✅ gh-copilot extension 安裝完成"
        else
            echo "請手動執行：gh extension install github/gh-copilot"
            exit 1
        fi
    else
        echo "✅ gh-copilot extension 已安裝"
    fi

    if ! gh auth status &> /dev/null; then
        echo "⚠️  尚未登入 GitHub"
        read -p "是否立即登入? (y/n) " -n 1 -r; echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            gh auth login
        else
            echo "請手動執行：gh auth login"
            exit 1
        fi
    fi
    echo "✅ GitHub 已登入"
fi

# ── 4. Claude / OpenAI：提示 API key ─────────────
if [ "$SDK_EXTRA" = "claude" ]; then
    echo ""
    echo "ℹ️  Anthropic Claude 需要設定環境變數："
    echo "   export ANTHROPIC_API_KEY=sk-ant-..."
    echo "   建議寫入 .env 檔案"
fi

if [ "$SDK_EXTRA" = "openai" ]; then
    echo ""
    echo "ℹ️  OpenAI Agents 需要設定環境變數："
    echo "   export OPENAI_API_KEY=sk-..."
    echo "   建議寫入 .env 檔案"
fi

# ── 5. 全域安裝 ──────────────────────────────────
echo ""
echo "📥 安裝 agent-fix（SDK: $SDK_NAME）..."
uv tool install --editable ".[$SDK_EXTRA]"

# ── 6. 驗證安裝 ──────────────────────────────────
echo ""
if command -v agent-fix &> /dev/null; then
    echo "✅ 安裝完成！已可使用："
    echo "   agent-fix --help"
    echo "   afix --help"
else
    echo "⚠️  指令未出現在 PATH，請確認 ~/.local/bin 已加入 PATH："
    echo "   echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
    echo "   source ~/.zshrc"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "初始化專案配置："
echo "  agent-fix init /path/to/project --output ./projects/myproject.yaml"
echo ""
echo "執行 Bug 修復："
echo "  export PROJECT_CONFIG=./projects/myproject.yaml"
echo "  agent-fix run BUG-001"
echo "═══════════════════════════════════════════"
