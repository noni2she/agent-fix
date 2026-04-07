"""
通用專案規格產生器
基於 ProjectConfig 產生 Agent 所需的架構定義和決策邏輯
"""
from pathlib import Path
from typing import Dict, Tuple

from .config import ProjectConfig


class ProjectSpec:
    """通用專案規格（配置驅動）"""
    
    def __init__(self, config: ProjectConfig):
        """
        初始化專案規格
        
        Args:
            config: 從 YAML 載入的專案配置
        """
        self.config = config
        self.project_root = config.get_project_root()
        self.spec = self._generate_spec()
    
    def _generate_spec(self) -> Dict:
        """產生完整的專案規格（從配置轉換）"""
        return {
            "project_name": self.config.project_name,
            "framework": self.config.framework,
            "language": self.config.language,
            "issue_prefix": self.config.issue_prefix,
            "monorepo": self.config.monorepo.model_dump() if self.config.monorepo else None,
            "paths": self.config.paths.model_dump(),
            "high_risk_keywords": self.config.high_risk_keywords,
            "quality_checks": {
                "typescript": self.config.quality_checks.typescript.model_dump(),
                "eslint": self.config.quality_checks.eslint.model_dump(),
                "prettier": self.config.quality_checks.prettier.model_dump() if self.config.quality_checks.prettier else None,
                "tests": self.config.quality_checks.tests.model_dump() if self.config.quality_checks.tests else None,
            },
            "coding_standards": self.config.coding_standards.model_dump()
        }
    
    def get_architecture_context(self) -> str:
        """產生給 Engineer Agent 的架構說明"""
        monorepo_info = ""
        if self.config.monorepo:
            monorepo_info = f"""
## 1. 專案結構
- **Monorepo 工具**: {self.config.monorepo.tool}
- **主要 Workspace**: {self.config.monorepo.main_workspace}
- **前端框架**: {self._get_framework_display()} + {self.config.language.upper()}
"""
        else:
            monorepo_info = f"""
## 1. 專案結構
- **專案類型**: 單一專案
- **前端框架**: {self._get_framework_display()} + {self.config.language.upper()}
"""
        
        paths_info = self._format_paths_info()
        keywords_info = self._format_keywords_info()
        standards_info = self._format_coding_standards()
        commands_info = self._format_quality_commands()
        
        return f"""
# {self.config.project_name} 專案架構規範
{monorepo_info}
## 2. 路徑分類與修復策略

{paths_info}

## 3. 高風險關鍵字
{keywords_info}

## 4. 程式碼規範
{standards_info}

## 5. 品質檢查指令
{commands_info}
"""
    
    def _get_framework_display(self) -> str:
        """取得框架顯示名稱"""
        framework_map = {
            "nextjs-15-app-router": "Next.js 15 (App Router)",
            "nextjs-14-pages-router": "Next.js 14 (Pages Router)",
            "nextjs-13-app-router": "Next.js 13 (App Router)",
            "react-vite": "React + Vite",
            "react-cra": "React (Create React App)"
        }
        return framework_map.get(self.config.framework, self.config.framework)
    
    def _format_paths_info(self) -> str:
        """格式化路徑資訊"""
        lines = []
        
        if self.config.paths.shared_packages:
            lines.append("### 🔴 共用套件 (Shared Packages) - 高風險")
            lines.append(f"路徑: {', '.join(self.config.paths.shared_packages)}")
            lines.append("**策略**: 必須使用 Tactical Fix (在呼叫端隔離修復)\n")
        
        if self.config.paths.shared_components:
            lines.append("### 🟡 共用元件 (Shared Components) - 中風險")
            lines.append(f"路徑: {', '.join(self.config.paths.shared_components)}")
            lines.append("**策略**: ")
            lines.append("- 如果影響 > 3 個模組 → Tactical Fix")
            lines.append("- 如果影響 ≤ 3 個模組 → Direct Fix\n")
        
        if self.config.paths.isolated_modules:
            lines.append("### 🟢 獨立模組 (Isolated Modules) - 低風險")
            lines.append(f"路徑: {', '.join(self.config.paths.isolated_modules)}")
            lines.append("**策略**: Direct Fix (直接修改)\n")
        
        return '\n'.join(lines) if lines else "（無特定路徑分類）"
    
    def _format_keywords_info(self) -> str:
        """格式化高風險關鍵字資訊"""
        if self.config.high_risk_keywords:
            return f"遇到以下關鍵字時需特別謹慎:\n{', '.join(self.config.high_risk_keywords)}"
        return "（無特定高風險關鍵字）"
    
    def _format_coding_standards(self) -> str:
        """格式化程式碼規範"""
        lines = []
        
        # 命名規範
        if self.config.coding_standards.naming:
            lines.append("**命名規範**:")
            for key, value in self.config.coding_standards.naming.items():
                lines.append(f"- {key.capitalize()}: {value}")
        
        # 檔案模式
        if self.config.coding_standards.file_patterns:
            lines.append("\n**檔案命名模式**:")
            for key, pattern in self.config.coding_standards.file_patterns.items():
                lines.append(f"- {key}: `{pattern}`")
        
        return '\n'.join(lines) if lines else "（使用預設規範）"
    
    def _format_quality_commands(self) -> str:
        """格式化品質檢查命令"""
        lines = []
        
        if self.config.quality_checks.typescript.enabled:
            lines.append(f"- TypeScript: `{self.config.quality_checks.typescript.command}`")
        
        if self.config.quality_checks.eslint.enabled:
            lines.append(f"- ESLint: `{self.config.quality_checks.eslint.command}`")
        
        if self.config.quality_checks.prettier and self.config.quality_checks.prettier.enabled:
            lines.append(f"- Prettier: `{self.config.quality_checks.prettier.command}`")
        
        if self.config.quality_checks.tests and self.config.quality_checks.tests.enabled:
            lines.append(f"- Tests: `{self.config.quality_checks.tests.command}`")
        
        return '\n'.join(lines) if lines else "（無配置的品質檢查）"
    
    def should_use_tactical_fix(self, file_path: str, impacted_count: int) -> Tuple[bool, str]:
        """
        判斷是否應使用戰術性修復
        
        Args:
            file_path: 檔案路徑（相對於專案根目錄）
            impacted_count: 受影響的模組數量
        
        Returns:
            (should_use_tactical, reason) 元組
        """
        # 檢查是否在共用套件
        for shared_pkg in self.config.paths.shared_packages:
            if file_path.startswith(shared_pkg):
                return True, f"檔案位於共用套件: {shared_pkg}"
        
        # 檢查是否在共用元件且影響範圍大
        for shared_comp in self.config.paths.shared_components:
            if file_path.startswith(shared_comp) and impacted_count > 3:
                return True, f"共用元件被 {impacted_count} 個模組引用 (超過安全閾值 3)"
        
        # 檢查是否包含高風險關鍵字
        for keyword in self.config.high_risk_keywords:
            if keyword.lower() in file_path.lower():
                return True, f"檔案路徑包含高風險關鍵字: {keyword}"
        
        return False, "影響範圍有限，可直接修改"
    
    def get_typecheck_command(self) -> str:
        """取得 TypeScript 型別檢查命令"""
        return self.config.quality_checks.typescript.command
    
    def get_lint_command(self) -> str:
        """取得 ESLint 檢查命令"""
        return self.config.quality_checks.eslint.command
    
    def get_test_command(self) -> str:
        """取得測試命令（如果有）"""
        if self.config.quality_checks.tests:
            return self.config.quality_checks.tests.command
        return None
    
    def get_main_workspace(self) -> str:
        """取得主要 workspace 名稱"""
        if self.config.monorepo:
            return self.config.monorepo.main_workspace
        return None
    
    def to_dict(self) -> Dict:
        """轉換為字典"""
        return self.spec


# 使用範例
if __name__ == "__main__":
    import sys
    from .config import ProjectConfig
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        
        try:
            # 載入配置
            config = ProjectConfig.from_yaml(config_path)
            
            # 建立專案規格
            spec = ProjectSpec(config)
            
            # 顯示架構說明
            print("="*60)
            print(spec.get_architecture_context())
            print("="*60)
            
            # 測試決策邏輯
            print("\n# 決策邏輯測試")
            test_cases = [
                ("packages/api-client/src/auth.ts", 5),
                ("apps/main-app/src/components/Button.tsx", 2),
                ("apps/main-app/src/app/home/page.tsx", 1),
            ]
            
            for file_path, impact_count in test_cases:
                should_tactical, reason = spec.should_use_tactical_fix(file_path, impact_count)
                strategy = "🔴 Tactical Fix" if should_tactical else "🟢 Direct Fix"
                print(f"\n{strategy}")
                print(f"  檔案: {file_path}")
                print(f"  影響: {impact_count} 個模組")
                print(f"  原因: {reason}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python project_spec.py <config-file.yaml>")
        sys.exit(1)
