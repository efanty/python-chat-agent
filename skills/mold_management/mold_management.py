"""mold_management Skill — 模具项目管理查询。

通过直接访问 mold 插件的独立 SQLite 数据库，
提供项目信息、模具信息、试模记录等数据查询。只读操作。
"""

import json
import os
import sqlite3

_ACTION_DESCRIPTION = "模具管理"

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_SKILL_DIR, '..', '..',
                        'app', 'plugins', 'mold',
                        'mold_management.db')
_DB_PATH = os.path.normpath(os.path.abspath(_DB_PATH))


def _get_conn():
    db_path = os.path.abspath(_DB_PATH)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"模具管理数据库不存在: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_projects(keyword: str = "", **kwargs) -> str:
    """查询项目列表。"""
    conn = _get_conn()
    query = "SELECT * FROM project_info"
    params = []
    if keyword:
        query += " WHERE mold_number LIKE ? OR customer_name LIKE ? OR product_name LIKE ?"
        kw = f"%{keyword}%"
        params = [kw, kw, kw]
    query += " ORDER BY created_at DESC LIMIT 50"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return "暂无模具项目。"

    lines = ["模具编号 | 客户名称 | 产品名称 | 模具类型 | 项目类型 | 启动日期",
             "-" * 80]
    for r in rows:
        lines.append(f"{r['mold_number'] or '-'} | {r['customer_name'] or '-'} | "
                     f"{r['product_name'] or '-'} | {r['mold_type'] or '-'} | "
                     f"{r['project_type'] or '-'} | {r['kickoff_date'] or '-'}")
    return "\n".join(lines)


def get_project(mold_number: str, **kwargs) -> str:
    """获取单个项目的完整信息。"""
    conn = _get_conn()
    project = conn.execute("SELECT * FROM project_info WHERE mold_number=?",
                          (mold_number,)).fetchone()
    if not project:
        conn.close()
        return f"未找到模具编号为 {mold_number} 的项目。"

    mold_info = conn.execute("SELECT * FROM mold_info WHERE mold_number=?",
                            (mold_number,)).fetchone()
    product_info = conn.execute("SELECT * FROM product_info WHERE mold_number=?",
                               (mold_number,)).fetchone()
    team_info = conn.execute("SELECT * FROM team_info WHERE mold_number=?",
                            (mold_number,)).fetchone()
    cost_rows = conn.execute("SELECT * FROM cost_items WHERE mold_number=? ORDER BY category, id",
                            (mold_number,)).fetchall()
    cost_data = {'quoted': [], 'actual': [], 'designed': []}
    for r in cost_rows:
        cat = r['category'] or 'quoted'
        if cat not in cost_data:
            cost_data[cat] = []
        cost_data[cat].append({'key': r['item_key'], 'value': r['item_value']})
    trial_count = conn.execute("SELECT COUNT(*) FROM trial_records WHERE mold_number=?",
                              (mold_number,)).fetchone()[0]
    issue_count = conn.execute("SELECT COUNT(*) FROM mold_issue_records WHERE mold_number=?",
                              (mold_number,)).fetchone()[0]
    conn.close()

    lines = [f"=== 项目概览: {mold_number} ===", ""]
    lines.append(f"客户: {project['customer_name'] or '-'}")
    lines.append(f"产品: {project['product_name'] or '-'}")
    lines.append(f"模具类型: {project['mold_type'] or '-'}")
    lines.append(f"项目类型: {project['project_type'] or '-'}")
    lines.append(f"订单号: {project['order_number'] or '-'}")
    lines.append(f"启动日期: {project['kickoff_date'] or '-'}")
    lines.append(f"SOP日期: {project['sop_date'] or '-'}")
    lines.append("")

    if mold_info:
        lines.append("--- 模具信息 ---")
        lines.append(f"模腔数: {mold_info['cavitation'] or '-'}")
        lines.append(f"流道类型: {mold_info['runner_type'] or '-'}")
        lines.append(f"浇口类型: {mold_info['gate_type'] or '-'}")
        lines.append(f"模具尺寸: {mold_info['mold_size'] or '-'}")
        lines.append(f"模架品牌: {mold_info['mold_base_brand'] or '-'}")
        lines.append("")

    if product_info:
        lines.append("--- 产品信息 ---")
        lines.append(f"产品编号: {product_info['product_number'] or '-'}")
        lines.append(f"图号: {product_info['drawing_number'] or '-'}")
        lines.append("")

    if team_info:
        lines.append("--- 团队信息 ---")
        for key, label in [('project_engineer', '项目工程师'),
                           ('mold_engineer', '模具工程师'),
                           ('mold_design_engineer', '模具设计工程师'),
                           ('sales_manager', '销售经理')]:
            val = team_info[key]
            if val:
                lines.append(f"  {label}: {val}")
        lines.append("")

    if any(cost_data.values()):
        lines.append("--- 成本信息 ---")
        for cat_label, cat_key in [('【报价成本】', 'quoted'), ('【实际成本】', 'actual'), ('【设计重量】', 'designed')]:
            items = cost_data.get(cat_key, [])
            if items:
                lines.append(f"  {cat_label}")
                for item in items:
                    lines.append(f"    {item['key']}: {item['value']}")
        lines.append("")

    lines.append(f"--- 统计 ---")
    lines.append(f"试模次数: {trial_count}")
    lines.append(f"问题记录: {issue_count}")

    return "\n".join(lines)


