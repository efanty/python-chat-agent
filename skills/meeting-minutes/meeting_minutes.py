"""meeting_minutes Skill — 会议纪要管理。

根据会议笔记或录音转文字内容，自动生成结构化会议纪要，
包含议题、讨论、决议、待办事项，并自动创建待办任务。
"""

import json
import re
from datetime import datetime, date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── 全局 MeetingMinutes 模型（只定义一次） ──────────────────────────────
_MeetingMinutes = None


def _get_meeting_minutes_model():
    """获取或创建 MeetingMinutes 模型（单例，避免重复定义表）。"""
    global _MeetingMinutes
    if _MeetingMinutes is not None:
        return _MeetingMinutes

    from app.extensions.init_sqlalchemy import db
    from sqlalchemy import Column, Integer, Text, DateTime, Date, String, ForeignKey

    class MeetingMinutes(db.Model):
        __tablename__ = "meeting_minutes"
        __table_args__ = {"extend_existing": True}
        id = Column(Integer, primary_key=True)
        title = Column(String(256), nullable=False)
        content = Column(Text, nullable=False)
        formatted = Column(Text, nullable=False)
        summary = Column(String(512), default="")
        participants = Column(String(512), default="")
        meeting_date = Column(Date, nullable=True)
        topics_count = Column(Integer, default=0)
        decisions_count = Column(Integer, default=0)
        action_items_count = Column(Integer, default=0)
        author_id = Column(Integer, ForeignKey('users.id'))
        created_at = Column(DateTime, default=lambda: datetime.now())

    _MeetingMinutes = MeetingMinutes
    return _MeetingMinutes


def _ensure_app_context():
    """确保 Flask 应用上下文可用。"""
    from flask import current_app
    try:
        _ = current_app.name
        return None
    except RuntimeError:
        pass
    from app import create_app
    app = create_app()
    ctx = app.app_context()
    ctx.push()
    return ctx


def _cleanup_context(ctx):
    if ctx is not None:
        ctx.pop()


def _get_todo_model():
    """获取 Todo 模型类。"""
    from app.models.todo import Todo
    return Todo


def _get_db():
    """获取 db 实例。"""
    from app.extensions.init_sqlalchemy import db
    return db


def _parse_meeting_content(content: str) -> dict:
    """解析会议内容，提取结构化信息。

    支持两种格式：
    1. 带标记的结构化文本（议题、决议、待办）
    2. 纯文本（自动提取关键信息）
    """
    result = {
        "topics": [],
        "decisions": [],
        "action_items": [],
        "summary": "",
    }

    if not content:
        return result

    lines = content.strip().split("\n")
    current_topic = ""
    current_topic_discussion = []
    in_action_items = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 检测议题/议题标记
        topic_match = re.match(r'^(?:议题|主题|Topic|议题\d*[.、：:])\s*(.*)', stripped)
        if topic_match:
            if current_topic:
                result["topics"].append({
                    "title": current_topic,
                    "discussion": "\n".join(current_topic_discussion).strip(),
                })
                current_topic_discussion = []
            current_topic = topic_match.group(1).strip() or f"议题 {len(result['topics']) + 1}"
            in_action_items = False
            continue

        # 检测决议标记
        decision_match = re.match(r'^(?:决议|决定|结论|Decision|决议\d*[.、：:])\s*(.*)', stripped)
        if decision_match:
            decision_text = decision_match.group(1).strip()
            if decision_text:
                result["decisions"].append(decision_text)
            continue

        # 检测待办事项区域
        if re.match(r'^(?:待办|待办事项|行动项|Action|ToDo|TODO|下一步)', stripped):
            in_action_items = True
            continue

        # 待办事项行
        if in_action_items:
            action_match = re.match(r'^[\d.、\-\*]\s*(.*)', stripped)
            if action_match:
                item_text = action_match.group(1).strip()
                # 尝试解析 "负责人 - 事项 - 截止日期" 格式
                parts = re.split(r'[-–—]', item_text)
                if len(parts) >= 2:
                    action_item = {
                        "assignee": parts[0].strip(),
                        "task": parts[1].strip(),
                        "due_date": parts[2].strip() if len(parts) >= 3 else "",
                    }
                else:
                    action_item = {
                        "assignee": "",
                        "task": item_text,
                        "due_date": "",
                    }
                result["action_items"].append(action_item)
                continue
            else:
                # 非列表格式的待办文本
                if stripped and not stripped.startswith("//"):
                    result["action_items"].append({
                        "assignee": "",
                        "task": stripped,
                        "due_date": "",
                    })
                continue

        # 收集当前议题的讨论内容
        if current_topic:
            current_topic_discussion.append(stripped)

    # 保存最后一个议题
    if current_topic:
        result["topics"].append({
            "title": current_topic,
            "discussion": "\n".join(current_topic_discussion).strip(),
        })

    # 生成摘要
    topic_titles = [t["title"] for t in result["topics"]]
    if topic_titles:
        result["summary"] = f"讨论了{'、'.join(topic_titles[:3])}"
        if len(topic_titles) > 3:
            result["summary"] += f"等 {len(topic_titles)} 个议题"
    elif result["decisions"]:
        result["summary"] = result["decisions"][0][:80]
    else:
        # 取前100字作为摘要
        result["summary"] = content.strip()[:100].replace("\n", " ")

    return result


