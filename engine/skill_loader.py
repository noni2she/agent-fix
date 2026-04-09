"""
Skill Loader 模組
從 SKILL.md 讀取並解析 skill 定義 (frontmatter + body)

skills_dir 必須由呼叫端傳入（從 config.skills.directories 取得），
沒有預設硬編碼路徑。
"""
from pathlib import Path
import yaml


def load_skill(skill_name: str, skills_dir: Path) -> tuple[dict, str]:
    """
    載入 skill 定義

    Args:
        skill_name: Skill 名稱（對應 skills/ 下的子目錄名稱）
        skills_dir: Skills 根目錄（從 ProjectConfig.skills.directories 取得）

    Returns:
        (metadata, body) 元組
        - metadata: YAML frontmatter 解析結果
        - body: skill 主體內容（作為 system prompt 注入）

    Raises:
        FileNotFoundError: SKILL.md 不存在
        ValueError: SKILL.md 格式錯誤
    """
    skill_path = Path(skills_dir) / skill_name / "SKILL.md"

    if not skill_path.exists():
        raise FileNotFoundError(
            f"Skill not found: {skill_path}\n"
            f"Check config.skills.directories points to the correct skills directory."
        )

    content = skill_path.read_text(encoding='utf-8')
    parts = content.split('---', 2)

    if len(parts) < 3:
        raise ValueError(
            f"Invalid SKILL.md format (missing --- frontmatter): {skill_path}"
        )

    metadata = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    return metadata, body
