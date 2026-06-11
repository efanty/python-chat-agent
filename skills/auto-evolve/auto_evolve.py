import os, json, datetime
from pathlib import Path
from typing import Dict, Any

# 项目根目录（基于此文件位置向上 3 级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 学习记录文件路径（使用绝对路径）
_LEARNINGS_FILE = _PROJECT_ROOT / "role" / "learnings.md"


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """自动进化 — 创建技能、记录学习笔记、列出技能。

    Args:
        action: "create_skill" / "record_learning" / "list_skills"
        **kwargs: 各 action 对应的参数
    """
    action = action or kwargs.get("action", "")

    if action == "create_skill":
        return json.dumps(create_skill(
            name=kwargs.get("name", ""),
            description=kwargs.get("description", ""),
            instructions=kwargs.get("instructions", ""),
            tool_code=kwargs.get("tool_code", ""),
        ), ensure_ascii=False)
    elif action == "record_learning":
        return json.dumps(record_learning(
            topic=kwargs.get("topic", ""),
            content=kwargs.get("content", "") or expression,
        ), ensure_ascii=False)
    elif action == "list_skills":
        return json.dumps(list_skills(), ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": f"未知 action: {action}，支持: create_skill, record_learning, list_skills"
        }, ensure_ascii=False)


def create_skill(name: str, description: str, instructions: str,
                 tool_code: str = "") -> Dict[str, Any]:
    """
    创建新的技能（Skill），让智能体学会新的能力。

    Args:
        name: 技能名称（英文小写，用连字符连接，如 "file-converter"）
        description: 简短的功能描述（用于 SKILL.md frontmatter）
        instructions: 详细的使用说明（markdown 正文）
        tool_code: 可选的 Python 工具函数代码

    Returns:
        创建结果
    """
    skill_dir = _PROJECT_ROOT / "skills" / "custom_skills" / name
    if skill_dir.exists():
        return {"status": "error", "message": f"Skill '{name}' 已存在"}

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)

        # SKILL.md
        skill_md = f"""---
name: {name}
description: "{description}"
---

# {name} Skill

## Instructions

{instructions}
"""
        (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        # .py tool stub
        if tool_code:
            (skill_dir / f"{name.replace('-', '_')}.py").write_text(tool_code, encoding="utf-8")

        return {
            "status": "success",
            "message": f"Skill '{name}' 已创建于 skills/custom_skills/{name}/",
            "note": "技能已创建。SkillManager 会在下次启动时自动发现并注册，无需修改代码。",
        }
    except Exception as e:
        return {"status": "error", "message": f"创建失败: {e}"}


def record_learning(topic: str, content: str) -> Dict[str, Any]:
    """
    记录一条学习笔记，保存到 role/learnings.md 中。

    当你在对话中学到了用户的重要偏好、发现处理某类问题更有效的方法、
    或者总结了优化的技巧时，用这个工具记录下来。下次启动时会自动加载。

    Args:
        topic: 学习主题（如 "用户偏好"、"处理技巧"、"优化记录"）
        content: 学习内容

    Returns:
        保存结果
    """
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n## {topic}\n- **时间**: {now}\n- **内容**: {content}\n"

        _LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

        if _LEARNINGS_FILE.exists():
            existing = _LEARNINGS_FILE.read_text(encoding="utf-8")
            _LEARNINGS_FILE.write_text(existing + entry, encoding="utf-8")
        else:
            header = "# 小薇的学习笔记\n\n*这些笔记由智能体自动记录，用于持续优化对话质量*\n"
            _LEARNINGS_FILE.write_text(header + entry, encoding="utf-8")

        return {"status": "success", "message": f"学习笔记已保存: {topic}"}
    except Exception as e:
        return {"status": "error", "message": f"保存失败: {e}"}


def list_skills() -> Dict[str, Any]:
    """
    列出当前所有可用的技能目录及其 SKILL.md 的描述。

    Returns:
        技能列表
    """
    skills_dir = _PROJECT_ROOT / "skills" / "custom_skills"
    if not skills_dir.is_dir():
        return {"status": "error", "message": "skills 目录不存在"}

    results = []
    for d in sorted(skills_dir.iterdir()):
        if d.is_dir():
            sk = d / "SKILL.md"
            if sk.exists():
                desc = ""
                for line in sk.read_text(encoding="utf-8").splitlines():
                    if line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip().strip('"')
                        break
                results.append({"name": d.name, "description": desc})
    return {"status": "success", "skills": results, "total": len(results)}
