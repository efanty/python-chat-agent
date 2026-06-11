"""db_operator Skill — 项目数据库操作（增查改，禁止删除）。

仅支持 INSERT / SELECT / UPDATE 操作，每次操作同时记录到：
  1) logs/app.log（文件日志）
  2) operation_logs 表（可查询的操作日志）
基于 SQLAlchemy（from app.extensions.init_sqlalchemy import db）。
"""

import re
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

_logger = logging.getLogger("deepagent")

# ── 表名白名单 ──────────────────────────────────────────────────────────
ALLOWED_TABLES = frozenset({
    "users", "conversations", "messages", "settings",
    "skills", "agent_configs", "llm_models", "mcp_tools",
    "api_endpoints", "knowledge_base", "knowledge_base_files",
    "user_memories",
    "operation_logs",
})

TABLE_LABELS = {
    "users": "用户", "conversations": "对话", "messages": "消息",
    "settings": "系统设置", "skills": "技能", "agent_configs": "智能体配置",
    "llm_models": "LLM 模型", "mcp_tools": "MCP 工具",
    "api_endpoints": "API 端点", "knowledge_base": "知识库",
    "knowledge_base_files": "知识库文件", "user_memories": "用户记忆",
    "operation_logs": "操作日志",
}

# ── 操作日志表 DDL ─────────────────────────────────────────────────────
_OPLOG_DDL = text("""
CREATE TABLE IF NOT EXISTS operation_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    operation   TEXT    NOT NULL,
    table_name  TEXT    NOT NULL,
    row_id      INTEGER,
    detail      TEXT,
    success     INTEGER NOT NULL DEFAULT 1,
    operator    TEXT,
    created_at  TEXT    NOT NULL
)
""")

# ── Flask app context 辅助 ────────────────────────────────────────────

def _ensure_app_context():
    """确保 Flask app 上下文存在。生产环境下已有，无需操作。"""
    from flask import current_app
    try:
        _ = current_app.name
        return None
    except RuntimeError:
        pass
    try:
        from app import create_app
        app = create_app()
        ctx = app.app_context()
        ctx.push()
        return ctx
    except (ImportError, ModuleNotFoundError):
        raise RuntimeError(
            "无法创建 Flask 应用上下文（缺少依赖模块），"
            "请在项目完整环境下使用此 Skill。"
        )

def _cleanup_context(ctx):
    if ctx is not None:
        ctx.pop()


# ── 自动建表 ──────────────────────────────────────────────────────────

def _ensure_log_table():
    """确保 operation_logs 表存在。"""
    from app.extensions.init_sqlalchemy import db
    try:
        db.session.execute(_OPLOG_DDL)
        db.session.commit()
    except Exception:
        db.session.rollback()


# ── 安全校验 ────────────────────────────────────────────────────────────

_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _ensure_table_allowed(table: str):
    if table not in ALLOWED_TABLES:
        allowed_list = ", ".join(sorted(ALLOWED_TABLES))
        raise ValueError(f"不允许操作的表: '{table}'。允许的表: {allowed_list}")

def _ensure_column_name(col: str):
    if not _COLUMN_RE.match(col):
        raise ValueError(f"非法的列名: '{col}'")

def _ensure_no_dangerous_values(values: dict):
    for k, v in values.items():
        if isinstance(v, str) and len(v) > 10000:
            raise ValueError(f"字段 '{k}' 的值过长（超过 10000 字符）")


# ── 双通道日志（文件 + DB） ───────────────────────────────────────────

def _write_file_log(operation: str, table: str, detail: str,
                    row_id=None, success: bool = True):
    table_label = TABLE_LABELS.get(table, table)
    status = "✓" if success else "✗"
    id_part = f" | ID: {row_id}" if row_id is not None else ""
    msg = f"[数据库操作] {status} {operation} | 表: {table}({table_label}){id_part} | {detail}"
    if success:
        _logger.info(msg)
    else:
        _logger.error(msg)