def list_molds(**kwargs) -> str:
    """查询模具信息列表。"""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM mold_info ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    if not rows:
        return "暂无模具信息。"
    lines = ["模具编号 | 模腔数 | 模具类型 | 流道类型 | 浇口类型 | 尺寸",
             "-" * 80]
    for r in rows:
        lines.append(f"{r['mold_number'] or '-'} | {r['cavitation'] or '-'} | "
                     f"{r['mold_type'] or '-'} | {r['runner_type'] or '-'} | "
                     f"{r['gate_type'] or '-'} | {r['mold_size'] or '-'}")
    return "\n".join(lines)


def list_trials(mold_number: str, **kwargs) -> str:
    """查询试模记录。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trial_records WHERE mold_number=? ORDER BY trial_number DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无试模记录。"
    lines = ["试模# | 优先级 | 开始日期 | 结束日期 | 机台 | 材料 | 原因 | 结果 | 负责人",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['trial_number'] or '-'} | {r['priority'] or '-'} | "
                     f"{r['trial_start_date'] or '-'} | {r['trial_end_date'] or '-'} | "
                     f"{r['trial_machine'] or '-'} | {r['material_number'] or '-'} | "
                     f"{r['trial_reason'] or '-'} | {r['trial_result'] or '-'} | "
                     f"{r['responsible_project_engineer'] or '-'}")
    return "\n".join(lines)


def list_open_items(mold_number: str, **kwargs) -> str:
    """查询待办事项。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM open_items WHERE mold_number=? ORDER BY deadline ASC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无待办事项。"
    lines = ["任务 | 负责人 | 截止日期 | 进度 | 状态",
             "-" * 80]
    for r in rows:
        status = "✓ 已完成" if r['is_done'] else "○ 进行中"
        lines.append(f"{r['todo_item'] or '-'} | {r['responsible_person'] or '-'} | "
                     f"{r['deadline'] or '-'} | {r['progress_notes'] or '-'} | {status}")
    return "\n".join(lines)


