"""interview-simulator Skill — 模拟面试。

提供一个结构化面试模拟环境，支持各类职业和级别。
"""

import json


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """开始或配置模拟面试。

    Args:
        expression: 面试请求文本，如 "Mock interview for Backend Engineer"
        action: "run"（默认）
        **kwargs:
            role: 职位名称
            level: 经验级别
            focus: 侧重点
            duration: 时长

    Returns:
        面试配置确认信息
    """
    role = expression or kwargs.get("role", "")
    level = kwargs.get("level", "")
    focus = kwargs.get("focus", "")

    if not role:
        return json.dumps({
            "success": True,
            "message": "面试模拟器已就绪。请告诉我：\n"
                       "1. 你想面试什么职位？\n"
                       "2. 你的经验级别？\n"
                       "3. 有没有侧重点？\n"
                       "4. 希望多长时间？",
        }, ensure_ascii=False)

    parts = [f"职位: {role}"]
    if level:
        parts.append(f"级别: {level}")
    if focus:
        parts.append(f"侧重点: {focus}")

    return json.dumps({
        "success": True,
        "message": "已配置模拟面试，请查看 SKILL.md 了解面试流程和评分标准。",
        "config": {
            "role": role,
            "level": level,
            "focus": focus,
        },
    }, ensure_ascii=False)