def _write_db_log(operation: str, table: str, detail: str,
                  row_id=None, success: bool = True, operator: str = ""):
    """写操作日志到 operation_logs 表（独立事务）。"""
    from app.extensions.init_sqlalchemy import db
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        db.session.execute(
            text("INSERT INTO operation_logs "
                 "(operation, table_name, row_id, detail, success, operator, created_at) "
                 "VALUES (:op, :tbl, :rid, :det, :suc, :opr, :now)"),
            {"op": operation, "tbl": table, "rid": row_id,
             "det": detail, "suc": 1 if success else 0,
             "opr": operator or "", "now": now},
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def _log_op(operation: str, table: str, detail: str,
            row_id=None, success: bool = True, operator: str = ""):
    """双通道写日志：文件 + DB（独立事务）。"""
    _write_file_log(operation, table, detail, row_id=row_id, success=success)
    _write_db_log(operation, table, detail, row_id=row_id,
                  success=success, operator=operator)


# ── 操作实现 ────────────────────────────────────────────────────────────

def _list_tables() -> str:
    """列出数据库中所有表。"""
    from app.extensions.init_sqlalchemy import db
    result = db.session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    )
    tables = [r[0] for r in result.fetchall()]
    filtered = [t for t in tables if t in ALLOWED_TABLES]
    lines = [f"数据库表（共 {len(filtered)} 张，仅显示白名单内）:"]
    for t in filtered:
        label = TABLE_LABELS.get(t, "")
        lines.append(f"  - {t}{'  (' + label + ')' if label else ''}")
    other = [t for t in tables if t not in ALLOWED_TABLES]
    if other:
        lines.append(f"\n其他系统表（{len(other)} 张，不可操作）:")
        for t in other:
            lines.append(f"  - {t}")
    return "\n".join(lines)


def _describe(table: str) -> str:
    """查看表结构。"""
    _ensure_table_allowed(table)
    from app.extensions.init_sqlalchemy import db
    label = TABLE_LABELS.get(table, table)
    result = db.session.execute(text(f"PRAGMA table_info('{table}')"))
    rows = result.fetchall()
    if not rows:
        return f"表 '{table}' 不存在。"
    lines = [f"表结构: {table} ({label})",
             "  # | 列名 | 类型 | 非空 | 默认值 | 主键"]
    for r in rows:
        lines.append(
            f"  {r.cid} | {r.name} | {r.type} | "
            f"{'是' if r.notnull else '否'} | "
            f"{r.dflt_value or '-'} | {'是' if r.pk else '否'}"
        )
    return "\n".join(lines)


def _query(table: str, columns: str = "*", where: str = "",
           order: str = "", limit: int = 50, operator: str = "") -> str:
    """查询数据（SELECT）。"""
    _ensure_table_allowed(table)
    from app.extensions.init_sqlalchemy import db

    if columns != "*":
        parts = [c.strip() for c in columns.split(",")]
        for c in parts:
            _ensure_column_name(c)
        cols_sql = ", ".join(parts)
    else:
        cols_sql = "*"

    order_sql = ""
    if order:
        order_parts = order.strip().split()
        _ensure_column_name(order_parts[0])
        if len(order_parts) > 1:
            direction = order_parts[1].upper()
            if direction not in ("ASC", "DESC"):
                raise ValueError(f"非法的排序方向: '{direction}'，仅支持 ASC/DESC")
            order_sql = f" ORDER BY {order_parts[0]} {direction}"
        else:
            order_sql = f" ORDER BY {order_parts[0]}"

    where_sql = f" WHERE {where}" if where else ""
    limit = min(max(limit, 1), 200)
    sql = f"SELECT {cols_sql} FROM {table}{where_sql}{order_sql} LIMIT :lim"

    result = db.session.execute(text(sql), {"lim": limit})
    rows = result.fetchall()

    if not rows:
        col_names = list(result.keys())
        _log_op("SELECT", table, f"0 行返回 | 列: {', '.join(col_names)}",
                operator=operator)
        return f"查询完成。列: {', '.join(col_names)}\n0 行数据。"

    col_names = list(result.keys())
    sep = "-" * max(40, len(" | ".join(col_names)))
    lines = [" | ".join(col_names), sep]
    for row in rows:
        vals = []
        for v in row:
            if v is None:
                vals.append("NULL")
            elif isinstance(v, str) and len(v) > 120:
                vals.append(v[:120] + "...")
            else:
                vals.append(str(v))
        lines.append(" | ".join(vals))

    count = len(rows)
    if count >= limit:
        lines.append(f"\n...（仅显示前 {limit} 条）")
    _log_op("SELECT", table, f"{count} 行返回", operator=operator)
    return "\n".join(lines)