def list_events(mold_number: str, **kwargs) -> str:
    """查询事件记录。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM event_records WHERE mold_number=? ORDER BY event_date DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无事件记录。"
    lines = ["日期 | 事件描述", "-" * 60]
    for r in rows:
        lines.append(f"{r['event_date'] or '-'} | {r['event_description'] or '-'}")
    return "\n".join(lines)


def list_modifications(mold_number: str, **kwargs) -> str:
    """查询改模记录。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM mold_modification_records WHERE mold_number=? ORDER BY created_at DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无改模记录。"
    lines = ["试模# | 改模内容 | 预计完成日期 | 创建时间",
             "-" * 80]
    for r in rows:
        lines.append(f"{r['trial_number'] or '-'} | {r['modification_content'] or '-'} | "
                     f"{r['expected_completion_date'] or '-'} | {r['created_at'] or '-'}")
    return "\n".join(lines)


def list_issues(mold_number: str, **kwargs) -> str:
    """查询问题记录（从 mold_issue_records 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM mold_issue_records WHERE mold_number=? ORDER BY created_at DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无问题记录。"
    lines = ["试模# | 问题描述 | 解决方案 | 记录时间",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['trial_number'] or '-'} | {r['mold_issue'] or '-'} | "
                     f"{r['solution'] or '-'} | {r['created_at'] or '-'}")
    return "\n".join(lines)


def list_lessons(mold_number: str, **kwargs) -> str:
    """查询经验教训（从 lesson_learn 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM lesson_learn WHERE mold_number=? ORDER BY date DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无经验教训记录。"
    lines = ["问题描述 | 解决方案 | 附件 | 日期",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['issue_description'] or '-'} | {r['solution'] or '-'} | "
                     f"{r['attachment'] or '-'} | {r['date'] or '-'}")
    return "\n".join(lines)


def list_materials(mold_number: str, **kwargs) -> str:
    """查询材料信息（从 material_info 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM material_info WHERE mold_number=? ORDER BY id",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无材料信息。"
    lines = ["材料编号 | 材料名称 | 色粉编号 | 色粉名称 | 配色比例 | 采购量 | 库存量",
             "-" * 120]
    for r in rows:
        lines.append(f"{r['material_number'] or '-'} | {r['material_name'] or '-'} | "
                     f"{r['colorant_number'] or '-'} | {r['colorant_name'] or '-'} | "
                     f"{r['color_ratio'] or '-'} | {r['purchased_material_qty'] or '-'} | "
                     f"{r['material_stock'] or '-'}")
    return "\n".join(lines)



def list_changes(mold_number: str, **kwargs) -> str:
    """查询ECN变更记录（从 change_management 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM change_management WHERE mold_number=? ORDER BY change_date DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无变更记录。"
    lines = ["变更编号 | 变更内容 | 变更来源 | 变更日期",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['change_number'] or '-'} | {r['change_content'] or '-'} | "
                     f"{r['change_source'] or '-'} | {r['change_date'] or '-'}")
    return "\n".join(lines)


def list_cost_info(mold_number: str, **kwargs) -> str:
    """查询成本总表（从 cost_info 表）。"""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM cost_info WHERE mold_number=?", (mold_number,)).fetchone()
    conn.close()
    if not row:
        return f"模具 {mold_number} 暂无成本信息。"
    lines = [f"=== 成本信息: {mold_number} ===", ""]
    lines.append("--- 报价 ---")
    lines.append(f"  报价单号: {row['quotation_number'] or '-'}")
    lines.append(f"  模具成本: {row['quoted_mold_cost'] or '-'}")
    lines.append(f"  测量治具: {row['quoted_measurement_fixture_cost'] or '-'}")
    lines.append(f"  EOAT: {row['quoted_eoat_cost'] or '-'}")
    lines.append(f"  产品重量: {row['quoted_product_weight'] or '-'}")
    lines.append(f"  模腔数: {row['quoted_cavity_number'] or '-'}")
    lines.append(f"  流道重量: {row['quoted_runner_weight'] or '-'}")
    lines.append(f"  周期时间: {row['quoted_cycle_time'] or '-'}")
    lines.append("")
    lines.append("--- 实际 ---")
    lines.append(f"  模具成本: {row['actual_mold_cost'] or '-'}")
    lines.append(f"  测量治具: {row['actual_measurement_fixture_cost'] or '-'}")
    lines.append(f"  EOAT: {row['actual_eoat_cost'] or '-'}")
    lines.append(f"  产品重量: {row['actual_product_weight'] or '-'}")
    lines.append(f"  流道重量: {row['actual_runner_weight'] or '-'}")
    lines.append(f"  周期时间: {row['actual_cycle_time'] or '-'}")
    lines.append("")
    lines.append("--- 设计 ---")
    lines.append(f"  产品重量: {row['designed_product_weight'] or '-'}")
    lines.append(f"  流道重量: {row['designed_runner_weight'] or '-'}")
    return "\n".join(lines)


