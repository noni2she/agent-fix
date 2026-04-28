---
name: project-init
description: 自動偵測目標專案結構並生成 agent-fix config.yaml
argument-hint: <project_path> <output_path> [issue_prefix]
---

# 專案初始化（Project Init）

你是一位專精於偵測專案結構的配置生成專家。你的任務是：

1. **探索**目標專案目錄
2. **識別**框架類型、Monorepo 結構、品質工具等資訊
3. **判斷**是否為前端專案，若是則偵測登入模組
4. **生成**一份符合 agent-fix `ProjectConfig` schema 的 `config.yaml`
5. **寫入**到指定的輸出路徑

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

### Step 7：偵測登入模組（Auth Detection）

**前置判斷：是否為前端專案？**

| framework 值 | 是否偵測 auth |
|---|---|
| `nextjs-*`、`react-vite`、`react-cra` | ✅ 繼續偵測 |
| 偵測不到（純 API、後端服務等）| ❌ `behavior_validation.enabled: false`，跳過本步驟 |

---

**前端專案：執行以下偵測流程**

#### 7-1：搜尋 login / auth 相關檔案

```
search_files(src_root, pattern="*login*|*auth*|*signin*", case_insensitive=true)
list_directory(src_root)  # 找 (login)、auth、login 等目錄
```

**若完全找不到任何 login 相關檔案**：
→ `behavior_validation.auth` 留空（以註解形式提示手動填寫），在完成報告列出「未偵測到 login 模組」

---

#### 7-2：判斷登入類型

| 偵測特徵 | 登入類型 |
|---|---|
| `src/app/login/page.tsx` 或 `pages/login.tsx` 存在 | **URL-based**：`login_url: /login` |
| `LoginModal`、`AuthModal`、`(login)` route group 存在 | **Modal-based**：需進一步找 trigger |
| 兩者都有 | 優先 modal-based |

---

#### 7-3：找 login_trigger（Modal-based 專用）

搜尋觸發登入 modal 的元素：

```
search_code(project_path, keywords=["openLoginModal", "showLogin", "openAuthModal", "handleLoginClick"])
```

讀取呼叫這些函式的 view-controller 或 layout 檔，找到觸發按鈕的 JSX，取其最穩定的 selector：
- 有 `id` → `#id`
- 有唯一 class → `button.class-name`
- 有文字 → `text=文字內容`

**多步驟判斷**：讀取 modal 內容，若登入 modal 顯示的是「方式選擇畫面」（如手機號 / Email / Google 三個選項），而不是直接顯示表單，則 `login_trigger` 為 list：

```yaml
login_trigger:
  - "<觸發 modal 的按鈕 selector>"
  - "<選擇登入方式的按鈕 selector>"   # 如 text=使用手机号继续
```

---

#### 7-4：分析登入表單欄位

讀取最終呈現的 form component（如 `PhoneLoginForm.tsx`、`EmailLoginForm.tsx`）：

| 找到的欄位 | selector 規則 |
|---|---|
| `<input id="phone">` | `username_selector: "#phone"` |
| `<input id="email">` | `username_selector: "#email"` |
| `<input id="password">` | `password_selector: "#password"` |
| `<button type="submit">` | `submit_selector: "button[type=submit]"` |
| submit button 無 `type=submit`（如 react-hook-form 的 `type=button`）| 找最穩定的 class 組合，如 `button.w-full.h-12.bg-green-500` |

> **react-hook-form 注意**：`FormButton` 元件常將 `type="button"` 而非 `type="submit"`，需讀取元件實作確認。

---

#### 7-5：偵測 pre_fill_actions 需求

檢查 form 是否有在填帳密前需要額外操作的 UI 元素：

| 偵測特徵 | pre_fill_actions 內容 |
|---|---|
| 手機登入含國家/地區選擇器（hidden input + dropdown button）| 加入開啟下拉、搜尋、選擇的 click/fill/wait 動作序列 |
| email 登入無額外前置操作 | `pre_fill_actions: []`（可省略） |
| 其他自訂前置步驟 | 依實際 UI 推斷 |

若無法確定 pre_fill_actions，留空並在報告中說明。

---

#### 7-6：產生 behavior_validation.auth 設定

依偵測結果填寫（**以偵測到的真實值填入，不使用範例值**）：

