---
name: 周报生成器
description: 根据本周待办完成情况、模具项目进度、会议纪要等数据，自动生成周报 Word 文档
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: generate(生成周报) / list(列出周报) / get(查看周报)"
    enum: ["generate", "list", "get"]
    required: true
  - name: mold_number
    type: string
    description: 模具编号（可选，指定后只生成该项目的周报）
  - name: week_start
    type: string
    description: 周报起始日期 YYYY-MM-DD（可选，默认本周一）
  - name: week_end
    type: string
    description: 周报结束日期 YYYY-MM-DD（可选，默认本周日）
  - name: report_id
    type: integer
    description: 周报 ID（get 时必需）
  - name: keyword
    type: string
    description: 搜索关键词（list 用）
  - name: limit
    type: integer
    description: 最大返回条数（list 用，默认 20）
---

# 周报生成器 (weekly_report)

根据本周的待办完成情况、模具项目进度、会议纪要等数据，自动汇总生成周报 Word 文档。

## 能力

- `generate` — 自动汇总本周数据，生成周报 Word 文档
- `list` — 查询已生成的周报列表
- `get` — 查看周报详情

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `generate` / `list` / `get` |
| `mold_number` | string | 否 | 全部项目 | generate | 模具编号，指定后只生成该项目的周报 |
| `week_start` | string | 否 | 本周一 | generate | 周报起始日期 YYYY-MM-DD |
| `week_end` | string | 否 | 本周日 | generate | 周报结束日期 YYYY-MM-DD |
| `report_id` | int | 是(get) | — | get | 周报 ID |
| `keyword` | string | 否 | — | list | 搜索关键词 |
| `limit` | int | 否 | 20 | list | 最大返回条数 |

### 调用示例

生成周报：

```json
{
  "action": "generate",
  "week_start": "2026-06-01",
  "week_end": "2026-06-07"
}
```

生成指定项目的周报：

```json
{
  "action": "generate",
  "mold_number": "M26007",
  "week_start": "2026-06-01",
  "week_end": "2026-06-07"
}
```

查询周报列表：

```json
{
  "action": "list",
  "keyword": "M26007",
  "limit": 10
}
```

### 返回格式

```json
{
  "success": true,
  "report_id": 1,
  "title": "周报 2026-06-01 ~ 2026-06-07",
  "file": "sandbox/weekly_report_20260601_20260607.docx",
  "summary": "本周完成待办 5 项，M26007 项目 T2 试模完成"
}
```

## 安全限制

- 只读操作，不修改数据库
- 需要 python-docx 库支持
