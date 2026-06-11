"""skill_creator Skill — 为当前项目创建新的 Skill。

管理员可以通过对话让智能体调用此工具来创建新的技能。
每个 Skill 包含 skills/<folder_name>/ 下的 SKILL.md 和 .py 文件，
并自动注册到管理后台的 Skills 管理数据库中。
"""

import os
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

from app.utils.time_utils import beijing_now
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _PROJECT_ROOT / "skills"


def _safe_folder_name(text: str) -> str:
    """将名称转为安全的文件夹名（小写字母数字连字符）。"""
    text = text.strip().lower()
    text = re.sub(r"[^\w\-]", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "new-skill"


def _skill_folder_exists(folder_name: str) -> bool:
    """检查 skills/<folder_name>/ 是否已存在。"""
    return (_SKILLS_DIR / folder_name).is_dir()


def _create_skill_files(folder_name: str, name: str, description: str,
                        py_content: str, md_content: str) -> list:
    """创建 SKILL.md 和 .py 文件，返回创建的文件路径列表。"""
    folder = _SKILLS_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    created = []

    # SKILL.md
    md_path = folder / "SKILL.md"
    md_path.write_text(md_content, encoding="utf-8")
    created.append(str(md_path))

    # .py file
    py_path = folder / f"{folder_name}.py"
    py_path.write_text(py_content, encoding="utf-8")
    created.append(str(py_path))

    (folder / "__init__.py").write_text("", encoding="utf-8")

    return created


# ── Flask app context 辅助（线程安全） ────────────────────────────────

def _ensure_app_context():
    from flask import current_app
    try:
        _ = current_app.name
        return None
    except RuntimeError:
        pass
    try:
        from app import create_app
        app = create_app()
        ctx = app.app_context()
        ctx.push()
        return ctx
    except Exception:
        raise RuntimeError("无法创建 Flask 应用上下文")

def _cleanup_context(ctx):
    if ctx is not None:
        ctx.pop()


def _register_in_db(folder_name: str, name: str, description: str) -> str:
    """在数据库中注册 Skill，返回注册信息。"""
    ctx = _ensure_app_context()
    try:
        from app.extensions.init_sqlalchemy import db
        from app.models.skill import Skill

        # Check if already registered
        existing = Skill.query.filter_by(folder_name=folder_name).first()
        if existing:
            existing.name = name
            existing.description = description
            existing.is_active = True
            existing.updated_at = beijing_now()
            db.session.commit()
            return f"已更新数据库记录（原有 id={existing.id}）"

        skill = Skill(
            name=name,
            description=description,
            folder_name=folder_name,
            is_active=True,
        )
        db.session.add(skill)
        db.session.commit()
        return f"已在数据库注册（id={skill.id}）"
    except Exception as e:
        return f"数据库注册失败（需在管理后台手动注册）: {e}"
    finally:
        _cleanup_context(ctx)


# ── 模板 ─────────────────────────────────────────────────────────────────

PYTHON_TEMPLATE = '''\"\"\"{name} Skill — {description}

通过 SkillExecutor 加载执行。
\"""

import json


def run(expression: str = "", action: str = "", **kwargs) -> str:
    \"\"\"{name} — {description}

    Args:
        expression: 主参数
        action:     操作类型
        **kwargs:   其他参数

    Returns:
        JSON 字符串
    \"\"\"
    # ← 在此处实现你的逻辑
    prompt = kwargs.get("prompt", "") or expression or ""
    return json.dumps({{
        "success": True,
        "message": "功能待实现",
        "prompt": prompt,
    }}, ensure_ascii=False)
'''

SKILL_MD_TEMPLATE = '''---
name: {name}
description: {description}
version: 1.0
author: DeepAgent Team
requires: （请补充需要的环境变量，如 ZHIPU_API_KEY）
parameters:
  - name: prompt
    type: string
    description: （请编辑补充参数说明）
    required: true
---

# {name}

{description}

## 能力

- （请编辑补充）

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 说明 |
|------|------|------|------|------|
| `prompt` | string | 是 | — | （请编辑补充） |

### 调用示例

```json
{{
  "prompt": ""
}}
```

### 返回格式

```json
{{
  "success": true,
  "result": "..."
}}
```

## 安全限制

- 注意限制敏感操作
'''



# ── 入口函数 ──────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """创建新的 Skill。

    创建 skills/<folder_name>/ 下的 SKILL.md 和 .py 文件，
    并在数据库中注册。

    Args:
        expression: JSON 字符串或空
        action:     "run"（默认，创建 skill）
        **kwargs:
            name:        Skill 名称（用于显示）
            description: Skill 描述（一句话说明）
            folder_name: 文件夹名（可选，自动从 name 生成）
            py_content:  Python 代码（可选，使用默认模板）
            md_content:  SKILL.md 内容（可选，使用默认模板）

    Returns:
        JSON: {"success": true, "folder": "...", "files": [...], "registered": "..."}
    """
    # ── 解析参数 ─────────────────────────────────────────────────────
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    name = params.get("name") or kwargs.get("name", "").strip()
    description = params.get("description") or kwargs.get("description", "").strip()
    folder_name = params.get("folder_name") or kwargs.get("folder_name", "").strip()

    # 也可从 expression 取纯文本
    if not name and expression and not expression.startswith("{"):
        lines = expression.strip().split("\n")
        name = lines[0].strip()[:80]
        if not description and len(lines) > 1:
            description = lines[1].strip()[:200]

    if not name:
        return json.dumps({
            "success": False,
            "error": "缺少必需参数 name（Skill 名称）",
            "usage": '调用方式: run(name="工具名", description="一句话描述", folder_name="文件夹名")',
        }, ensure_ascii=False)

    if not description:
        return json.dumps({
            "success": False,
            "error": "缺少必需参数 description（Skill 描述）",
        }, ensure_ascii=False)

    if not folder_name:
        folder_name = _safe_folder_name(name)

    # ── 检查是否已存在 ───────────────────────────────────────────────
    if _skill_folder_exists(folder_name):
        return json.dumps({
            "success": False,
            "error": f"文件夹 skills/{folder_name}/ 已存在",
            "hint": "请使用不同的 name 或指定不同的 folder_name",
        }, ensure_ascii=False)

    # ── 准备内容 ─────────────────────────────────────────────────────
    py_content = params.get("py_content") or kwargs.get("py_content", "")
    if not py_content:
        py_content = PYTHON_TEMPLATE.format(name=name, description=description)

    md_content = params.get("md_content") or kwargs.get("md_content", "")
    if not md_content:
        md_content = SKILL_MD_TEMPLATE.format(
            folder_name=folder_name,
            name=name,
            description=description,
        )

    # ── 创建文件 ─────────────────────────────────────────────────────
    try:
        files = _create_skill_files(folder_name, name, description, py_content, md_content)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"创建文件失败: {e}",
        }, ensure_ascii=False)

    # ── 注册数据库 ───────────────────────────────────────────────────
    try:
        reg_info = _register_in_db(folder_name, name, description)
    except Exception:
        reg_info = "数据库注册失败，请在管理后台手动注册"

    # ── 通知管理员下一步 ─────────────────────────────────────────────
    result = {
        "success": True,
        "name": name,
        "folder": f"skills/{folder_name}/",
        "files": files,
        "registered": reg_info,
        "next_steps": [
            "1. 编辑 .py 文件实现具体逻辑",
            "2. 如果需要，更新 SKILL.md 完善参数说明",
            f"3. 在管理后台「智能体管理」中将此 Skill 绑定到智能体",
        ],
    }
    return json.dumps(result, ensure_ascii=False)
