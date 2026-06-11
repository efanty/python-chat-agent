# DeepAgent Chat — Skill 开发指南

## 目录

- [概述](#概述)
- [目录结构](#目录结构)
- [SKILL.md —— 描述文件](#skillmd--描述文件)
- [Python 辅助文件](#python-辅助文件)
- [参数传递](#参数传递)
- [注册与使用](#注册与使用)
- [最佳实践](#最佳实践)
- [现有 Skill 参考](#现有-skill-参考)

---

## 概述

Skill 是 DeepAgent Chat 的功能扩展单元。一个 Skill 封装一组相关能力（如"执行 SQL 查询"、"发送邮件"），智能体（Agent）可以根据对话需要自动调用。

Skill 遵循以下原则：

- **每个 Skill 一个独立文件夹**，位于 `skills/<folder_name>/` 下
- **`SKILL.md`** 描述能力、用法和安全限制（同时也是给 LLM 看的工具描述）
- **一个 `.py` 文件** 实现具体逻辑，提供 `run()` 作为入口
- 通过管理后台注册后，绑定到智能体即可使用

---

## 目录结构

```
skills/
├── calculator/          #    Skill 功能名（文件夹名）
│   ├── SKILL.md         # ── 描述文件（必需）
│   └── calculator.py    # ── Python 实现（可选，可只有 SKILL.md）
├── db_operator/
│   ├── SKILL.md
│   └── db_operator.py
├── get_date/
│   ├── SKILL.md
│   └── get_date.py
├── ocr_reader/
│   ├── SKILL.md
│   └── ocr_reader.py
├── pdf_reader/
│   ├── SKILL.md
│   └── pdf_reader.py
├── send_email/
│   ├── SKILL.md
│   └── send_email.py
└── web_search/
    ├── SKILL.md
    └── web_search.py
```

> 文件夹名 **不必** 与 `.py` 文件名相同，但建议保持一致便于维护。

---

## SKILL.md —— 描述文件

每个 Skill 必须在根目录放置 `SKILL.md`。这是 **核心描述文件**，系统从这里读取工具描述和参数说明。

### 格式

```markdown
---
name: <skill_name>
description: <一句话描述（显示在工具列表中）>
version: 1.0
author: <作者名>
requires: <可选：环境变量要求>
---

# <Skill 标题>

<详细的功能介绍>

## 能力

- 能力 1
- 能力 2

## 使用方式

<调用示例、参数说明>

## 安全限制

<可选：限制条件>
```

### YAML 前置元数据

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 是 | Skill 名称，LLM 看到的函数名中的标识 |
| `description` | 是 | 工具列表中的描述，LLM 据此决定是否调用 |
| `version` | 否 | 版本号 |
| `author` | 否 | 作者 |
| `requires` | 否 | 依赖的环境变量或系统要求 |
| `parameters` | 否 | 参数声明列表（推荐），详见下方[参数声明](#参数声明) |

### 参数声明（parameters）

> 这是本系统最重要的特性：**在 SKILL.md 中声明参数后，无需修改 `tools.py` 即可自动注册为 LLM 可调用的工具。**

`parameters` 是一个 YAML 列表，每个参数包含以下字段：

| 字段 | 必需 | 类型 | 说明 |
|------|------|------|------|
| `name` | 是 | string | 参数名 |
| `type` | 是 | string | `string` / `integer` / `number` / `boolean` |
| `description` | 是 | string | 参数说明，LLM 据此决定传什么值 |
| `required` | 否 | boolean | 是否必需（默认 false） |
| `enum` | 否 | list | 枚举值列表，限制参数的可选范围 |

示例（`send_email`）：

```yaml
parameters:
  - name: to
    type: string
    description: 收件人邮箱，多个用英文逗号分隔
    required: true
  - name: subject
    type: string
    description: 邮件主题
    required: true
  - name: body
    type: string
    description: 邮件正文（纯文本或 HTML）
    required: true
  - name: content_type
    type: string
    description: 正文格式
    enum: ["plain", "html"]
  - name: cc
    type: string
    description: 抄送邮箱，多个用英文逗号分隔
  - name: attachments
    type: string
    description: 附件路径，多个用英文逗号分隔
```

系统启动后，`build_definitions()` 会调用 `SkillExecutor.read_skill_parameters()` 读取每个 SKILL.md 的 `parameters`，自动生成 OpenAI function-calling schema。**不需要在 `tools.py` 中添加任何 `if name == "..."` 代码。**

### Markdown 正文

正文中的内容会传递给 LLM 作为工具的描述。**LLM 通过阅读正文来了解这个 Skill 能做什么、怎么用**。建议包含：

- **能力列表** —— 具体说明功能边界
- **使用方式** —— 参数说明、调用示例
- **安全限制** —— 防止 LLM 误用

---

## Python 辅助文件

Python 文件提供具体的功能实现。系统通过 `SkillExecutor` 动态加载并调用其中的函数。

### 入口函数

系统会依次查找：

1. `run(action, expression, **kwargs)` —— 通用入口，所有 Skill 都应该提供
2. 其他命名函数（如 `describe`、`list_tables`），可通过 `action` 参数指定

```python
def run(expression: str = "", action: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Args:
        expression: 主参数（文件路径、查询语句等）
        action:     要执行的操作（如 "ocr", "extract", "now"）
        **kwargs:   额外的命名参数

    Returns:
        字符串结果（通常为 JSON 格式，便于 LLM 解析）
    """
    # 实现逻辑...
    return json.dumps({"success": True, "result": "..."}, ensure_ascii=False)
```

### 返回值规范

返回值是 **字符串**，系统会原样返回给 LLM。建议：

- **成功时** 返回 JSON：`{"success": true, "result": "...", ...}`
- **失败时** 返回 JSON：`{"success": false, "error": "错误信息"}`
- 纯文本也可以，但 LLM 解析 JSON 更可靠
- 控制长度，太长会被截断

### 项目路径解析

Python 文件可以通过 `__file__` 相对路径定位项目根目录：

```python
from pathlib import Path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # 3 层: skills/<name>/<file>.py → 项目根
```

### .env 加载

如果 Skill 需要读取 `.env` 中的配置：

```python
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass
```

---

## 参数传递

系统支持三种传参方式，Skill 的 `run()` 函数应当兼容所有方式。

### 方式 1：命名关键字参数

```python
# LLM 调用时自然传参
run(action="ocr", file_path="/path/to/image.png", prompt="识别文字")
```

### 方式 2：JSON 字符串

```python
# 通过 expression 参数传入 JSON
run('{"action":"extract","file_path":"/path/to/file.pdf"}')
```

### 方式 3：简单字符串

```python
# 把 expression 作为唯一参数
run("2 + 3 * 5")
```

### 推荐的解析逻辑

```python
def run(expression: str = "", action: str = "", **kwargs) -> str:
    # 1. 如果 expression 是 JSON，解析它并提取参数
    if expression and expression.strip().startswith("{"):
        try:
            args = json.loads(expression)
            action = args.get("action", action)
            file_path = args.get("file_path", file_path)
        except json.JSONDecodeError:
            pass

    # 2. 也接受关键字参数
    file_path = file_path or kwargs.get("file_path", expression)

    # 3. 执行逻辑...
```

---

## 注册与使用

### 1. 在管理后台注册

1. 进入 **AI 配置 → Skills 管理**
2. 点击 **添加 Skill**
3. 填写：
   - **名称** —— 显示用名称
   - **描述** —— 一句话说明
   - **文件夹名** —— `skills/` 下的子文件夹名（如 `calculator`）
4. 保存

### 2. 绑定到智能体

1. 进入 **AI 配置 → 智能体管理**
2. 编辑目标智能体
3. 在 **Skills** 区域勾选需要的 Skill
4. 保存

### 3. 系统自动注册

**从 `v2.0` 开始，Skill 的参数声明直接从 `SKILL.md` 的 `parameters` 字段自动读取，无需修改 `tools.py`。**

当用户向智能体发送消息时：

1. 系统读取关联的 Skill 列表
2. 读取每个 Skill 的 `SKILL.md` 内容
3. 调用 `SkillExecutor.read_skill_parameters()` 解析 `parameters` 字段，自动生成 OpenAI function-calling schema
4. 将 Skill 描述和参数注册为 LLM 可调用的函数
5. LLM 根据对话内容决定是否调用
6. 调用时系统通过 `SkillExecutor` 加载 `.py` 文件并执行 `run()` 函数
7. 结果返回给 LLM，LLM 据此生成最终回复

---

## 最佳实践

### SKILL.md 写作

- **描述要准确** —— LLM 根据描述决定是否调用。描述不清楚会导致 LLM 在不需要时误调用，或在需要时忽略
- **提供参数示例** —— 正文中包含 JSON 调用示例，帮助 LLM 理解参数格式
- **明确安全边界** —— 在 `安全限制` 中标明不能做什么
- **保持简洁** —— LLM 的上下文有限，正文不宜过长

### 参数设计

- `expression` 作为主参数（查询字符串、文件路径等）
- `action` 如果 Skill 有多种操作模式
- 其他参数用明确的命名关键字
- 在 `run()` 函数内兼容多种调用方式

### 安全

- **永远不要在 `.py` 文件中硬编码密钥** —— 通过 `.env` 或系统环境变量注入
- 如果 Skill 执行危险操作（如发送邮件），在 `SKILL.md` 中标明限制条件
- 使用 `eval()` 时务必限制命名空间，禁止访问 `__builtins__`
- 文件操作类 Skill 注意路径穿越防护

### 依赖管理

- 在 `SKILL.md` 的 `requires` 字段标明第三方依赖
- 将依赖添加到项目 `requirements.txt`
- 使用 `try/except` 处理可选依赖缺失的情况

---

## 现有 Skill 参考

| Skill | 功能 | 技术栈 | 参考文件 |
|-------|------|--------|---------|
| `calculator` | 安全数学计算 | `math.eval()` 沙箱 | `skills/calculator/` |
| `db_operator` | SQLite 增查改（禁止删除），自动日志 | `sqlite3` | `skills/db_operator/` |
| `get_date` | 日期时间/农历 | Python `datetime` | `skills/get_date/` |
| `ocr_reader` | 图片文字识别 | Zhipu GLM-4V API | `skills/ocr_reader/` |
| `pdf_reader` | PDF 文本提取 | `pypdf` | `skills/pdf_reader/` |
| `send_email` | 发送邮件 | `smtplib` + Flask-Mail | `skills/send_email/` |
| `web_search` | 网络搜索 | Serper API | `skills/web_search/` |
