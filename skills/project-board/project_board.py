"""project_board Skill — 模具项目看板生成。

根据模具编号从模具数据库和主数据库获取数据，
生成可视化的 HTML 看板，展示项目全貌。
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILL_DIR = Path(__file__).resolve().parent
_MOLD_DB = _PROJECT_ROOT / "app" / "plugins" / "mold" / "mold_management.db"
_SANDBOX_DIR = _PROJECT_ROOT / "sandbox"


def _get_mold_conn():
    """连接模具数据库。"""
    db_path = os.path.normpath(str(_MOLD_DB))
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"模具管理数据库不存在: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _get_project_data(mold_number: str) -> dict:
    """获取模具项目的完整数据。"""
    conn = _get_mold_conn()
    try:
        project = conn.execute(
            "SELECT * FROM project_info WHERE mold_number=?", (mold_number,)
        ).fetchone()
        if not project:
            return {"error": f"未找到模具编号 {mold_number}"}

        project = dict(project)

        # 模具信息
        mold = conn.execute(
            "SELECT * FROM mold_info WHERE mold_number=?", (mold_number,)
        ).fetchone()
        project["mold"] = dict(mold) if mold else {}

        # 产品信息
        product = conn.execute(
            "SELECT * FROM product_info WHERE mold_number=?", (mold_number,)
        ).fetchone()
        project["product"] = dict(product) if product else {}

        # 团队信息
        team = conn.execute(
            "SELECT * FROM team_info WHERE mold_number=?", (mold_number,)
        ).fetchone()
        project["team"] = dict(team) if team else {}

        # 试模记录
        trials = conn.execute(
            "SELECT * FROM trial_records WHERE mold_number=? ORDER BY trial_date DESC",
            (mold_number,),
        ).fetchall()
        project["trials"] = [dict(r) for r in trials]

        # 问题记录
        issues = conn.execute(
            "SELECT * FROM mold_issue_records WHERE mold_number=? ORDER BY created_at DESC",
            (mold_number,),
        ).fetchall()
        project["issues"] = [dict(r) for r in issues]

        # 成本数据
        costs = conn.execute(
            "SELECT * FROM cost_items WHERE mold_number=? ORDER BY category, id",
            (mold_number,),
        ).fetchall()
        project["costs"] = [dict(r) for r in costs]

        # 时间线
        timeline = conn.execute(
            "SELECT * FROM timeline_tasks WHERE mold_number=? ORDER BY planned_start",
            (mold_number,),
        ).fetchall()
        project["timeline"] = [dict(r) for r in timeline]

        # 改模记录
        modifications = conn.execute(
            "SELECT * FROM modification_records WHERE mold_number=? ORDER BY created_at DESC",
            (mold_number,),
        ).fetchall()
        project["modifications"] = [dict(r) for r in modifications]

        # 经验教训
        lessons = conn.execute(
            "SELECT * FROM lesson_learn WHERE mold_number=? ORDER BY created_at DESC",
            (mold_number,),
        ).fetchall()
        project["lessons"] = [dict(r) for r in lessons]

        return project
    finally:
        conn.close()


def _get_todo_stats(mold_number: str) -> dict:
    """从主数据库获取待办统计。"""
    try:
        from flask import current_app
        from app import create_app

        app = create_app()
        with app.app_context():
            from app.extensions.init_sqlalchemy import db
            from app.models.todo import Todo

            total = Todo.query.filter_by(mold_number=mold_number).count()
            done = Todo.query.filter_by(mold_number=mold_number, done=True).count()
            pending = total - done
            return {
                "total": total,
                "done": done,
                "pending": pending,
                "completion_rate": round(done / total * 100, 1) if total > 0 else 0,
            }
    except Exception:
        return {"total": 0, "done": 0, "pending": 0, "completion_rate": 0}


def _generate_html(data: dict, mold_number: str) -> str:
    """生成 HTML 看板。"""
    p = data  # project data
    mold = p.get("mold", {})
    product = p.get("product", {})
    team = p.get("team", {})
    trials = p.get("trials", [])
    issues = p.get("issues", [])
    costs = p.get("costs", [])
    timeline = p.get("timeline", [])
    modifications = p.get("modifications", [])
    lessons = p.get("lessons", [])

    # 成本分类统计
    cost_quoted = sum(float(c["item_value"]) for c in costs if c.get("category") == "quoted" and c.get("item_value"))
    cost_actual = sum(float(c["item_value"]) for c in costs if c.get("category") == "actual" and c.get("item_value"))
    cost_designed = sum(float(c["item_value"]) for c in costs if c.get("category") == "designed" and c.get("item_value"))

    # 试模统计
    trial_ok = sum(1 for t in trials if t.get("result") and "OK" in str(t.get("result", "")))
    trial_ng = len(trials) - trial_ok

    # 问题统计
    issue_open = sum(1 for i in issues if i.get("status") and "open" in str(i.get("status", "")).lower())
    issue_closed = len(issues) - issue_open

    # 时间线进度
    timeline_done = sum(1 for t in timeline if t.get("status") and "done" in str(t.get("status", "")).lower())
    timeline_total = len(timeline)

    # 待办统计
    todo_stats = _get_todo_stats(mold_number)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>项目看板 - {mold_number}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #333; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 24px; }}
.header h1 {{ font-size: 28px; margin-bottom: 8px; }}
.header .meta {{ opacity: 0.9; font-size: 14px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.card h3 {{ font-size: 14px; color: #666; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 1px; }}
.card .value {{ font-size: 32px; font-weight: 700; color: #333; }}
.card .sub {{ font-size: 13px; color: #999; margin-top: 4px; }}
.section {{ background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.section h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #667eea; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f8f9fa; font-weight: 600; color: #555; }}
tr:hover {{ background: #f8f9fa; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.badge-ok {{ background: #d4edda; color: #155724; }}
.badge-ng {{ background: #f8d7da; color: #721c24; }}
.badge-open {{ background: #fff3cd; color: #856404; }}
.badge-closed {{ background: #d4edda; color: #155724; }}
.badge-done {{ background: #d4edda; color: #155724; }}
.badge-pending {{ background: #fff3cd; color: #856404; }}
.progress-bar {{ height: 8px; background: #e9ecef; border-radius: 4px; margin-top: 8px; overflow: hidden; }}
.progress-bar .fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
.progress-bar .fill.green {{ background: linear-gradient(90deg, #28a745, #20c997); }}
.progress-bar .fill.blue {{ background: linear-gradient(90deg, #667eea, #764ba2); }}
.progress-bar .fill.orange {{ background: linear-gradient(90deg, #ffc107, #fd7e14); }}
.info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }}
.info-item {{ padding: 8px 0; }}
.info-item .label {{ font-size: 12px; color: #999; }}
.info-item .val {{ font-size: 14px; font-weight: 500; }}
.footer {{ text-align: center; color: #999; font-size: 12px; padding: 20px; }}
</style>
</head>
<body>

<div class="header">
    <h1>📊 项目看板 — {mold_number}</h1>
    <div class="meta">
        客户: {p.get('customer_name', '-')} | 产品: {p.get('product_name', '-')} |
        模具类型: {p.get('mold_type', '-')} | 项目类型: {p.get('project_type', '-')} |
        生成时间: {now}
    </div>
</div>

<!-- 概览卡片 -->
<div class="grid">
    <div class="card">
        <h3>📋 项目进度</h3>
        <div class="value">{timeline_done}/{timeline_total}</div>
        <div class="sub">时间线任务完成</div>
        <div class="progress-bar">
            <div class="fill {'green' if timeline_total > 0 else ''}" style="width: {(timeline_done/timeline_total*100) if timeline_total > 0 else 0}%"></div>
        </div>
    </div>
    <div class="card">
        <h3>🔧 试模</h3>
        <div class="value">{len(trials)}</div>
        <div class="sub">OK: {trial_ok} | NG: {trial_ng}</div>
        <div class="progress-bar">
            <div class="fill {'green' if len(trials) > 0 else ''}" style="width: {(trial_ok/len(trials)*100) if len(trials) > 0 else 0}%"></div>
        </div>
    </div>
    <div class="card">
        <h3>⚠️ 问题</h3>
        <div class="value">{len(issues)}</div>
        <div class="sub">未关闭: {issue_open} | 已关闭: {issue_closed}</div>
        <div class="progress-bar">
            <div class="fill {'green' if len(issues) > 0 else ''}" style="width: {(issue_closed/len(issues)*100) if len(issues) > 0 else 0}%"></div>
        </div>
    </div>
    <div class="card">
        <h3>💰 成本</h3>
        <div class="value">¥{cost_actual:,.0f}</div>
        <div class="sub">预算: ¥{cost_quoted:,.0f} | 差异: ¥{cost_actual - cost_quoted:+,.0f}</div>
        <div class="progress-bar">
            <div class="fill {'orange' if cost_quoted > 0 else ''}" style="width: {min((cost_actual/cost_quoted*100), 100) if cost_quoted > 0 else 0}%"></div>
        </div>
    </div>
    <div class="card">
        <h3>✅ 待办</h3>
        <div class="value">{todo_stats['done']}/{todo_stats['total']}</div>
        <div class="sub">完成率: {todo_stats['completion_rate']}% | 待处理: {todo_stats['pending']}</div>
        <div class="progress-bar">
            <div class="fill blue" style="width: {todo_stats['completion_rate']}%"></div>
        </div>
    </div>
    <div class="card">
        <h3>🔄 改模</h3>
        <div class="value">{len(modifications)}</div>
        <div class="sub">经验教训: {len(lessons)} 条</div>
    </div>
</div>

<!-- 项目信息 -->
<div class="section">
    <h2>📄 项目信息</h2>
    <div class="info-grid">
        <div class="info-item"><div class="label">模具编号</div><div class="val">{mold_number}</div></div>
        <div class="info-item"><div class="label">客户名称</div><div class="val">{p.get('customer_name', '-')}</div></div>
        <div class="info-item"><div class="label">产品名称</div><div class="val">{p.get('product_name', '-')}</div></div>
        <div class="info-item"><div class="label">模具类型</div><div class="val">{p.get('mold_type', '-')}</div></div>
        <div class="info-item"><div class="label">项目类型</div><div class="val">{p.get('project_type', '-')}</div></div>
        <div class="info-item"><div class="label">启动日期</div><div class="val">{p.get('kickoff_date', '-')}</div></div>
        <div class="info-item"><div class="label">模具尺寸</div><div class="val">{mold.get('mold_size', '-')}</div></div>
        <div class="info-item"><div class="label">模具重量</div><div class="val">{mold.get('mold_weight', '-')}</div></div>
        <div class="info-item"><div class="label">型腔数</div><div class="val">{mold.get('cavity_count', '-')}</div></div>
        <div class="info-item"><div class="label">产品材料</div><div class="val">{product.get('material', '-')}</div></div>
        <div class="info-item"><div class="label">产品重量</div><div class="val">{product.get('product_weight', '-')}</div></div>
        <div class="info-item"><div class="label">收缩率</div><div class="val">{product.get('shrinkage_rate', '-')}</div></div>
    </div>
</div>

<!-- 团队信息 -->
<div class="section">
    <h2>👥 项目团队</h2>
    <div class="info-grid">
        <div class="info-item"><div class="label">项目经理</div><div class="val">{team.get('project_manager', '-')}</div></div>
        <div class="info-item"><div class="label">模具设计</div><div class="val">{team.get('mold_designer', '-')}</div></div>
        <div class="info-item"><div class="label">模具制造</div><div class="val">{team.get('mold_maker', '-')}</div></div>
        <div class="info-item"><div class="label">品质</div><div class="val">{team.get('quality_engineer', '-')}</div></div>
        <div class="info-item"><div class="label">项目工程师</div><div class="val">{team.get('project_engineer', '-')}</div></div>
    </div>
</div>

<!-- 时间线 -->
<div class="section">
    <h2>📅 时间线</h2>
    <table>
        <tr><th>任务</th><th>计划开始</th><th>计划完成</th><th>实际完成</th><th>状态</th></tr>
"""
    for t in timeline:
        status = str(t.get("status", "") or "")
        badge_class = "badge-done" if "done" in status.lower() else "badge-pending"
        html += f"        <tr><td>{t.get('task_name', '-')}</td><td>{t.get('planned_start', '-')}</td><td>{t.get('planned_end', '-')}</td><td>{t.get('actual_end', '-')}</td><td><span class='badge {badge_class}'>{status}</span></td></tr>\n"

    html += """    </table>
</div>

<!-- 试模记录 -->
<div class="section">
    <h2>🔧 试模记录</h2>
    <table>
        <tr><th>日期</th><th>试模次数</th><th>结果</th><th>备注</th></tr>
"""
    for t in trials:
        result = str(t.get("result", "") or "")
        badge_class = "badge-ok" if "OK" in result else "badge-ng"
        html += f"        <tr><td>{t.get('trial_date', '-')}</td><td>{t.get('trial_count', '-')}</td><td><span class='badge {badge_class}'>{result}</span></td><td>{t.get('remarks', '-')}</td></tr>\n"

    html += """    </table>
</div>

<!-- 问题记录 -->
<div class="section">
    <h2>⚠️ 问题记录</h2>
    <table>
        <tr><th>问题描述</th><th>提出人</th><th>状态</th><th>创建时间</th></tr>
"""
    for i in issues:
        status = str(i.get("status", "") or "")
        badge_class = "badge-closed" if "close" in status.lower() else "badge-open"
        html += f"        <tr><td>{i.get('issue_description', '-')[:60]}</td><td>{i.get('reported_by', '-')}</td><td><span class='badge {badge_class}'>{status}</span></td><td>{i.get('created_at', '-')}</td></tr>\n"

    html += """    </table>
</div>

<!-- 成本明细 -->
<div class="section">
    <h2>💰 成本明细</h2>
    <table>
        <tr><th>类别</th><th>项目</th><th>金额</th></tr>
"""
    for c in costs:
        html += f"        <tr><td>{c.get('category', '-')}</td><td>{c.get('item_key', '-')}</td><td>¥{float(c.get('item_value', 0)):,.0f}</td></tr>\n"

    html += f"""    </table>
    <p style="margin-top:12px;font-size:14px;color:#666;">
        报价合计: ¥{cost_quoted:,.0f} | 实际合计: ¥{cost_actual:,.0f} | 差异: <strong style="color:{'#dc3545' if cost_actual > cost_quoted else '#28a745'}">¥{cost_actual - cost_quoted:+,.0f}</strong>
    </p>
</div>

<!-- 改模记录 -->
<div class="section">
    <h2>🔄 改模记录</h2>
    <table>
        <tr><th>改模内容</th><th>原因</th><th>状态</th><th>日期</th></tr>
"""
    for m in modifications:
        html += f"        <tr><td>{m.get('modification_content', '-')[:50]}</td><td>{m.get('reason', '-')[:40]}</td><td>{m.get('status', '-')}</td><td>{m.get('created_at', '-')}</td></tr>\n"

    html += """    </table>
</div>

<!-- 经验教训 -->
<div class="section">
    <h2>📚 经验教训</h2>
    <table>
        <tr><th>类别</th><th>内容</th><th>提出人</th></tr>
"""
    for l in lessons:
        html += f"        <tr><td>{l.get('category', '-')}</td><td>{l.get('content', '-')[:80]}</td><td>{l.get('author', '-')}</td></tr>\n"

    html += f"""    </table>
</div>

<div class="footer">
    项目看板 - {mold_number} | 生成时间: {now} | DeepAgent Project Board
</div>

</body>
</html>"""
    return html


