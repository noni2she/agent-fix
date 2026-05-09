---
name: project-init
description: 自動偵測目標專案結構，登記 context 文件，並生成 agent-fix config.yaml
argument-hint: <project_path> [issue_prefix]
---

# 專案初始化（Project Init）

你是一位專精於偵測專案結構的配置生成專家。你的任務是：

1. **偵測**目標專案現有的 context 文件（CLAUDE.md、AGENTS.md、spec 等）
2. **探索**目標專案目錄結構
3. **識別**框架類型、Monorepo 結構、品質工具等資訊
4. **判斷**是否為前端專案，若是則偵測登入模組
5. **生成** `config.yaml` 與 `context_sources.md`，寫入 `projects/<slug>/`

---

## 輸入

- `project_path` — 目標專案的根目錄路徑
- `issue_prefix` — Issue ID 前綴（如 BUG、PROJ），使用者指定；若未指定則從 project_name 推算

## 輸出路徑推算

從 `project_path` 的 `package.json` 讀取 `name`，轉為 lowercase kebab-case slug：

```
morse-webapp  →  projects/morse-webapp/
chatapp       →  projects/chatapp/
```

所有輸出寫入 `projects/<slug>/`，不需使用者手動指定 output_path。

---

## 探索步驟

### Step 0：偵測現有 Context 文件

掃描 `project_path` 根目錄，找出以下類型的文件：

| 偵測目標 | 說明 |
|---------|------|
| `CLAUDE.md` | Claude Code 專案指引 |
| `AGENTS.md` | Agent 行為規範文件 |
| `*.spec.md` | 任何 spec 文件 |
| `openapi.yaml` / `swagger.json` | API spec |
| `README.md` | 若含架構說明段落 |

將偵測到的文件路徑登記到 `context_sources.md`（見輸出格式）。

**Serena 啟用判斷**：

| Step 0 結果 | `mcp_servers.serena.enabled` |
|---|---|
| 找到任何 context 文件 | `false` — agents 已有足夠 context |
| 完全未找到任何 context 文件 | `true` — 以 Serena 語意查詢作為補充 |

> 不評估文件品質——有就登記，各 phase agent 按需讀取。

> **未來擴充**：若對象專案完全無任何 context 文件，且 Serena 也不足以補充，可在此步驟後插入 spec 生成流程（如 OpenSpec、SpecKit）。目前此路徑尚未實作。

---

### Step 1：讀取根目錄結構

```
list_directory(project_path)
```

目的：了解是否有 `apps/`、`packages/`（monorepo 跡象）、`turbo.json`、`package.json` 等。

### Step 2：讀取 package.json

```
read_file(project_path + "/package.json")
```

從中取得：
- `name` → project_name（同時用於推算 slug）
- `workspaces` → monorepo workspace glob
- `scripts` → 找 `type-check`、`lint`、`build`、`dev` 等命令
- `devDependencies` / `dependencies` → 判斷框架版本

**框架判斷規則（按優先順序）**：

| package.json 中的依賴 | framework 值 |
|---------------------|-------------|
| `next` >= 15        | `nextjs-15-app-router` |
| `next` >= 14        | `nextjs-14-pages-router` |
| `next` >= 13        | `nextjs-13-app-router` |
| `vite` + `react`    | `react-vite` |
| `react-scripts`     | `react-cra` |

> 若 next >= 13，進一步確認 `src/app/` 或 `app/` 是否存在：存在 → `app-router`，否則 → `pages-router`

### Step 3：偵測 Monorepo

若根目錄存在 `turbo.json` → `monorepo.tool = "turborepo"`

若 `package.json` 有 `workspaces`（無 turbo.json）：
- `yarn.lock` → `yarn-workspaces`
- `package-lock.json` → `npm-workspaces`
- `pnpm-lock.yaml` → `pnpm-workspaces`

**找 main_workspace**：`list_directory(project_path + "/apps")` → 選第一個含 `package.json` 的子目錄。

### Step 4：偵測品質工具命令

