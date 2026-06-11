"""DOCX skill — read, create, edit Word documents."""

import os
import json
from pathlib import Path


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Actions:
      read    — extract text from a .docx file
      create  — create a new Word document
      edit    — edit an existing document (append content)
    """
    action = kwargs.get("action", action) or "read"

    if action == "read":
        return _read_docx(kwargs)
    elif action == "create":
        return _create_docx(kwargs)
    elif action == "edit":
        return _edit_docx(kwargs)
    else:
        return json.dumps({"success": False, "error": f"未知操作: {action}"},
                          ensure_ascii=False)


def _resolve_path(file_path: str, sandbox_dir: str = None) -> Path:
    p = Path(file_path)
    if p.is_absolute():
        return p
    if sandbox_dir:
        return Path(sandbox_dir) / file_path
    return Path(__file__).resolve().parent.parent.parent / file_path


def _read_docx(data: dict) -> str:
    file_path = data.get("file_path", "")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 DOCX 文件路径"},
                          ensure_ascii=False)
    try:
        from docx import Document
        path = _resolve_path(file_path, sandbox_dir)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        doc = Document(str(path))

        # Paragraphs
        paragraphs = []
        for p in doc.paragraphs:
            if p.text.strip():
                paragraphs.append({
                    "style": p.style.name if p.style else "Normal",
                    "text": p.text.strip(),
                })

        # Tables
        tables = []
        for table in doc.tables:
            rows_data = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows_data.append(cells)
            tables.append(rows_data)

        return json.dumps({
            "success": True,
            "file": path.name,
            "paragraphs": paragraphs,
            "tables": tables,
            "para_count": len(paragraphs),
            "table_count": len(tables),
        }, ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-docx: pip install python-docx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"读取失败: {e}"},
                          ensure_ascii=False)


def _create_docx(data: dict) -> str:
    content = data.get("content", "")
    # 兼容 SKILL.md 中定义的多种输出文件名参数
    output = data.get("output") or data.get("filename") or data.get("output_path") or "output.docx"
    title = data.get("title", "Document")
    headings = data.get("headings", [])
    sandbox_dir = data.get("sandbox_dir")
    if not content and not headings:
        return json.dumps({"success": False, "error": "请提供文本内容 (content)"},
                          ensure_ascii=False)
    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Title
        if title:
            p = doc.add_heading(title, level=0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Structured content from headings list
        if headings:
            for section in headings:
                h = section.get("heading", "")
                body = section.get("body", "")
                if h:
                    doc.add_heading(h, level=1)
                if body:
                    for line in body.split("\n"):
                        if line.strip():
                            doc.add_paragraph(line.strip())

        # Plain content
        if content:
            doc.add_paragraph(content)

        out_path = _resolve_path(output, sandbox_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
        return json.dumps({"success": True, "output": str(out_path)},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-docx: pip install python-docx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"创建失败: {e}"},
                          ensure_ascii=False)


def _edit_docx(data: dict) -> str:
    file_path = data.get("file_path", "")
    output = data.get("output", "edited.docx")
    content = data.get("content", "")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 DOCX 文件路径"},
                          ensure_ascii=False)
    if not content:
        return json.dumps({"success": False, "error": "请提供要添加的内容"},
                          ensure_ascii=False)
    try:
        from docx import Document
        path = _resolve_path(file_path, sandbox_dir)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        doc = Document(str(path))
        for line in content.split("\n"):
            if line.strip():
                doc.add_paragraph(line.strip())
        out_path = _resolve_path(output, sandbox_dir)
        doc.save(str(out_path))
        return json.dumps({"success": True, "output": str(out_path)},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-docx: pip install python-docx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"编辑失败: {e}"},
                          ensure_ascii=False)
