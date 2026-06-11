---
name: get_date
description: 获取日期时间信息，支持公历、农历、星期、生肖、日期计算
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: now(当前时间) / date(日期信息) / calc(日期计算)"
    enum: ["now", "date", "calc"]
    required: true
  - name: expression
    type: string
    description: 日期字符串或计算参数的 JSON
---

# Get Date Skill

获取日期和时间信息。

## 能力

- 当前日期时间（本地/UTC）
- 指定日期的详细信息（星期、季度、第几周、是否闰年）
- 农历日期 + 生肖 + 天干地支
- 日期加减计算（天/月/年）

## 使用方式

调用 `run(action, expression)` 函数：
- `action="now"` — 获取当前时间
- `action="date"` — 获取指定日期信息，`expression="YYYY-MM-DD"`
- `action="calc"` — 日期计算，`expression` 为 JSON：`{"base":"2025-01-01","days":30}`