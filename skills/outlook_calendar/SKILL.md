---
name: outlook_calendar
description: 将待办事项或日程添加到 Windows 11 Outlook 日历中
version: 1.0
author: DeepAgent Team
requires: pywin32 (pip install pywin32), Microsoft Outlook (Windows 11)
parameters:
  - name: action
    type: string
    description: "操作: add(添加日程) / list(列出今日日程)"
    required: true
  - name: subject
    type: string
    description: 日程标题（add 时必需）
  - name: start_time
    type: string
    description: "开始时间，格式 YYYY-MM-DD HH:MM（add 时必需）"
  - name: end_time
    type: string
    description: "结束时间，格式 YYYY-MM-DD HH:MM（默认开始后1小时）"
  - name: body
    type: string
    description: 日程备注或详细说明
  - name: location
    type: string
    description: 地点
  - name: reminder_minutes
    type: integer
    description: "提前提醒分钟数（默认 15，设为 0 关闭提醒）"
  - name: category
    type: string
    description: 分类标签（如"会议"、"待办"、"个人"）
---

# Outlook 日历管理 (outlook_calendar)

将待办事项添加到 Windows 11 的 Microsoft Outlook 日历中。

## 前置条件

- Windows 11 操作系统
- 已安装 Microsoft Outlook（任何版本）
- 已安装 `pywin32` 库：`pip install pywin32`

## 能力

- `add` — 添加一条新日程到 Outlook 默认日历
- `list` — 列出今天 Outlook 日历中的日程

## 使用方式

### 添加日程（add）

```json
{
  "action": "add",
  "subject": "项目评审会议",
  "start_time": "2026-06-01 14:00",
  "end_time": "2026-06-01 15:30",
  "body": "讨论 Q2 项目进度和风险点\n需准备：季度报告、数据分析",
  "location": "3楼会议室A",
  "reminder_minutes": 15,
  "category": "会议"
}
```

### 列出今日日程（list）

```json
{
  "action": "list"
}
```

## 返回格式

```json
{
  "success": true,
  "message": "日程已添加到 Outlook 日历: 项目评审会议",
  "appointment": {
    "subject": "项目评审会议",
    "start": "2026-06-01 14:00",
    "end": "2026-06-01 15:30",
    "location": "3楼会议室A"
  }
}
```

## 注意事项

- 操作的是当前 Windows 用户的 Outlook 默认日历
- 如果 Outlook 未运行，pywin32 会自动启动它（可能弹出安全提示）
- 日程保存后自动同步到 Exchange/Office 365（如果已配置）
- pywin32 仅在 Windows 平台可用