def _generate_action(parsed: dict, title: str, meeting_date: str, author_id: int = 1) -> list:
    """根据解析结果创建待办事项。"""
    ctx = _ensure_app_context()
    try:
        Todo = _get_todo_model()
        db = _get_db()
        created = []

        for item in parsed.get("action_items", []):
            task_text = item.get("task", "").strip()
            if not task_text:
                continue

            # 构建待办内容
            todo_body = f"[{title}] {task_text}"
            if item.get("assignee"):
                todo_body = f"[{title}] {task_text}（负责人：{item['assignee']}）"

            # 解析截止日期
            due = None
            due_str = item.get("due_date", "").strip()
            if due_str:
                try:
                    # 尝试多种日期格式
                    for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%m-%d", "%m/%d"]:
                        try:
                            parsed_date = datetime.strptime(due_str, fmt)
                            if fmt in ("%m-%d", "%m/%d"):
                                parsed_date = parsed_date.replace(year=datetime.now().year)
                            due = parsed_date.date()
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            todo = Todo(
                body=todo_body,
                done=False,
                author_id=author_id,
                due_date=due or (datetime.strptime(meeting_date, "%Y-%m-%d").date() if meeting_date else None),
            )
            db.session.add(todo)
            db.session.flush()
            created.append({
                "todo_id": todo.id,
                "task": task_text,
                "assignee": item.get("assignee", ""),
                "due_date": str(due) if due else "",
            })

        db.session.commit()
        return created
    except Exception as e:
        raise RuntimeError(f"创建待办失败: {e}")
    finally:
        _cleanup_context(ctx)


def _format_minutes(parsed: dict, title: str, meeting_date: str, participants: str) -> str:
    """格式化会议纪要文本。"""
    lines = []
    lines.append(f"# {title}")
    lines.append(f"**日期**: {meeting_date}")
    if participants:
        lines.append(f"**参会人员**: {participants}")
    lines.append("")

    # 议题
    if parsed.get("topics"):
        lines.append("## 议题")
        for i, topic in enumerate(parsed["topics"], 1):
            lines.append(f"### {i}. {topic['title']}")
            if topic.get("discussion"):
                lines.append(topic["discussion"])
            lines.append("")

    # 决议
    if parsed.get("decisions"):
        lines.append("## 决议")
        for d in parsed["decisions"]:
            lines.append(f"- {d}")
        lines.append("")

    # 待办
    if parsed.get("action_items"):
        lines.append("## 待办事项")
        for item in parsed["action_items"]:
            parts = []
            if item.get("assignee"):
                parts.append(f"负责人: {item['assignee']}")
            if item.get("due_date"):
                parts.append(f"截止: {item['due_date']}")
            suffix = f"（{'，'.join(parts)}）" if parts else ""
            lines.append(f"- {item['task']}{suffix}")
        lines.append("")

    # 摘要
    if parsed.get("summary"):
        lines.append(f"**摘要**: {parsed['summary']}")

    return "\n".join(lines)