def list_dimension_reports(mold_number: str, **kwargs) -> str:
    """查询尺寸检测报告（从 dimensional_reports 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM dimensional_reports WHERE mold_number=? ORDER BY created_at DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无尺寸报告。"
    lines = ["试模# | 报告路径 | 创建时间",
             "-" * 80]
    for r in rows:
        lines.append(f"{r['trial_number'] or '-'} | {r['dimensional_report_path'] or '-'} | "
                     f"{r['created_at'] or '-'}")
    return "\n".join(lines)


def list_injection_info(mold_number: str, **kwargs) -> str:
    """查询注塑成型信息（从 injection_molding_info 表）。"""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM injection_molding_info WHERE mold_number=?", (mold_number,)).fetchone()
    conn.close()
    if not row:
        return f"模具 {mold_number} 暂无注塑成型信息。"
    yes_no = lambda v: "是" if v else "否"
    lines = [f"=== 注塑成型信息: {mold_number} ===", ""]
    lines.append(f"  机台编号: {row['machine_number'] or '-'}")
    lines.append(f"  机台吨位: {row['machine_tonnage'] or '-'}")
    lines.append(f"  需要EOAT: {yes_no(row['requires_eoat'])}")
    lines.append(f"  需要压力传感器: {yes_no(row['requires_pressure_sensor'])}")
    lines.append(f"  需要热流道控制器: {yes_no(row['requires_hot_runner_controller'])}")
    lines.append(f"  需要中子: {yes_no(row['requires_core_pulling'])}")
    lines.append(f"  需要高温模温机: {yes_no(row['requires_high_temp_mold_temperature_controller'])}")
    lines.append(f"  需要冷冻机: {yes_no(row['requires_chiller'])}")
    return "\n".join(lines)


def list_packaging(mold_number: str, **kwargs) -> str:
    """查询包装要求（从 packaging_requirements 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM packaging_requirements WHERE mold_number=? ORDER BY id",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无包装要求。"
    lines = ["产品编号 | 产品名称 | 包装方式 | 包装指导附件",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['product_number'] or '-'} | {r['product_name'] or '-'} | "
                     f"{r['packaging_details'] or '-'} | {r['packaging_instruction_attachment_path'] or '-'}")
    return "\n".join(lines)


def list_shipments(mold_number: str, **kwargs) -> str:
    """查询样品寄送记录（从 sample_shipment_records 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM sample_shipment_records WHERE mold_number=? ORDER BY shipping_date DESC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无样品寄送记录。"
    lines = ["寄送日期 | 快递公司 | 运单号 | 收件公司 | 收件人 | 电话 | 是否签收",
             "-" * 120]
    for r in rows:
        received = "是" if r['is_received'] else "否"
        lines.append(f"{r['shipping_date'] or '-'} | {r['express_company_name'] or '-'} | "
                     f"{r['tracking_number'] or '-'} | {r['recipient_company'] or '-'} | "
                     f"{r['recipient_name'] or '-'} | {r['recipient_phone'] or '-'} | {received}")
    return "\n".join(lines)


def list_timeline_tasks(mold_number: str, **kwargs) -> str:
    """查询时间线任务（从 timeline_tasks 表）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM timeline_tasks WHERE mold_number=? ORDER BY start_date ASC",
        (mold_number,)).fetchall()
    conn.close()
    if not rows:
        return f"模具 {mold_number} 暂无时间线任务。"
    lines = ["任务名称 | 开始日期 | 结束日期 | 负责人 | 状态 | 进度说明",
             "-" * 100]
    for r in rows:
        lines.append(f"{r['task_name'] or '-'} | {r['start_date'] or '-'} | "
                     f"{r['end_date'] or '-'} | {r['responsible_person'] or '-'} | "
                     f"{r['status'] or '-'} | {r['notes'] or '-'}")
    return "\n".join(lines)