def _insert(table: str, data: dict, operator: str = "") -> str:
    """插入一条数据（INSERT）。"""
    _ensure_table_allowed(table)
    _ensure_no_dangerous_values(data)
    from app.extensions.init_sqlalchemy import db

    if not data:
        raise ValueError("data 不能为空，请提供要插入的字段值对")

    cols, param_names, values = [], [], {}
    for col, val in data.items():
        _ensure_column_name(col)
        cols.append(col)
        pname = f"v_{col}"
        param_names.append(f":{pname}")
        values[pname] = val

    cols_sql = ", ".join(cols)
    ph_sql = ", ".join(param_names)
    sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({ph_sql})"

    try:
        result = db.session.execute(text(sql), values)
        db.session.commit()
        row_id = result.lastrowid
        detail = f"字段: {', '.join(cols[:5])}{'...' if len(cols) > 5 else ''}"
        _log_op("INSERT", table, detail, row_id=row_id, operator=operator)
        return json.dumps({
            "success": True, "operation": "INSERT", "table": table,
            "row_id": row_id, "affected_rows": result.rowcount,
        }, ensure_ascii=False)
    except Exception as e:
        db.session.rollback()
        _log_op("INSERT", table, str(e), success=False, operator=operator)
        raise


def _update(table: str, data: dict, where: str = "", operator: str = "") -> str:
    """更新数据（UPDATE）。"""
    _ensure_table_allowed(table)
    _ensure_no_dangerous_values(data)
    from app.extensions.init_sqlalchemy import db

    if not data:
        raise ValueError("data 不能为空，请提供要更新的字段值对")

    if not where or where.strip().upper() == "1=1":
        raise ValueError("UPDATE 操作必须提供明确的 WHERE 条件，禁止全表更新")

    set_parts, values = [], {}
    for col, val in data.items():
        _ensure_column_name(col)
        pname = f"v_{col}"
        set_parts.append(f"{col} = :{pname}")
        values[pname] = val

    set_sql = ", ".join(set_parts)
    sql = f"UPDATE {table} SET {set_sql} WHERE {where}"

    try:
        result = db.session.execute(text(sql), values)
        db.session.commit()
        affected = result.rowcount
        detail = f"更新 {affected} 行 | 条件: {where[:80]}"
        _log_op("UPDATE", table, detail, operator=operator)
        return json.dumps({
            "success": True, "operation": "UPDATE", "table": table,
            "affected_rows": affected,
        }, ensure_ascii=False)
    except Exception as e:
        db.session.rollback()
        _log_op("UPDATE", table, str(e), success=False, operator=operator)
        raise


# ── 操作日志查询 ───────────────────────────────────────────────────────

def _query_logs(operation: str = "", table_name: str = "",
                success: str = "", limit: int = 50,
                operator: str = "") -> str:
    """查询操作日志记录。"""
    from app.extensions.init_sqlalchemy import db

    conditions = []
    params = {}

    if operation:
        conditions.append("lo.operation = :op")
        params["op"] = operation.upper()
    if table_name:
        conditions.append("lo.table_name = :tbl")
        params["tbl"] = table_name
    if success in ("1", "0", "true", "false"):
        val = 1 if success in ("1", "true") else 0
        conditions.append("lo.success = :suc")
        params["suc"] = val

    where_sql = ""
    if conditions:
        where_sql = " WHERE " + " AND ".join(conditions)

    limit = min(max(limit, 1), 200)
    params["lim"] = limit

    sql = (
        f"SELECT lo.id, lo.operation, lo.table_name, lo.row_id, "
        f"lo.detail, lo.success, lo.operator, lo.created_at "
        f"FROM operation_logs lo{where_sql} "
        f"ORDER BY lo.id DESC LIMIT :lim"
    )

    result = db.session.execute(text(sql), params)
    rows = result.fetchall()

    if not rows:
        _log_op("SELECT", "operation_logs", "0 行返回", operator=operator)
        return "操作日志为空，或没有匹配的记录。"

    lines = [
        "ID | 操作 | 目标表 | 行ID | 操作者 | 时间 | 详情 | 状态",
        "-" * 80,
    ]
    for r in rows:
        op = r.operation
        tbl = r.table_name
        rid = str(r.row_id) if r.row_id is not None else "-"
        op_user = r.operator or "-"
        ts = (r.created_at or "")[:19]
        det = (r.detail or "")[:60]
        status = "✓" if r.success else "✗"
        lines.append(f"{r.id} | {op} | {tbl} | {rid} | {op_user} | {ts} | {det} | {status}")

    count = len(rows)
    if count >= limit:
        lines.append(f"\n...（仅显示前 {limit} 条）")
    _log_op("SELECT", "operation_logs", f"{count} 行返回", operator=operator)
    return "\n".join(lines)


