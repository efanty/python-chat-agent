---
name: db_operator
description: 项目数据库操作 — 增、查、改（禁止删除）。每次操作自动记录双通道日志。
version: 1.1
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作类型: query(查询) / insert(插入) / update(更新) / list_tables(列出表) / describe(表结构) / query_logs(查询日志)"
    enum: ["query", "insert", "update", "list_tables", "describe", "query_logs"]
    required: true
  - name: table
    type: string
    description: 表名
    required: true
  - name: data
    type: string
    description: 'JSON格式的字段值，如 {"field": "value"}（insert/update 用）'
  - name: where
    type: string
    description: WHERE条件（query/update 用）
  - name: order
    type: string
    description: 排序，如 id DESC（query 用）
  - name: limit
    type: integer
    description: 返回行数上限
  - name: operation
    type: string
    description: 筛选操作类型（query_logs 用）
  - name: table_name
    type: string
    description: 筛选目标表（query_logs 用）
  - name: success
    type: string
    description: "筛选状态: 1=成功 0=失败（query_logs 用）"
---

# 数据库操作工具 (db_operator)

操作项目的 SQLite 数据库（`instance/app.db`），支持查询、插入、更新数据。
**禁止删除操作** — DELETE / DROP / ALTER / TRUNCATE / CREATE 均被阻断。

## 双通道日志

每次操作同时记录到两处：

- **文件日志**: `logs/app.log` — 系统级审计追溯
- **DB 日志**: `operation_logs` 表 — 可通过 `query_logs` 动作在线查询

`operation_logs` 表自动创建（首次连接时），无需手动迁移。

## 能力

- `list_tables` — 列出数据库中所有表名（含中文说明）
- `describe` — 查看指定表的列结构（列名、类型、非空、默认值、主键）
- `query` — 查询数据（SELECT），支持 WHERE / ORDER BY / LIMIT
- `insert` — 插入数据（INSERT），返回新记录 ID
- `update` — 更新数据（UPDATE），**必须提供 WHERE 条件**，禁止全表更新
- `query_logs` — 查询操作日志，支持按操作类型/目标表/成功状态筛选

## 安全限制

- **绝对禁止**：DELETE / DROP / ALTER / TRUNCATE / CREATE 操作
- 仅允许操作白名单内的业务表（`users`, `conversations`, `messages`, `settings`, `skills`, `agent_configs`, `llm_models`, `mcp_tools`, `api_endpoints`, `knowledge_base`, `knowledge_base_files`, `user_memories`, `operation_logs`）
- 所有数据值使用参数化查询（`?` 占位符），防 SQL 注入
- 列名和表名经过严格正则校验
- UPDATE 必须提供明确的 WHERE 条件，禁止 `1=1` 全表更新
- INSERT 单次数据值限制 10000 字符/字段
- query 结果上限 200 行

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `query` / `insert` / `update` / `list_tables` / `describe` / `query_logs` |
| `table` | string | 是* | — | query/insert/update/describe | 表名，*list_tables/query_logs 不需要 |
| `columns` | string | 否 | `*` | query | 要查询的列，逗号分隔 |
| `where` | string | 是(update) | — | query/update | WHERE 条件，update 必须提供 |
| `order` | string | 否 | — | query | 排序，如 `id DESC` |
| `limit` | int | 否 | 50 | query/query_logs | 最大返回行数（1~200） |
| `data` | JSON | 是* | — | insert/update | 字段值对 `{"field": "value", ...}` |
| `operator` | string | 否 | "" | 所有 | 操作者标识，如 `"user:admin"` 或 `"system"` |
| `operation` | string | 否 | — | query_logs | 筛选操作类型：`INSERT` / `UPDATE` / `SELECT` |
| `table_name` | string | 否 | — | query_logs | 筛选目标表名 |
| `success` | string | 否 | — | query_logs | 筛选状态：`"1"`（成功）或 `"0"`（失败） |

### 调用示例

查询用户：

```json
{
  "action": "query",
  "table": "users",
  "columns": "id, username, email, role",
  "where": "role='admin'",
  "order": "id ASC",
  "limit": 10
}
```

插入新设置：

```json
{
  "action": "insert",
  "table": "settings",
  "data": "{\"key\": \"site_title\", \"value\": \"My Site\"}",
  "operator": "user:admin"
}
```

更新用户信息：

```json
{
  "action": "update",
  "table": "users",
  "data": "{\"nickname\": \"新昵称\"}",
  "where": "id=1",
  "operator": "user:admin"
}
```

查询操作日志（最近 20 条成功插入操作）：

```json
{
  "action": "query_logs",
  "operation": "INSERT",
  "success": "1",
  "limit": 20
}
```

查询对 `users` 表的所有操作：

```json
{
  "action": "query_logs",
  "table_name": "users"
}
```

### 返回格式

`query` 和 `query_logs` 返回格式化表格：

```
ID | 操作 | 目标表 | 行ID | 操作者 | 时间 | 详情 | 状态
--------------------------------------------------------------------------------
1 | INSERT | settings | 42 | user:admin | 2026-05-18T10:30:00 | 字段: key, value | ✓
2 | UPDATE | users | 1 | user:admin | 2026-05-18T10:31:00 | 更新 1 行 | ✓
3 | SELECT | users | - | system | 2026-05-18T10:32:00 | 3 行返回 | ✓
```

`insert` / `update` 返回 JSON：

```json
{
  "success": true,
  "operation": "INSERT",
  "table": "settings",
  "row_id": 42,
  "affected_rows": 1
}
```

## 日志格式

### 文件日志（logs/app.log）

```
2026-05-18 10:30:00 | INFO  | [数据库操作] ✓ INSERT | 表: settings(系统设置) | ID: 42 | 字段: key, value
2026-05-18 10:31:00 | ERROR | [数据库操作] ✗ UPDATE | 表: users(用户) | 违反安全限制: WHERE 条件不能为空
```

### DB 日志（operation_logs 表）

每条记录包含：ID、操作类型、目标表、影响行ID、详情、成功状态、操作者、UTC 时间戳。
可通过 `query_logs` 动作查询，也支持直接用 `query` 动作查 `operation_logs` 表。

## 日志表结构

```sql
CREATE TABLE operation_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT NOT NULL,       -- INSERT / UPDATE / SELECT
    table_name  TEXT NOT NULL,       -- 操作的目标表
    row_id      INTEGER,            -- 受影响的行 ID
    detail      TEXT,               -- 操作详情
    success     INTEGER NOT NULL,   -- 1=成功, 0=失败
    operator    TEXT,               -- 操作者标识
    created_at  TEXT NOT NULL       -- ISO-8601 UTC 时间
);
```

## 注意事项

- 本项目默认使用 SQLite 数据库（`instance/app.db`），如切换为 MySQL 需修改连接逻辑
- 日志记录字段名但不记录具体字段值，保护数据隐私
- 日志表自动创建，无需手动迁移
- `operation_logs` 表本身也可通过 `query` 动作直接查询（属白名单）
- 如果数据库文件不存在，会返回明确的错误提示