```yaml
behavior_validation:
  enabled: true
  port: <dev server port>
  headless: true
  channel: null
  auth:
    login_url: <URL-based 填路徑；Modal-based 填觸發頁面路徑，通常為 />
    login_trigger:                    # 單步驟用字串，多步驟用 list；URL-based 省略
      - "<step-1 selector>"
      - "<step-2 selector>"
    pre_fill_actions:                 # 若無前置操作則省略此欄位
      - action: click
        selector: "<selector>"
      - action: fill
        selector: "<selector>"
        value: "<value>"
      - action: wait
        selector: "<selector>"
    username_selector: "<input selector>"
    password_selector: "<input selector>"
    submit_selector: "<button selector>"
    username_env: <PROJECT_KEY>_TEST_USERNAME   # 以專案 key 為前綴，支援多專案共存
    password_env: <PROJECT_KEY>_TEST_PASSWORD
```

> `username_env` / `password_env` 命名規則：將 `project_name` 轉大寫 + 底線，如 `morse-webapp` → `MORSE_WEBAPP_TEST_USERNAME`。
> 帳密由使用者自行設定至 agent-fix 根目錄的 `.env`，**不寫入 config.yaml**。

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
  enabled: <前端專案為 true；非前端為 false>
  port: <偵測到的 port，預設 3000>
  headless: true
  channel: null
  # ── 以下為前端專案才有的 auth 區塊 ──────────────────────────────
  # 若 Step 7 成功偵測到 login 模組，填入以下真實值：
  auth:
    login_url: <偵測到的值>
    login_trigger:            # URL-based 省略；multi-step modal 為 list
      - "<step-1>"
      - "<step-2>"
    pre_fill_actions:         # 若無前置操作則省略
      - action: click
        selector: "<selector>"
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
```

---

## 注意事項

1. **`paths.root` 必須是絕對路徑**：直接使用傳入的 `project_path`（已是絕對路徑）
2. **monorepo 命令使用 `{{main_workspace}}`**：config loader 會自動替換
3. **若偵測不到某項資訊**：填入最合理的預設值，並在輸出末尾列出「無法偵測的項目」
4. **不要猜測 issue_prefix**：使用傳入的值
5. **寫入後確認**：呼叫 `write_file(output_path, yaml_content)` 並確認回傳成功訊息
6. **非前端專案跳過 auth**：若框架偵測不到（純 API、後端服務等），`behavior_validation.enabled: false`，直接省略 `auth` 區塊
7. **auth selector 必須填真實值**：不可使用 SKILL.md 中的範例 selector，所有 selector 必須來自實際讀取的原始碼
8. **`username_env` / `password_env` 命名規則**：`project_name` 轉大寫 + 底線前綴，如 `morse-webapp` → `MORSE_WEBAPP_TEST_USERNAME`；帳密由使用者自行設定至 agent-fix 根目錄的 `.env`，**不寫入 config.yaml**
9. **auth 偵測失敗時保留註解提示**：若 Step 7 無法確定 selector，以 YAML 註解方式保留空白區塊，並在報告中說明需手動補填

---

## 完成後輸出

```
### 初始化報告

- **專案名稱**: <name>
- **框架**: <framework>
- **Monorepo**: <是/否>
- **Auth 偵測**:
  - 類型：<URL-based / Modal-based / 未偵測到 / 非前端專案（跳過）>
  - login_trigger：<偵測到的 selector 或「需手動填寫」>
  - pre_fill_actions：<有 N 個前置動作 / 無 / 需手動確認>
  - form selectors：<username / password / submit 是否偵測成功>
- **輸出路徑**: <output_path>
- **無法自動偵測的項目**:
  - <若有，列出需要手動填寫的欄位>
- **建議下一步**:
  1. 檢查並調整 `quality_checks.typescript.command` 與 `eslint.command`
  2. 確認 `behavior_validation.port` 與 `dev_server.command`
  3. 在 agent-fix 根目錄的 `.env` 設定測試帳密：
     `<PROJECT_KEY>_TEST_USERNAME=<帳號>`
     `<PROJECT_KEY>_TEST_PASSWORD=<密碼>`
  4. 若 auth 有欄位需手動補填，編輯 `<output_path>` 中的 `behavior_validation.auth`
  5. 執行驗證：`agent-fix validate <output_path>`
```