# ── 入口 ────────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """模具项目管理入口。

    Args:
        action: 操作类型
        keyword: 搜索关键词
        mold_number: 模具编号
    """
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = params.get("action") or action or kwargs.get("action", "")
    keyword = params.get("keyword") or kwargs.get("keyword", "")
    mold_number = params.get("mold_number") or kwargs.get("mold_number", "")

    try:
        if action == "list_projects":
            return list_projects(keyword=keyword)
        elif action == "get_project":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return get_project(mold_number)
        elif action == "list_molds":
            return list_molds()
        elif action == "list_trials":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_trials(mold_number)
        elif action == "list_open_items":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_open_items(mold_number)
        elif action == "list_events":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_events(mold_number)
        elif action == "list_modifications":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_modifications(mold_number)
        elif action == "list_issues":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_issues(mold_number)
        elif action == "list_lessons":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_lessons(mold_number)
        elif action == "list_materials":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_materials(mold_number)
        elif action == "list_changes":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_changes(mold_number)
        elif action == "list_cost_info":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_cost_info(mold_number)
        elif action == "list_dimension_reports":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_dimension_reports(mold_number)
        elif action == "list_injection_info":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_injection_info(mold_number)
        elif action == "list_packaging":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_packaging(mold_number)
        elif action == "list_shipments":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_shipments(mold_number)
        elif action == "list_timeline_tasks":
            if not mold_number:
                return json.dumps({"success": False, "error": "缺少 mold_number"})
            return list_timeline_tasks(mold_number)
        else:
            return ("模具管理工具 (mold_management)\n"
                    "用法: run(action='操作类型', ...)\n\n"
                    "支持的操作:\n"
                    "  list_projects     — 查询项目列表（可选 keyword）\n"
                    "  get_project       — 获取项目详情（需 mold_number）\n"
                    "  list_molds        — 查询模具列表\n"
                    "  list_trials       — 查询试模记录（需 mold_number）\n"
                    "  list_open_items   — 查询待办事项（需 mold_number）\n"
                    "  list_events       — 查询事件记录（需 mold_number）\n"
                    "  list_modifications — 查询改模记录（需 mold_number）\n"
                    "  list_issues        — 查询问题记录（需 mold_number）\n"
                    "  list_lessons       — 查询经验教训（需 mold_number）\n"
                    "  list_materials     — 查询材料信息（需 mold_number）\n"
                    "  list_changes       — 查询ECN变更记录（需 mold_number）\n"
                    "  list_cost_info     — 查询成本总表（需 mold_number）\n"
                    "  list_dimension_reports — 查询尺寸检测报告（需 mold_number）\n"
                    "  list_injection_info — 查询注塑成型信息（需 mold_number）\n"
                    "  list_packaging     — 查询包装要求（需 mold_number）\n"
                    "  list_shipments     — 查询样品寄送记录（需 mold_number）\n"
                    "  list_timeline_tasks — 查询时间线任务（需 mold_number）\n\n"
                    "示例:\n"
                    "  run(action='list_projects')\n"
                    "  run(action='get_project', mold_number='M26007')\n"
                    "  run(action='list_trials', mold_number='M26007')")
    except FileNotFoundError as e:
        return json.dumps({"success": False, "error": str(e)})
    except Exception as e:
        return json.dumps({"success": False, "error": f"错误: {e}"})
