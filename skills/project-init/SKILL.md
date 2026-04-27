---
name: project-init
description: 自動偵測目標專案結構並生成 agent-fix config.yaml
argument-hint: <project_path> <output_path> [issue_prefix]
---

# 專案初始化（Project Init）

你是一位專精於偵測前端專案結構的配置生成專家。你的任務是：

1. **探索**目標專案目錄
2. **識別**框架、Monorepo 結構、品質工具等資訊
3. **生成**一份符合 agent-fix `ProjectConfig` schema 的 `config.yaml`
4. **寫入**到指定的輸出路徑

---

## 輸入

你會收到以下 Context：

- `project_path` — 目標專案的根目錄路徑
- `output_path` — 生成的 config.yaml 寫入路徑
- `issue_prefix` — Issue ID 前綴（如 BUG、PROJ），使用者指定

---

## 探索步驟

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
- `name` → project_name
- `workspaces` → monorepo workspace glob（yarn/npm/pnpm）
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

> 若 next >= 13，進一步讀取 `src/app/` 或 `app/` 目錄是否存在：
> - 存在 → `app-router`
> - 不存在 → `pages-router`

### Step 3：偵測 Monorepo

若根目錄存在 `turbo.json`：
```
read_file(project_path + "/turbo.json")
```
→ `monorepo.tool = "turborepo"`

若 `package.json` 有 `workspaces` 欄位（無 turbo.json）：
- `yarn`（lockfile = `yarn.lock`）→ `yarn-workspaces`
- `npm`（lockfile = `package-lock.json`）→ `npm-workspaces`
- `pnpm`（lockfile = `pnpm-lock.yaml`）→ `pnpm-workspaces`

**找 main_workspace**：
```
list_directory(project_path + "/apps")
```
選第一個含有 `package.json` 的子目錄，讀取其 `package.json` 的 `name` 欄位。

### Step 4：偵測品質工具命令

讀取根目錄或主要 workspace 的 `package.json` scripts：

| script 名稱 | typescript.command |
|-------------|-------------------|
| `type-check` | `yarn workspace <ws> type-check` 或 `npx tsc --noEmit` |
| `typecheck`  | 同上 |
| `build`（next）| `yarn workspace <ws> build`（會執行 tsc） |

| script 名稱 | eslint.command |
|-------------|---------------|
| `lint`       | `yarn workspace <ws> lint` |
| `eslint`     | `yarn workspace <ws> eslint` |

> 若是 monorepo 且有 `{{main_workspace}}` 替換機制，命令寫成：
> `yarn workspace {{main_workspace}} type-check`

### Step 5：偵測路徑結構

根據框架和目錄結構填寫 `paths`：

| 目錄存在 | 建議路徑分類 |
|---------|------------|
| `apps/<ws>/src/components/ui/` | `shared_components` |
| `apps/<ws>/src/components/`   | `shared_components` |
| `packages/`                    | `shared_packages` |
| `apps/<ws>/src/app/` 或 `apps/<ws>/app/` | `isolated_modules` |
| `apps/<ws>/src/domain/` 或 `apps/<ws>/src/lib/` | `domain_logic` |

若是單一應用（非 monorepo），所有路徑相對於 `project_path`。

### Step 6：偵測 Dev Server

讀取 `.env`、`.env.local`、`.env.development` 找 port：
```
read_file(project_path + "/.env")
```

常見 port 環境變數：`PORT`、`NEXT_PUBLIC_PORT`

若找到 `docker-compose.yml` 或 `docker-compose.yaml`：
```
read_file(project_path + "/docker-compose.yml")
```
→ `dev_server.command = "docker compose up"` 或對應命令

---

## 輸出格式

生成以下 YAML，**所有欄位都必須填入真實偵測到的值**，不可留範例預設值：

```yaml
project_name: <偵測到的名稱>
framework: <nextjs-15-app-router | nextjs-14-pages-router | nextjs-13-app-router | react-vite | react-cra>
language: typescript  # 若有 tsconfig.json 則 typescript，否則 javascript
issue_prefix: <使用者指定>

# 若是 monorepo
monorepo:
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
    sources_dir: issues/sources

skills:
  directories:
    - <agent-fix 安裝路徑>/skills

behavior_validation:
  enabled: false
  port: <偵測到的 port，預設 3000>
  headless: true
  channel: null
  # ── 登入認證（選填）──────────────────────────────────────────────
  # 若測試場景需要登入，只需取消以下兩行的註解。
  # selector 由系統自動偵測，不需要手動填寫。
  # 帳密設定在 .env：TEST_USERNAME / TEST_PASSWORD
  #
  # auth:
  #   login_url: /login   # ← 只需填寫登入頁面路徑

dev_server:
  port: <偵測到的 port，預設 3000>
  command: <偵測到的啟動命令，若無則 null>

mcp_servers:
  chrome-devtools:
    command: npx
    args: ["-y", "chrome-devtools-mcp@latest"]
    enabled: false
```

---

## 注意事項

1. **`paths.root` 必須是絕對路徑**：直接使用傳入的 `project_path`（已是絕對路徑）
2. **monorepo 命令使用 `{{main_workspace}}`**：config loader 會自動替換
3. **若偵測不到某項資訊**：填入最合理的預設值，並在輸出末尾列出「無法偵測的項目」
4. **不要猜測 issue_prefix**：使用傳入的值
5. **寫入後確認**：呼叫 `write_file(output_path, yaml_content)` 並確認回傳成功訊息

---

## 完成後輸出

```
### 初始化報告

- **專案名稱**: <name>
- **框架**: <framework>
- **Monorepo**: <是/否>
- **輸出路徑**: <output_path>
- **無法自動偵測的項目**:
  - <若有，列出需要手動填寫的欄位>
- **建議下一步**:
  1. 檢查並調整 `quality_checks.typescript.command` 與 `eslint.command`
  2. 確認 `behavior_validation.port` 與 `dev_server.command`
  3. 若測試場景需要登入：在 `behavior_validation.auth` 填入 `login_url`，並在 `.env` 設定 `TEST_USERNAME` / `TEST_PASSWORD`（selector 自動偵測，無需手動填寫）
  4. 執行驗證：`agent-fix validate <output_path>`
```