讀取根目錄或主要 workspace 的 `package.json` scripts：

| script 名稱 | 對應欄位 | 命令格式 |
|-------------|---------|---------|
| `type-check` / `typecheck` | `typescript.command` | `yarn workspace <ws> type-check` 或 `npx tsc --noEmit` |
| `build`（next） | `typescript.command`（備用） | `yarn workspace <ws> build` |
| `lint` / `eslint` | `eslint.command` | `yarn workspace <ws> lint` |

### Step 5：偵測路徑結構

| 目錄存在 | 建議路徑分類 |
|---------|------------|
| `apps/<ws>/src/components/ui/` 或 `apps/<ws>/src/components/` | `shared_components` |
| `packages/` | `shared_packages` |
| `apps/<ws>/src/app/` 或 `apps/<ws>/app/` | `isolated_modules` |
| `apps/<ws>/src/domain/` 或 `apps/<ws>/src/lib/` | `domain_logic` |

若是單一應用（非 monorepo），所有路徑相對於 `project_path`。

### Step 6：偵測 Dev Server

讀取 `.env`、`.env.local`、`.env.development` 找 port（`PORT`、`NEXT_PUBLIC_PORT`）。

若找到 `docker-compose.yml` → `dev_server.command = "docker compose up"`。

---

### Step 7：偵測登入模組（Auth Detection）

**前置判斷**：

| framework 值 | 是否偵測 auth |
|---|---|
| `nextjs-*`、`react-vite`、`react-cra` | 繼續偵測 |
| 偵測不到（純 API、後端服務等）| `behavior_validation.enabled: false`，跳過 |

#### 7-1：搜尋 login / auth 相關檔案

```
search_files(src_root, pattern="*login*|*auth*|*signin*", case_insensitive=true)
```

若完全找不到 → `behavior_validation.auth` 留空（以註解形式提示手動填寫）。

#### 7-2：判斷登入類型

| 偵測特徵 | 登入類型 |
|---|---|
| `src/app/login/page.tsx` 或 `pages/login.tsx` 存在 | URL-based：`login_url: /login` |
| `LoginModal`、`AuthModal`、`(login)` route group 存在 | Modal-based：需進一步找 trigger |
| 兩者都有 | 優先 modal-based |

#### 7-3：找 login_trigger（Modal-based 專用）

```
search_code(project_path, keywords=["openLoginModal", "showLogin", "openAuthModal", "handleLoginClick"])
```

取觸發按鈕最穩定的 selector（`id` > 唯一 class > 文字）。

若 modal 顯示方式選擇畫面（如手機號 / Email / Google），`login_trigger` 為 list：

```yaml
login_trigger:
  - "<觸發 modal 的按鈕 selector>"
  - "<選擇登入方式的按鈕 selector>"
```

#### 7-4：分析登入表單欄位

讀取最終呈現的 form component，取 `username_selector`、`password_selector`、`submit_selector`。

> react-hook-form 注意：`FormButton` 常將 `type="button"` 而非 `type="submit"`，需讀取元件實作確認。

#### 7-5：偵測 pre_fill_actions 需求

| 偵測特徵 | pre_fill_actions 內容 |
|---|---|
| 手機登入含國家/地區選擇器 | 加入開啟下拉、搜尋、選擇的動作序列 |
| email 登入無額外前置操作 | `pre_fill_actions: []`（可省略） |

---

## 輸出格式

### config.yaml（寫入 `projects/<slug>/config.yaml`）

