---
name: local_todo
description: 本地待办提醒 — 增、查、改、删待办事项，定时检查并弹出 Windows 系统通知提醒
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作类型: add(新增) / list(查询) / update(更新) / delete(删除) / check(手动检查) / start(启动定时提醒) / stop(停止定时提醒)"
    enum: ["add", "list", "update", "delete", "check", "start", "stop"]
    required: true
  - name: title
    type: string
    description: 待办标题（add 时必需）
  - name: due_time
    type: string
    description: 提醒时间，格式 "HH:MM"（当天）或 "YYYY-MM-DD HH:MM"
  - name: note
    type: string
    description: 备注信息
  - name: todo_id
    type: integer
    description: 待办 ID（update/delete 时必需）
  - name: done
    type: boolean
    description: 完成状态 true/false（update 用）
  - name: show_done
    type: boolean
    description: 是否显示已完成（list 用）
  - name: keyword
    type: string
    description: 按标题关键词搜索（list 用）
  - name: interval
    type: integer
    description: 定时检查间隔（秒，默认30）
---

# 本地待办提醒 (local_todo)

## 功能描述
本地待办事项管理 Skill，支持增、查、改、删操作，并能在指定时间弹出 Windows 系统通知提醒。

## 数据存储
数据存储在 `skills/local_todo/data/todos.json` 文件中，纯本地运行，无需联网。

## 可用操作 (action)

| 操作 | 说明 | 必需参数 | 可选参数 |
|------|------|---------|---------|
| `add` | 添加待办 | `title` | `due_time`, `note` |
| `list` | 查询待办 | - | `show_done`, `keyword` |
| `update` | 更新待办 | `todo_id` | `title`, `due_time`, `note`, `done` |
| `delete` | 删除待办 | `todo_id` | - |
| `check` | 手动检查到期提醒 | - | - |
| `start` | 启动定时提醒服务 | - | `interval`(秒,默认30) |
| `stop` | 停止定时提醒服务 | - | - |

## 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `title` | string | 待办标题 |
| `due_time` | string | 提醒时间，格式 `HH:MM`（当天）或 `YYYY-MM-DD HH:MM` |
| `note` | string | 备注信息 |
| `todo_id` | integer | 待办 ID（update/delete 用） |
| `done` | boolean | 完成状态 true/false（update 用） |
| `show_done` | boolean | 是否显示已完成（list 用） |
| `keyword` | string | 按标题关键词搜索（list 用） |
| `interval` | integer | 定时检查间隔（秒，默认30） |

## 使用示例

### 添加待办
```
action=add, title=喝水, due_time=14:00, note=记得喝一杯温水
```

### 查询所有未完成待办
```
action=list
```

### 按关键词搜索
```
action=list, keyword=喝水
```

### 标记完成
```
action=update, todo_id=1, done=true
```

### 删除待办
```
action=delete, todo_id=1
```

### 启动定时提醒
```
action=start, interval=30
```

## 系统要求
- Windows 系统（通知依赖 plyer 库）
- 依赖库：`plyer`
