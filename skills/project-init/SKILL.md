---
name: project-init
description: 自動偵測目標專案結構，登記 context 文件，並生成 agent-fix config.yaml
argument-hint: <project_path> [issue_prefix]
---

# 專案初始化（Project Init）

輸入 `project_path`，依序執行以下步驟，產出 `config.yaml` 與 `context_sources.md` 寫入 `projects/<slug>/`。

## 輸出路徑

從 `package.json` 的 `name` 轉為 kebab-case slug：`morse-webapp` → `projects/morse-webapp/`

---

## 步驟

### Step 0：偵測 Context 文件

掃描 `project_path` 根目錄，登記以下文件（有就登記，不評估品質）：

`CLAUDE.md` / `AGENTS.md` / `*.spec.md` / `openapi.yaml` / `swagger.json` / `README.md`（含架構段落）

結果寫入 `context_sources.md`（見輸出格式）。

> **未來擴充**：若完全無 context 文件且 Serena 不足補充，可插入 spec 生成流程（尚未實作）。

### Step 1：讀取根目錄與 package.json

確認 monorepo 跡象（`apps/`、`packages/`、`turbo.json`），取得：

- `name` → slug
- `workspaces` → monorepo workspace glob
- `scripts` → 品質工具命令
- `dependencies` → 框架版本

**框架判斷**：

| 依賴 | framework |
|------|-----------|
| `next` >= 15 | `nextjs-15-app-router` |
| `next` >= 14 | `nextjs-14-pages-router` |
| `next` >= 13 | `nextjs-13-app-router` |
| `vite` + `react` | `react-vite` |
| `react-scripts` | `react-cra` |

> next >= 13：確認 `src/app/` 或 `app/` 存在 → `app-router`，否則 → `pages-router`

### Step 2：偵測 Monorepo

| 條件 | tool |
|------|------|
| `turbo.json` 存在 | `turborepo` |
| `workspaces` + `yarn.lock` | `yarn-workspaces` |
| `workspaces` + `package-lock.json` | `npm-workspaces` |
| `workspaces` + `pnpm-lock.yaml` | `pnpm-workspaces` |

**main_workspace**：`apps/` 下第一個含 `package.json` 的子目錄。

### Step 3：偵測品質工具與路徑結構

**品質工具**（讀根目錄與 main_workspace 的 scripts 及根目錄設定檔）：

| 條件 | 欄位 | 命令格式 |
|------|------|---------|
| scripts 有 `type-check` / `typecheck` | `typescript.command` | `yarn workspace <ws> type-check` |
| 無上述 script（fallback） | `typescript.command` | `npx tsc --noEmit` |
| scripts 有 `lint` / `eslint` | `eslint.command` | `yarn workspace <ws> lint` |
| 根目錄有 `.prettierrc*` 或 `prettier.config.*` | `prettier.command` | `yarn prettier --check .` |
| scripts 有 `test` / `vitest` / `jest` | `tests.command` | `yarn workspace <ws> test`（`enabled: false`） |

**路徑結構**：

| 目錄 | 分類 |
|------|------|
| `apps/<ws>/src/components/` | `shared_components` |
| `packages/` | `shared_packages` |
| `apps/<ws>/src/app/` | `isolated_modules` |

單一應用（非 monorepo）路徑相對於 `project_path`。

### Step 4：偵測 Dev Server

讀 `.env` / `.env.local` / `.env.development` / `apps/<ws>/.env.local` 找 `PORT` 或 `NEXT_PUBLIC_PORT`。

若有 `docker-compose.yml` 或 `compose.yaml` → `dev_server.command = "docker compose up"`。

### Step 5：偵測登入模組（Auth）

前端框架（`nextjs-*`、`react-vite`、`react-cra`）才執行；否則 `behavior_validation.enabled: false`，跳過。

**5-1 搜尋 auth 檔案**：`*login*|*auth*|*signin*`（case-insensitive）

若找不到 → auth 區塊留空並加註解提示手動填寫。

**5-2 登入類型**：

| 特徵 | 類型 |
|------|------|
| `app/login/page.tsx` 或 `pages/login.tsx` | URL-based |
| `LoginModal` / `AuthModal` / `(login)` route group | Modal-based（優先） |

**5-3 Modal trigger**（Modal-based 專用）：

搜尋 `openLoginModal` / `showLogin` / `openAuthModal` / `handleLoginClick`，取最穩定 selector（`id` > 唯一 class > 文字）。

多步驟選擇畫面（如手機號 / Email / Google）→ `login_trigger` 為 list。

**5-4 表單欄位**：讀 form component，取 `username_selector`、`password_selector`、`submit_selector`。

> react-hook-form：`FormButton` 常用 `type="button"`，需確認元件實作。