# ── 入口 ────────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """数据库增查改操作入口（禁止删除）。

    Actions:
      query        — 查询数据（SELECT）
      insert       — 插入数据（INSERT）
      update       — 更新数据（UPDATE）
      list_tables  — 列出所有表名
      describe     — 查看表结构
      query_logs   — 查询操作日志

    Args:
        action:     操作类型
        expression: 可选的 JSON 字符串，包含所有参数
        table:      表名
        columns:    要查询的列（query 用，默认 "*"）
        where:      WHERE 条件
        order:      排序（如 "id DESC"）
        limit:      最大返回行数（默认 50，最大 200）
        data:       JSON 字符串，字段值对（insert/update 用）
        operator:   操作者标识

      query_logs 接受:
        operation:  按操作类型筛选
        table_name: 按目标表名筛选
        success:    按状态筛选（"1"=成功, "0"=失败）

    Returns:
        JSON 字符串或格式化文本
    """
    # ── 解析参数 ──────────────────────────────────────────────────
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = params.get("action") or action or ""
    table = params.get("table") or kwargs.get("table", "")
    columns = params.get("columns") or kwargs.get("columns", "*")
    where = params.get("where") or kwargs.get("where", "")
    order = params.get("order") or kwargs.get("order", "")
    operator = params.get("operator") or kwargs.get("operator", "")
    try:
        limit = int(params.get("limit") or kwargs.get("limit", 50))
    except (ValueError, TypeError):
        limit = 50

    data_raw = kwargs.get("data") or params.get("data", "")
    data = {}
    if isinstance(data_raw, dict):
        data = data_raw
    elif isinstance(data_raw, str) and data_raw.strip().startswith("{"):
        try:
            data = json.loads(data_raw)
        except json.JSONDecodeError:
            pass

    # ── 确保 Flask 上下文 + 建表 ─────────────────────────────────
    ctx = _ensure_app_context()
    try:
        _ensure_log_table()

        if action == "list_tables":
            return _list_tables()

        if action == "describe":
            if not table:
                return "缺少参数: table（表名）"
            return _describe(table)

        if action == "query":
            if not table:
                return "缺少参数: table（表名）"
            return _query(table, columns=columns, where=where,
                          order=order, limit=limit, operator=operator)

        if action == "insert":
            if not table:
                return "缺少参数: table（表名）"
            if not data:
                return "缺少参数: data（字段值对，JSON 格式）"
            return _insert(table, data, operator=operator)

        if action == "update":
            if not table:
                return "缺少参数: table（表名）"
            if not data:
                return "缺少参数: data（要更新的字段值对）"
            if not where:
                return "缺少参数: where（UPDATE 必须提供 WHERE 条件）"
            return _update(table, data, where=where, operator=operator)

        if action == "query_logs":
            filter_op = params.get("operation") or kwargs.get("fs_operation", "")
            filter_table = params.get("table_name") or kwargs.get("table_name", "")
            filter_success = params.get("success") or kwargs.get("success", "")
            return _query_logs(
                operation=filter_op, table_name=filter_table,
                success=filter_success, limit=limit, operator=operator,
            )

        return (
            "数据库操作工具 (db_operator)\n"
            "用法: run(action='操作类型', table='表名', ...)\n\n"
            "支持的操作:\n"
            "  list_tables  — 列出所有表名\n"
            "  describe     — 查看表结构（需 table 参数）\n"
            "  query        — 查询数据（需 table，可选 columns/where/order/limit）\n"
            "  insert       — 插入数据（需 table + data）\n"
            "  update       — 更新数据（需 table + data + where）\n"
            "  query_logs   — 查询操作日志（可选 operation/table_name/success 筛选）\n\n"
            "安全限制:\n"
            "  - 禁止 DELETE / DROP / ALTER / TRUNCATE / CREATE\n"
            "  - 仅允许操作白名单中的表\n"
            "  - UPDATE 必须提供 WHERE 条件，禁止全表更新\n"
            "  - 每次操作自动记录双通道日志（文件 + operation_logs 表）"
        )

    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        _logger.error(f"[数据库操作] ✗ 未知错误: {e}")
        return json.dumps({"success": False, "error": f"操作失败: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)


# ── 动作别名 ────────────────────────────────────────────────────────────
query = lambda expression="", **kwargs: run(action="query", expression=expression, **kwargs)
insert = lambda expression="", **kwargs: run(action="insert", expression=expression, **kwargs)
update = lambda expression="", **kwargs: run(action="update", expression=expression, **kwargs)
list_tables = lambda expression="", **kwargs: run(action="list_tables", **kwargs)
query_logs = lambda expression="", **kwargs: run(action="query_logs", **kwargs)
