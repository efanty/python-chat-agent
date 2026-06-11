"""deep-research-pro Skill — 深度调研工作流。

不直接执行操作，而是提供调研方法论的说明供 LLM 参考。
实际的搜索调用通过 skill__web_search 完成。
"""

import json


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """获取深度调研工作流说明。

    Args:
        expression: 调研主题
        action: "run"（默认）— 返回调研方法说明

    Returns:
        调研工作流说明文本
    """
    topic = expression or kwargs.get("topic", "")
    return json.dumps({
        "success": True,
        "message": "深度调研工作流已加载，请遵循 SKILL.md 中的步骤执行。"
                    "使用 skill__web_search 进行搜索，使用 sandbox_write_file 保存报告。",
        "topic": topic,
    }, ensure_ascii=False)
