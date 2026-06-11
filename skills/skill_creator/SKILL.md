---
name: skill_creator
description: 创建一个适用于本项目的新 Skill，包括文件结构和数据库注册
version: 1.0
author: DeepAgent Team
parameters:
  - name: name
    type: string
    description: Skill 名称（用于显示），如"天气查询"
    required: true
  - name: description
    type: string
    description: 一句话描述这个 Skill 的功能
    required: true
  - name: folder_name
    type: string
    description: 文件夹名（可选，自动从 name 生成小写加下划线格式）
  - name: py_content
    type: string
    description: 自定义 Python 代码（可选，使用默认模板）
  - name: md_content
    type: string
    description: 自定义 SKILL.md 内容（可选，使用默认模板）
---

# Skill Creator (skill_creator)

创建新的 Skill：在 `skills/<folder_name>/` 目录下生成 `SKILL.md` 和 `.py` 文件，并自动在数据库中注册。
创建完成后，管理员只需编辑 `.py` 文件实现具体逻辑，然后在智能体管理中绑定即可使用。

## 能力

- 创建 Skill 文件夹和文件结构（SKILL.md + .py）
- 自动使用默认模板生成代码和文档
- 在项目数据库中注册 Skill（可在管理后台看到）
- 支持自定义 Python 代码和 MD 内容
- 自动检测文件夹冲突，避免覆盖已有 Skill

## 使用方式

### 必需参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | Skill 名称（用于显示），如"天气查询" |
| `description` | string | 一句话描述这个 Skill 的功能 |

### 可选参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `folder_name` | string | 文件夹名（自动从 name 生成，如 `weather-query`） |
| `py_content` | string | 自定义 Python 代码（使用默认模板） |
| `md_content` | string | 自定义 SKILL.md 内容（使用默认模板） |

### 调用示例

最简单的用法（使用默认模板）：

```json
{
  "name": "天气查询",
  "description": "根据城市名查询实时天气信息，包括温度、湿度、风速等"
}
```

自定义 Python 代码：

```json
{
  "name": "翻译工具",
  "description": "调用翻译 API 将文本翻译为目标语言",
  "folder_name": "translate_text",
  "py_content": "import json\nimport requests\n\ndef run(expression, action, **kwargs):\n    prompt = kwargs.get('prompt', '') or expression or ''\n    return json.dumps({'success': True, 'result': prompt})"
}
```

### 返回格式

```json
{
  "success": true,
  "name": "天气查询",
  "folder": "skills/weather_query/",
  "files": [
    "skills/weather_query/SKILL.md",
    "skills/weather_query/weather_query.py"
  ],
  "registered": "已在数据库注册（id=12）",
  "next_steps": [
    "1. 编辑 .py 文件实现具体逻辑",
    "2. 如果需要，更新 SKILL.md 完善参数说明",
    "3. 在管理后台「智能体管理」中将此 Skill 绑定到智能体"
  ]
}
```

## 安全限制

- 需要在 Flask 应用上下文中运行才能注册数据库
- 禁止创建名称与已有 Skill 重复的文件夹
- 文件夹名自动转为小写字母数字下划线格式