def _save_board(mold_number: str, html_content: str) -> dict:
    """保存看板 HTML 文件并记录到数据库。"""
    # 保存 HTML 文件
    _SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"board_{mold_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = _SANDBOX_DIR / filename
    filepath.write_text(html_content, encoding="utf-8")

    # 记录到数据库
    board_id = None
    try:
        from flask import current_app
        from app import create_app

        app = create_app()
        with app.app_context():
            from app.extensions.init_sqlalchemy import db
            from sqlalchemy import Column, Integer, String, Text, DateTime

            class ProjectBoard(db.Model):
                __tablename__ = "project_boards"
                id = Column(Integer, primary_key=True)
                mold_number = Column(String(64), nullable=False)
                html_file = Column(String(256), nullable=False)
                created_at = Column(db.DateTime, default=lambda: datetime.now())

            db.create_all()
            record = ProjectBoard(
                mold_number=mold_number,
                html_file=str(filepath),
            )
            db.session.add(record)
            db.session.commit()
            board_id = record.id
    except Exception:
        pass

    return {
        "board_id": board_id,
        "mold_number": mold_number,
        "html_file": str(filepath),
        "url": f"/sandbox/{filename}",
    }


def _list_boards(keyword: str = "", limit: int = 20) -> list:
    """查询看板列表。"""
    try:
        from flask import current_app
        from app import create_app

        app = create_app()
        with app.app_context():
            from app.extensions.init_sqlalchemy import db
            from sqlalchemy import Column, Integer, String, DateTime

            class ProjectBoard(db.Model):
                __tablename__ = "project_boards"
                id = Column(Integer, primary_key=True)
                mold_number = Column(String(64))
                html_file = Column(String(256))
                created_at = Column(db.DateTime)

            query = ProjectBoard.query
            if keyword:
                query = query.filter(ProjectBoard.mold_number.like(f"%{keyword}%"))
            records = query.order_by(ProjectBoard.created_at.desc()).limit(min(limit, 100)).all()

            result = []
            for r in records:
                result.append({
                    "id": r.id,
                    "mold_number": r.mold_number,
                    "html_file": r.html_file,
                    "created_at": str(r.created_at) if r.created_at else "",
                })
            return result
    except Exception:
        return []