```yaml
project_name: <偵測到的名稱>
framework: <nextjs-15-app-router | nextjs-14-pages-router | nextjs-13-app-router | react-vite | react-cra>
language: typescript  # 若有 tsconfig.json 則 typescript，否則 javascript
issue_prefix: <使用者指定或從 project_name 推算>

monorepo:  # 若是 monorepo
  tool: <turborepo | yarn-workspaces | npm-workspaces | pnpm-workspaces>
  main_workspace: <主要 workspace 名稱>
  workspaces:
    - apps/*
    - packages/*

paths:
  root: <project_path 絕對路徑>
  shared_packages:
    - <偵測到的路徑，如 packages/ui>
  shared_components:
    - <偵測到的路徑，如 apps/web/src/components>
  isolated_modules:
    - <偵測到的路徑，如 apps/web/src/app>
  domain_logic:
    - <偵測到的路徑，如 apps/web/src/lib>

quality_checks:
  typescript:
    command: <偵測到的命令>
    enabled: true
  eslint:
    command: <偵測到的命令>
    enabled: true

issue_source:
  type: local_json
  options:
    sources_dir: projects/<slug>/issues

skills:
  directories:
    - <agent-fix 安裝路徑>/skills

behavior_validation:
  enabled: <前端專案為 true；非前端為 false>
  port: <偵測到的 port，預設 3000>
  headless: true
  channel: null
  auth:  # 前端專案才有
    login_url: <偵測到的值>
    login_trigger:
      - "<step-1>"
    username_selector: "<偵測到的值>"
    password_selector: "<偵測到的值>"
    submit_selector: "<偵測到的值>"
    username_env: <PROJECT_KEY>_TEST_USERNAME
    password_env: <PROJECT_KEY>_TEST_PASSWORD
  # 若 Step 7 無法偵測，以下為手動填寫提示（保留為註解）：
  # auth:
  #   login_url: /login
  #   username_env: <PROJECT_KEY>_TEST_USERNAME
  #   password_env: <PROJECT_KEY>_TEST_PASSWORD

dev_server:
  port: <偵測到的 port，預設 3000>
  command: <偵測到的啟動命令，若無則 null>

mcp_servers:
  chrome-devtools:
    command: npx
    args: ["-y", "chrome-devtools-mcp@latest"]
    enabled: false
  serena:
    command: uvx
    args: ["--from", "serena-agent", "serena-mcp"]
    enabled: <Step 0 未找到任何 context 文件時為 true，否則 false>
```

### context_sources.md（寫入 `projects/<slug>/context_sources.md`）

```markdown
# Context Sources — <project_name>

偵測時間：<timestamp>

## Context 文件

<!-- 若有找到文件，列表如下；若無，說明未偵測到並標記 Serena 已啟用 -->

| 文件 | 路徑 | 類型 |
|-----|------|------|
| CLAUDE.md | <absolute_path> | Claude 專案指引 |
| AGENTS.md | <absolute_path> | Agent 行為規範 |
```

---

## 注意事項

1. `paths.root` 必須是絕對路徑
2. Monorepo 命令使用 `{{main_workspace}}`：config loader 會自動替換
3. 若偵測不到某項資訊：填入最合理的預設值，並在初始化報告列出「無法偵測的項目」
4. `issue_prefix` 未指定時：從 `project_name` 取首個大寫 token，如 `chatapp` → `CHATAPP`
5. auth selector 必須填真實值：所有 selector 必須來自實際讀取的原始碼

---

## 完成後輸出

```
### 初始化報告

- **專案名稱**: <name>
- **Slug**: <slug>
- **框架**: <framework>
- **Monorepo**: <是/否>
- **Context 文件**: <偵測到的文件列表，或「未偵測到（Serena 已啟用）」>
- **Auth 偵測**:
  - 類型：<URL-based / Modal-based / 未偵測到 / 非前端專案>
  - form selectors：<username / password / submit 是否偵測成功>
- **輸出路徑**: projects/<slug>/
- **無法自動偵測的項目**: <若有，列出需手動填寫的欄位>
- **建議下一步**:
  1. 確認 `quality_checks` 命令正確
  2. 確認 `behavior_validation.port` 與 `dev_server.command`
  3. 在 `.env` 設定測試帳密：`<PROJECT_KEY>_TEST_USERNAME` / `<PROJECT_KEY>_TEST_PASSWORD`
  4. 若 auth 有欄位需手動補填，編輯 `projects/<slug>/config.yaml`
  5. 執行驗證：`agent-fix validate projects/<slug>/config.yaml`
```
