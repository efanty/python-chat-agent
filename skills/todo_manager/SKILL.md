---
name: todo_manager
description: 待办事项管理 — 增、查、改、删，支持分类和关键词搜索
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作类型: list(查询) / add(新增) / update(更新) / delete(删除)"
    enum: ["list", "add", "update", "delete", "query", "create", "edit", "remove"]
    required: true
  - name: body
    type: string
    description: 待办内容（add/update 时传入）
  - name: todo_id
    type: integer
    description: 待办 ID（update/delete 时传入）
  - name: done
    type: string
    description: "完成状态: 1/0 true/false 是/否（list 筛选或 update 设值）"
  - name: mold_number
    type: string
    description: 分类编号
  - name: keyword
    type: string
    description: 关键词搜索（list 用）
  - name: limit
    type: integer
    description: 最大返回行数（list 用，默认 50）
  - name: due_date
    type: string
    description: 截止日期 YYYY-MM-DD（add/update 用）
---

# 待办事项管理 (todo_manager)

管理项目的待办事项（`todo` 表），支持完整的 CRUD 操作。
每次操作自动记录日志到 `logs/app.log`。

## 能力

- `list` — 查询待办事项列表，支持按用户、完成状态、关键词筛选
- `add` — 创建待办事项，可指定分类（mold_number）和创建者
- `update` — 更新待办事项内容、完成状态、分类
- `delete` — 删除待办事项

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `list` / `add` / `update` / `delete` |
| `body` | string | 是(add) | — | add/update | 待办内容 |
| `todo_id` | int | 是(update/delete) | — | update/delete | 待办 ID |
| `done` | bool/string | 否 | — | list/update | 完成状态：`1`/`0`、`true`/`false`、`是`/`否` |
| `mold_number` | string | 否 | "" | add/update | 分类编号，如 "shopping"、"work" 等 |
| `due_date` | string | 否 | — | add/update | 截止日期，格式 `YYYY-MM-DD` |
| `keyword` | string | 否 | — | list | 按待办内容关键词搜索 |
| `limit` | int | 否 | 50 | list | 最大返回行数（1~200） |

### 权限规则

| 用户角色 | list | add | update | delete |
|---------|------|-----|--------|--------|
| 普通用户 | 仅看到自己的待办 | 作者设为当前用户 | 仅能修改自己的 | 仅能删除自己的 |
| 管理员 | 可查看全部 | 作者设为当前用户 | 可修改任何用户的 | 可删除任何用户的 |

### 调用示例

创建待办（作者自动设为当前登录用户，无需传入）：

```json
{
  "action": "add",
  "body": "买牛奶和面包",
  "mold_number": "shopping",
  "due_date": "2026-06-01"
}
```

查询未完成的待办：

```json
{
  "action": "list",
  "done": "0",
  "limit": 20
}
```

关键词搜索：

```json
{
  "action": "list",
  "keyword": "牛奶"
}
```

标记完成：

```json
{
  "action": "update",
  "todo_id": 1,
  "done": "1"
}
```

删除待办：

```json
{
  "action": "delete",
  "todo_id": 1
}
```

### 返回格式

`list` 返回格式化表格：

```
ID | 内容 | 状态 | 分类 | 截止日期 | 创建者 | 时间
--------------------------------------------------------------------------------
1 | 买牛奶和面包 | ○ 待办 | shopping | 2026-06-01 | admin | 2026-05-19T16:55:27
2 | 开会报告 | ✓ 已完成 | work | - | admin | 2026-05-19T16:50:00
```

`add` / `update` / `delete` 返回 JSON：

```json
{
  "success": true,
  "operation": "INSERT",
  "todo_id": 1,
  "body": "买牛奶和面包",
  "mold_number": "shopping",
  "due_date": "2026-06-01"
}
```

## 安全限制

- 基于 SQLAlchemy ORM，天然防 SQL 注入
- 删除操作仅支持按 ID 单条删除
- 更新操作仅更新传入的字段，其他字段不受影响
- 查询结果上限 200 行

## 日志格式

```
2026-05-19 16:55:00 | INFO  | [todo 管理] ✓ INSERT | ID: 1 | 创建待办: 买牛奶和面包
2026-05-19 16:56:00 | INFO  | [todo 管理] ✓ UPDATE | ID: 1 | 更新字段: done=True
2026-05-19 16:57:00 | INFO  | [todo 管理] ✓ DELETE | ID: 1 | 删除待办: 买牛奶和面包
```