**5-5 pre_fill_actions**：手機登入含國家選擇器 → 加入下拉操作序列；email 登入 → 省略。

---

## 輸出格式

### config.yaml

```yaml
project_name: <name>
framework: <nextjs-15-app-router | nextjs-14-pages-router | nextjs-13-app-router | react-vite | react-cra>
language: typescript  # 有 tsconfig.json → typescript，否則 javascript
issue_prefix: <指定值；未指定則取 project_name 第一段並大寫：morse-webapp → MORSE>

monorepo:  # monorepo 才有此區塊
  tool: <turborepo | yarn-workspaces | npm-workspaces | pnpm-workspaces>
  main_workspace: <ws>
  workspaces:
    - apps/*
    - packages/*

paths:
  root: <project_path 絕對路徑>
  shared_packages:    [<e.g. packages/ui>]
  shared_components:  [<e.g. apps/web/src/components>]
  isolated_modules:   [<e.g. apps/web/src/app>]

quality_checks:
  typescript:
    command: <偵測到的命令，無 type-check script 時為 npx tsc --noEmit>
    enabled: true
  eslint:
    command: <偵測到的命令>
    enabled: true
  prettier:  # 偵測到 .prettierrc* 才產生此區塊
    command: <偵測到的命令>
    enabled: true
  tests:  # 偵測到 test script 才產生此區塊
    command: <偵測到的命令>
    enabled: false

issue_source:
  type: local_json
  options:
    sources_dir: projects/<slug>/issues

skills:
  directories:
    - <agent-fix 安裝路徑>/skills

behavior_validation:
  enabled: <前端 true；非前端 false>
  port: <port，預設 3000>
  headless: true
  channel: null
  auth:  # 前端才有
    login_url: <值>
    login_trigger:
      - "<step-1 selector>"
    username_selector: "<值>"
    password_selector: "<值>"
    submit_selector: "<值>"
    username_env: <PROJECT_KEY>_TEST_USERNAME
    password_env: <PROJECT_KEY>_TEST_PASSWORD
  # 若 Step 5 無法偵測，保留以下為手動填寫提示：
  # auth:
  #   login_url: /login
  #   username_env: <PROJECT_KEY>_TEST_USERNAME
  #   password_env: <PROJECT_KEY>_TEST_PASSWORD

dev_server:
  port: <port，預設 3000>
  command: <啟動命令，若無則 null>

mcp_servers:
  chrome-devtools:
    command: npx
    args: ["-y", "chrome-devtools-mcp@latest"]
    enabled: <前端 true；非前端 false>
    # 進階：連接既有 Chrome session（保留登入狀態）：
    # args: ["-y", "chrome-devtools-mcp@latest", "--browserUrl", "http://localhost:9222"]
    # pre_launch: "open -na 'Google Chrome' --args --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug"
    # pre_launch_wait: 3
  serena:
    command: uvx
    args: ["--from", "serena-agent", "serena", "start-mcp-server", "--project", "<paths.root>"]
    enabled: true
```

### context_sources.md

```markdown
# Context Sources — <project_name>

偵測時間：<timestamp>

## Context 文件

<!-- 有文件則列表；無則說明未偵測到 -->

| 文件 | 路徑 | 類型 |
|-----|------|------|
| CLAUDE.md | <path> | Claude 專案指引 |
```

---

## 注意事項

1. `paths.root` 必須是絕對路徑
2. Monorepo 命令使用 `{{main_workspace}}`：config loader 會自動替換
3. 偵測不到某項資訊：填最合理預設值，並在報告列出「無法偵測的項目」
4. `issue_prefix` 未指定：取 `project_name` 第一個 `-` 前的詞並大寫，如 `morse-webapp → MORSE`、`chatapp → CHATAPP`
5. auth selector 必須來自實際讀取的原始碼，不可猜測

---

## 完成後輸出

```
### 初始化報告

- **專案名稱**: <name>
- **Slug**: <slug>
- **框架**: <framework>
- **Monorepo**: <是/否>
- **Context 文件**: <列表，或「未偵測到」>
- **Auth 偵測**: <URL-based / Modal-based / 未偵測到 / 非前端>
  - form selectors: <username / password / submit 是否偵測成功>
- **輸出路徑**: projects/<slug>/
- **無法自動偵測**: <需手動補填的欄位>
- **建議下一步**:
  1. 確認 quality_checks 命令正確
  2. 確認 behavior_validation.port 與 dev_server.command
  3. 在 .env 設定：<PROJECT_KEY>_TEST_USERNAME / <PROJECT_KEY>_TEST_PASSWORD
  4. 若 auth 有欄位需手動補填，編輯 projects/<slug>/config.yaml
  5. 執行驗證：agent-fix validate projects/<slug>/config.yaml
```