def _get_board(board_id: int) -> dict:
    """获取看板详情。"""
    try:
        from flask import current_app
        from app import create_app

        app = create_app()
        with app.app_context():
            from app.extensions.init_sqlalchemy import db
            from sqlalchemy import Column, Integer, String, DateTime

            class ProjectBoard(db.Model):
                __tablename__ = "project_boards"
                id = Column(Integer, primary_key=True)
                mold_number = Column(String(64))
                html_file = Column(String(256))
                created_at = Column(db.DateTime)

            record = ProjectBoard.query.get(board_id)
            if not record:
                return {"error": f"未找到 ID 为 {board_id} 的看板"}

            return {
                "id": record.id,
                "mold_number": record.mold_number,
                "html_file": record.html_file,
                "created_at": str(record.created_at) if record.created_at else "",
            }
    except Exception as e:
        return {"error": str(e)}


# ── 入口函数 ──────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """模具项目看板生成。

    Args:
        expression: JSON 字符串
        action: "generate" / "list" / "get"
        **kwargs: 见 SKILL.md 参数说明

    Returns:
        JSON 字符串
    """
    # 解析参数
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = params.get("action") or action or "generate"
    mold_number = params.get("mold_number") or kwargs.get("mold_number", "")
    board_id = params.get("board_id") or kwargs.get("board_id", 0)
    keyword = params.get("keyword") or kwargs.get("keyword", "")
    limit = params.get("limit") or kwargs.get("limit", 20)

    # ── list: 查询列表 ───────────────────────────────────────────────
    if action == "list":
        try:
            records = _list_boards(keyword=keyword, limit=int(limit))
            return json.dumps({
                "success": True,
                "records": records,
                "total": len(records),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"查询失败: {e}",
            }, ensure_ascii=False)

    # ── get: 查看详情 ────────────────────────────────────────────────
    if action == "get":
        try:
            board_id = int(board_id)
        except (ValueError, TypeError):
            return json.dumps({
                "success": False,
                "error": "board_id 必须是整数",
            }, ensure_ascii=False)
        record = _get_board(board_id)
        if "error" in record:
            return json.dumps({
                "success": False,
                "error": record["error"],
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "record": record,
        }, ensure_ascii=False)

    # ── generate: 生成看板 ───────────────────────────────────────────
    if not mold_number:
        return json.dumps({
            "success": False,
            "error": "缺少必需参数 mold_number（模具编号）",
        }, ensure_ascii=False)

    try:
        data = _get_project_data(mold_number)
        if "error" in data:
            return json.dumps({
                "success": False,
                "error": data["error"],
            }, ensure_ascii=False)

        html = _generate_html(data, mold_number)
        saved = _save_board(mold_number, html)

        return json.dumps({
            "success": True,
            "board_id": saved["board_id"],
            "mold_number": saved["mold_number"],
            "html_file": saved["html_file"],
            "url": saved["url"],
            "message": f"看板已生成: {saved['url']}",
        }, ensure_ascii=False)

    except FileNotFoundError as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"生成看板失败: {e}",
        }, ensure_ascii=False)