def _save_to_db(title: str, content: str, meeting_date: str, participants: str,
                parsed: dict, formatted: str, author_id: int = 1) -> dict:
    """将会议纪要保存到数据库。"""
    ctx = _ensure_app_context()
    try:
        db = _get_db()
        MeetingMinutes = _get_meeting_minutes_model()

        # 确保表存在
        from flask import current_app
        with current_app.app_context():
            from app.extensions.init_sqlalchemy import db as app_db
            app_db.create_all()

        meeting_date_obj = None
        if meeting_date:
            try:
                meeting_date_obj = datetime.strptime(meeting_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        record = MeetingMinutes(
            title=title,
            content=content,
            formatted=formatted,
            summary=parsed.get("summary", "")[:500],
            participants=participants,
            meeting_date=meeting_date_obj,
            topics_count=len(parsed.get("topics", [])),
            decisions_count=len(parsed.get("decisions", [])),
            action_items_count=len(parsed.get("action_items", [])),
            author_id=author_id,
        )
        db.session.add(record)
        db.session.commit()

        return {
            "meeting_id": record.id,
            "title": title,
            "summary": parsed.get("summary", ""),
            "topics": len(parsed.get("topics", [])),
            "decisions": len(parsed.get("decisions", [])),
            "action_items": len(parsed.get("action_items", [])),
        }
    except Exception as e:
        raise RuntimeError(f"保存会议纪要失败: {e}")
    finally:
        _cleanup_context(ctx)


def _list_minutes(keyword: str = "", limit: int = 20) -> list:
    """查询会议纪要列表。"""
    ctx = _ensure_app_context()
    try:
        db = _get_db()
        MeetingMinutes = _get_meeting_minutes_model()

        query = MeetingMinutes.query
        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(
                db.or_(
                    MeetingMinutes.title.like(kw),
                    MeetingMinutes.summary.like(kw),
                    MeetingMinutes.content.like(kw),
                )
            )
        records = query.order_by(MeetingMinutes.created_at.desc()).limit(min(limit, 100)).all()

        result = []
        for r in records:
            result.append({
                "id": r.id,
                "title": r.title,
                "summary": r.summary,
                "participants": r.participants,
                "meeting_date": str(r.meeting_date) if r.meeting_date else "",
                "topics": r.topics_count or 0,
                "action_items": r.action_items_count or 0,
                "created_at": str(r.created_at) if r.created_at else "",
            })
        return result
    finally:
        _cleanup_context(ctx)


def _get_minutes(meeting_id: int) -> dict:
    """获取单条会议纪要详情。"""
    ctx = _ensure_app_context()
    try:
        db = _get_db()
        MeetingMinutes = _get_meeting_minutes_model()

        record = MeetingMinutes.query.get(meeting_id)
        if not record:
            return {"error": f"未找到 ID 为 {meeting_id} 的会议纪要"}

        return {
            "id": record.id,
            "title": record.title,
            "content": record.content,
            "formatted": record.formatted,
            "summary": record.summary,
            "participants": record.participants,
            "meeting_date": str(record.meeting_date) if record.meeting_date else "",
            "topics": record.topics_count or 0,
            "decisions": record.decisions_count or 0,
            "action_items": record.action_items_count or 0,
            "created_at": str(record.created_at) if record.created_at else "",
        }
    finally:
        _cleanup_context(ctx)


# ── 入口函数 ──────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """会议纪要管理。

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
    title = params.get("title") or kwargs.get("title", "")
    content = params.get("content") or kwargs.get("content", "")
    meeting_date = params.get("meeting_date") or kwargs.get("meeting_date", "")
    participants = params.get("participants") or kwargs.get("participants", "")
    meeting_id = params.get("meeting_id") or kwargs.get("meeting_id", 0)
    keyword = params.get("keyword") or kwargs.get("keyword", "")
    limit = params.get("limit") or kwargs.get("limit", 20)

    # ── list: 查询列表 ───────────────────────────────────────────────
    if action == "list":
        try:
            records = _list_minutes(keyword=keyword, limit=int(limit))
            if not records:
                return json.dumps({
                    "success": True,
                    "records": [],
                    "message": "暂无会议纪要",
                }, ensure_ascii=False)
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
            meeting_id = int(meeting_id)
        except (ValueError, TypeError):
            return json.dumps({
                "success": False,
                "error": "meeting_id 必须是整数",
            }, ensure_ascii=False)
        try:
            record = _get_minutes(meeting_id)
            if "error" in record:
                return json.dumps({
                    "success": False,
                    "error": record["error"],
                }, ensure_ascii=False)
            return json.dumps({
                "success": True,
                "record": record,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"查询失败: {e}",
            }, ensure_ascii=False)

    # ── generate: 生成纪要 ───────────────────────────────────────────
    if not content:
        return json.dumps({
            "success": False,
            "error": "缺少必需参数 content（会议内容）",
        }, ensure_ascii=False)

    if not meeting_date:
        meeting_date = datetime.now().strftime("%Y-%m-%d")

    if not title:
        # 从内容中自动提取标题
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and len(line) > 3:
                title = line[:60]
                break
        if not title:
            title = f"会议纪要 {meeting_date}"

    try:
        # 解析内容
        parsed = _parse_meeting_content(content)

        # 格式化纪要
        formatted = _format_minutes(parsed, title, meeting_date, participants)

        # 保存到数据库
        saved = _save_to_db(title, content, meeting_date, participants, parsed, formatted)

        # 创建待办事项
        try:
            created_todos = _generate_action(parsed, title, meeting_date)
        except Exception as e:
            created_todos = []
            saved["todo_warning"] = str(e)

        result = {
            "success": True,
            "meeting_id": saved["meeting_id"],
            "title": saved["title"],
            "summary": saved["summary"],
            "topics": saved["topics"],
            "decisions": saved["decisions"],
            "action_items": saved["action_items"],
            "todos_created": len(created_todos),
            "formatted": formatted,
        }
        if created_todos:
            result["todos"] = created_todos

        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"生成会议纪要失败: {e}",
        }, ensure_ascii=False)
