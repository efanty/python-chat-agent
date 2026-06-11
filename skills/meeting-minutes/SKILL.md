---
name: 会议纪要
description: 根据会议笔记或录音转文字内容，自动生成结构化会议纪要（议题、讨论、决议、待办），并创建 Outlook 日历待办
version: 1.0
author: DeepAgent Team
requires: ZHIPU_API_KEY (可选，用于智能提取结构化信息)
parameters:
  - name: action
    type: string
    description: "操作: generate(生成纪要) / list(列出纪要) / get(查看详情)"
    enum: ["generate", "list", "get"]
    required: true
  - name: content
    type: string
    description: 会议笔记或录音转文字内容（generate 时必需）
  - name: title
    type: string
    description: 会议标题（generate 时可选，默认自动提取）
  - name: meeting_date
    type: string
    description: 会议日期 YYYY-MM-DD（可选，默认今天）
  - name: participants
    type: string
    description: 参会人员列表，逗号分隔（可选）
  - name: meeting_id
    type: integer
    description: 纪要 ID（get 时必需）
  - name: keyword
    type: string
    description: 搜索关键词（list 用）
  - name: limit
    type: integer
    description: 最大返回条数（list 用，默认 20）
---

# 会议纪要 (meeting_minutes)

根据会议笔记或录音转文字内容，自动生成结构化会议纪要，并存入数据库。

## 能力

- `generate` — 根据会议内容生成结构化纪要（议题、讨论、决议、待办），自动保存到数据库
- `list` — 查询历史会议纪要列表
- `get` — 查看单条会议纪要详情

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `generate` / `list` / `get` |
| `content` | string | 是(generate) | — | generate | 会议笔记或录音转文字内容 |
| `title` | string | 否 | 自动提取 | generate | 会议标题 |
| `meeting_date` | string | 否 | 今天 | generate | 会议日期 YYYY-MM-DD |
| `participants` | string | 否 | — | generate | 参会人员，逗号分隔 |
| `meeting_id` | int | 是(get) | — | get | 纪要 ID |
| `keyword` | string | 否 | — | list | 按标题/内容搜索 |
| `limit` | int | 否 | 20 | list | 最大返回条数 |

### 调用示例

生成会议纪要：

```json
{
  "action": "generate",
  "title": "Q2 模具项目评审会",
  "content": "参会人员：张三、李四、王五\n时间：2026-06-03 14:00-15:30\n\n议题1：M26007 项目进度\n张三汇报了M26007的试模进度，目前已完成T1试模，T2试模安排在6月10日。李四提出需要确认钢材到货时间。\n决议：王五负责跟进钢材到货，6月7日前反馈。\n\n议题2：M25021 成本超支问题\n当前实际成本已超出预算15%，主要原因是钢材价格上涨和T1试模废品率偏高。\n决议：张三分析废品原因，李四重新询价钢材供应商。\n\n待办事项：\n1. 王五 - 跟进钢材到货 - 6月7日\n2. 张三 - 分析T1废品原因 - 6月10日\n3. 李四 - 重新询价钢材供应商 - 6月10日",
  "participants": "张三,李四,王五",
  "meeting_date": "2026-06-03"
}
```

查询纪要列表：

```json
{
  "action": "list",
  "keyword": "模具",
  "limit": 10
}
```

查看详情：

```json
{
  "action": "get",
  "meeting_id": 1
}
```

### 返回格式

generate 返回：

```json
{
  "success": true,
  "meeting_id": 1,
  "title": "Q2 模具项目评审会",
  "summary": "讨论了M26007项目进度和M25021成本超支问题",
  "action_items": 3,
  "created_todos": 3
}
```

## 安全限制

- 基于 SQLAlchemy ORM，防 SQL 注入
- 仅限登录用户操作自己的数据
