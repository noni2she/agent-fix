# Brainstorm

> 與 agent-fix 架構無直接關聯的新 idea、路線討論、跨專案整合構想。
> 隨時隨地記錄，不需要結構化，等想法成熟後再決定歸屬。

---

## 2026-04-11：個人知識庫 × jarvis-team

### 緣起

在 agent-fix Direction B（pip install package 化）的過程中，討論了大量 Python 開發工具知識（pyproject.toml entry points、hatch build、uv vs pip、module-level import 問題等）。這些知識目前散落在 Claude Code 對話紀錄裡，沒有被系統化保留。

### 構想

透過 jarvis-team（個人 Telegram Bot 助理）的 Main Jarvis 建立**技能樹式的個人知識庫**：

- 不只是記 note，而是要**描繪對各領域知識的理解程度**
- 像技能樹一樣，有階層、有分支、可擴展
- 每個節點有 level（heard_of / can_use / can_teach / expert）、evidence（做過什麼）、gaps（已知的未知）

### 技能樹 schema（草案）

```
{
  "domain_path": "python/packaging/entry-points",
  "level": "can_use",
  "confidence": "high",
  "last_touched": "2026-04-11",
  "evidence": [
    "修好 agent-fix pyproject.toml entry point bug (cli:main)",
    "理解 module:function 格式 vs file.py:function 差異"
  ],
  "gaps": [
    "沒用過 setuptools entry_points",
    "不清楚 console_scripts vs gui_scripts 差別"
  ]
}
```

### 從這次 session 可提煉的 seed entries

```
python/packaging/
├── pyproject-toml/
│   ├── [project.scripts] entry points
│   └── hatch.build.targets.wheel include/packages
├── dependency-management/
│   ├── uv sync vs pip install 差異
│   ├── uv run 的 venv 自動解析機制
│   └── optional-dependencies groups
└── module-loading/
    ├── module-level code 在 import 時執行的陷阱
    ├── sys.exit(1) 在 import 時會殺掉所有 subcommands
    └── __file__-relative paths vs cwd-relative paths
```

### 實作路徑選項

| 階段 | 做法 | 說明 |
|------|------|------|
| **短期 MVP** | 用 Main Jarvis 現有 `saveNote` + tag 約定（`kb:python/packaging/...`） | 零改動，先累積資料驗證 schema |
| **中期** | jarvis-team 新增 `knowledge[]` 欄位 + `saveKnowledge` tool | 累積 20+ 筆後，確認 schema 穩定再做 |
| **長期** | 視覺化技能樹 dashboard + 跨 session 自動摘要注入 | 需要 MCP / API 整合 |

### 與 agent-fix retro 的潛在關聯

Retro 產出的技術知識（例：「原來 Pydantic `any` 是 built-in function 不是 `typing.Any`」）可以是知識庫的 input 來源之一。但兩者獨立發展，不必綁定。

### 待決策

1. Schema 先用 tag 約定（方案 A）還是直接改 jarvis-team（方案 B）？
2. 技能樹範圍：只記技術？還是涵蓋軟技能、專案知識、管理？
3. 知識進入方式：手動告知 Main Jarvis + 批次整理 vs 自動化？
4. 我（Claude Code）要不要直接寫 `main-jarvis-memory.json`？還是產出 draft 讓使用者手動轉交？

---

<!-- 下一個 brainstorm 在這裡接續 -->
