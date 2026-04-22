# Skills References

此目錄存放可選的「vendor skills」，供 core workflow skills（bugfix-implement、bugfix-analyze、bugfix-test）在執行過程中按需載入。

## 已內建的 skills

| Skill | 說明 | 觸發情境 |
|-------|------|---------|
| `vercel-react-best-practices` | React/Next.js 效能最佳化規則（Vercel 官方） | 修改 React component、資料獲取、bundle 優化 |
| `web-design-guidelines` | Web UI 合規性檢查（Vercel 官方） | 修改 UI 樣式或互動行為 |

## 如何新增 skill

將 skill 目錄放入此資料夾，確保包含 `SKILL.md`：

```
skills/references/
└── your-skill-name/
    └── SKILL.md
```

然後在 `config.yaml` 的 `skills.directories` 加入此目錄路徑，LLM 即可在執行時用 `read_file` 載入。

## 設定方式

在專案 `config.yaml` 中：

```yaml
skills:
  directories:
    - /path/to/agent-fix/skills           # core workflow skills
    - /path/to/agent-fix/skills/references  # vendor/optional skills
```
