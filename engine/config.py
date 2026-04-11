"""
通用專案配置模型
支援從 YAML 載入專案特定配置
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class MonorepoConfig(BaseModel):
    """Monorepo 配置"""
    tool: Literal["turborepo", "yarn-workspaces", "npm-workspaces", "pnpm-workspaces"] = Field(
        description="Monorepo 工具"
    )
    main_workspace: str = Field(
        description="主要 workspace 名稱（用於執行命令）"
    )
    workspaces: List[str] = Field(
        default=["apps/*", "packages/*"],
        description="Workspace glob 模式列表"
    )


class PathsConfig(BaseModel):
    """路徑配置"""
    root: str = Field(
        description="專案根目錄路徑（相對於 workflow 根目錄）"
    )
    shared_packages: List[str] = Field(
        default=[],
        description="共用套件路徑列表（高風險區域）"
    )
    shared_components: List[str] = Field(
        default=[],
        description="共用元件路徑列表（中風險區域）"
    )
    isolated_modules: List[str] = Field(
        default=[],
        description="獨立模組路徑列表（低風險區域）"
    )
    domain_logic: List[str] = Field(
        default=[],
        description="領域邏輯路徑列表"
    )


class CommandConfig(BaseModel):
    """命令配置"""
    command: str = Field(description="執行命令")
    enabled: bool = Field(default=True, description="是否啟用")


class QualityChecksConfig(BaseModel):
    """品質檢查配置"""
    typescript: CommandConfig = Field(
        description="TypeScript 型別檢查"
    )
    eslint: CommandConfig = Field(
        description="ESLint 程式碼檢查"
    )
    prettier: Optional[CommandConfig] = Field(
        default=None,
        description="Prettier 格式檢查（可選）"
    )
    tests: Optional[CommandConfig] = Field(
        default=None,
        description="測試執行（可選）"
    )


class CodingStandardsConfig(BaseModel):
    """程式碼規範配置"""
    naming: Dict[str, str] = Field(
        default={
            "variables": "camelCase",
            "functions": "camelCase",
            "constants": "UPPER_CASE",
            "components": "PascalCase",
            "types": "PascalCase"
        },
        description="命名規範"
    )
    file_patterns: Dict[str, str] = Field(
        default={},
        description="檔案命名模式"
    )


class SkillsConfig(BaseModel):
    """Skills 配置"""
    directories: List[str] = Field(
        default=[],
        description="Skills 目錄路徑列表（相對或絕對路徑）"
    )
    coding_standards_skill: Optional[str] = Field(
        default=None,
        description="Coding standards skill 名稱（可選，如 vercel-react-best-practices）"
    )


class ProjectConfig(BaseModel):
    """專案配置（從 YAML 載入）"""
    
    project_name: str = Field(
        description="專案名稱"
    )
    framework: Literal[
        "nextjs-15-app-router",
        "nextjs-14-pages-router",
        "nextjs-13-app-router",
        "react-vite",
        "react-cra"
    ] = Field(
        description="前端框架"
    )
    language: Literal["typescript", "javascript"] = Field(
        default="typescript",
        description="程式語言"
    )
    issue_prefix: str = Field(
        default="BUG",
        description="Issue ID 前綴（如 BUG-1234, PROJ-5678）"
    )
    monorepo: Optional[MonorepoConfig] = Field(
        default=None,
        description="Monorepo 配置（如果是 monorepo 專案）"
    )
    paths: PathsConfig = Field(
        description="路徑配置"
    )
    high_risk_keywords: List[str] = Field(
        default=[],
        description="高風險關鍵字列表"
    )
    quality_checks: QualityChecksConfig = Field(
        description="品質檢查配置"
    )
    coding_standards: CodingStandardsConfig = Field(
        default_factory=CodingStandardsConfig,
        description="程式碼規範"
    )
    skills: SkillsConfig = Field(
        default_factory=SkillsConfig,
        description="Skills 配置"
    )
    dev_server: Optional[Dict[str, Any]] = Field(
        default={"port": 3001, "command": None},
        description="開發伺服器配置"
    )
    
    @field_validator('issue_prefix')
    @classmethod
    def validate_issue_prefix(cls, v: str) -> str:
        """驗證 issue_prefix 格式"""
        if not v or not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError(f"Invalid issue_prefix: {v}. Must be alphanumeric (with optional - or _)")
        return v.upper()
    
    @model_validator(mode='after')
    def validate_monorepo_consistency(self):
        """驗證 monorepo 配置一致性"""
        if self.monorepo:
            # 如果是 monorepo，確保命令中包含 workspace 引用
            ts_cmd = self.quality_checks.typescript.command
            if "workspace" not in ts_cmd and "{{main_workspace}}" not in ts_cmd:
                # 自動補充 workspace 前綴（如果需要）
                pass
        return self
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'ProjectConfig':
        """
        從 YAML 檔案載入配置
        
        Args:
            config_path: YAML 配置檔案路徑
            
        Returns:
            ProjectConfig 實例
            
        Raises:
            FileNotFoundError: 配置檔案不存在
            ValueError: YAML 格式錯誤或驗證失敗
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please create a config file. See examples/ directory for templates."
            )
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                yaml_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML format in {config_path}: {e}")
        
        if not yaml_data:
            raise ValueError(f"Empty configuration file: {config_path}")
        
        # 處理變數替換（如 {{main_workspace}}）
        yaml_data = cls._resolve_template_variables(yaml_data)
        
        try:
            return cls(**yaml_data)
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {e}")
    
    @staticmethod
    def _resolve_template_variables(data: dict) -> dict:
        """
        解析模板變數（如 {{main_workspace}}）
        
        Args:
            data: 原始配置資料
            
        Returns:
            解析後的配置資料
        """
        import copy
        import re
        
        resolved_data = copy.deepcopy(data)
        
        # 取得變數值
        variables = {}
        if 'monorepo' in data and data['monorepo']:
            variables['main_workspace'] = data['monorepo'].get('main_workspace', '')
        variables['project_name'] = data.get('project_name', '')
        
        def replace_variables(obj):
            """遞迴替換物件中的變數"""
            if isinstance(obj, dict):
                return {k: replace_variables(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_variables(item) for item in obj]
            elif isinstance(obj, str):
                # 替換 {{variable}} 模式
                for var_name, var_value in variables.items():
                    pattern = r'\{\{' + var_name + r'\}\}'
                    obj = re.sub(pattern, var_value, obj)
                return obj
            else:
                return obj
        
        return replace_variables(resolved_data)
    
    def get_project_root(self) -> Path:
        """取得專案根目錄的絕對路徑"""
        return Path(self.paths.root).resolve()
    
    def get_workspace_command(self, base_command: str) -> str:
        """
        產生 workspace 命令
        
        Args:
            base_command: 基礎命令（如 "tsc", "lint"）
            
        Returns:
            完整的 workspace 命令
        """
        if self.monorepo:
            tool = self.monorepo.tool
            workspace = self.monorepo.main_workspace
            
            if tool == "turborepo":
                return f"turbo run {base_command}"
            elif tool in ["yarn-workspaces", "npm-workspaces", "pnpm-workspaces"]:
                pkg_manager = tool.split('-')[0]
                return f"{pkg_manager} workspace {workspace} {base_command}"
        
        # 非 monorepo 或無法判斷
        return base_command
    
    def validate_project_structure(self) -> List[str]:
        """
        驗證專案結構是否符合配置
        
        Returns:
            警告訊息列表（空列表表示通過）
        """
        warnings = []
        project_root = self.get_project_root()
        
        # 檢查專案根目錄
        if not project_root.exists():
            warnings.append(f"Project root does not exist: {project_root}")
            return warnings  # 根目錄不存在，無法繼續檢查
        
        # 檢查 package.json
        package_json = project_root / "package.json"
        if not package_json.exists():
            warnings.append(f"package.json not found in {project_root}")
        
        # 檢查 monorepo 配置
        if self.monorepo:
            if self.monorepo.tool == "turborepo":
                turbo_json = project_root / "turbo.json"
                if not turbo_json.exists():
                    warnings.append(f"turbo.json not found (monorepo.tool=turborepo)")
        
        # 檢查路徑是否存在
        for path_type, paths in [
            ("shared_packages", self.paths.shared_packages),
            ("shared_components", self.paths.shared_components),
            ("isolated_modules", self.paths.isolated_modules),
        ]:
            for path in paths:
                full_path = project_root / path
                if not full_path.exists():
                    warnings.append(f"{path_type} path does not exist: {path}")
        
        return warnings


class ConfigurationError(Exception):
    """配置錯誤例外"""
    pass


def load_config_from_env() -> ProjectConfig:
    """
    從環境變數載入配置
    
    Returns:
        ProjectConfig 實例
        
    Raises:
        ConfigurationError: 缺少必要環境變數或配置無效
    """
    config_path = os.getenv("PROJECT_CONFIG")
    
    if not config_path:
        raise ConfigurationError(
            "PROJECT_CONFIG environment variable is required.\n"
            "Example: export PROJECT_CONFIG=./config/your-project.yaml"
        )
    
    try:
        return ProjectConfig.from_yaml(config_path)
    except (FileNotFoundError, ValueError) as e:
        raise ConfigurationError(f"Failed to load configuration: {e}")


# 使用範例
if __name__ == "__main__":
    # 測試配置載入
    import sys
    
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        try:
            config = ProjectConfig.from_yaml(config_path)
            print(f"✅ Configuration loaded successfully")
            print(f"   Project: {config.project_name}")
            print(f"   Framework: {config.framework}")
            print(f"   Root: {config.get_project_root()}")
            
            # 驗證專案結構
            warnings = config.validate_project_structure()
            if warnings:
                print(f"\n⚠️  Warnings:")
                for warning in warnings:
                    print(f"   - {warning}")
            else:
                print(f"\n✅ Project structure validation passed")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python config.py <config-file.yaml>")
        sys.exit(1)
