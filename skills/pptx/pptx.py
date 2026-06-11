"""PPTX skill — read, create, edit PowerPoint presentations."""

import os
import json
from pathlib import Path


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Actions:
      read        — extract text from a .pptx file
      create      — create a new presentation with slides
      edit        — edit an existing presentation
    """
    action = kwargs.get("action", action) or "read"
    file_path = kwargs.get("file_path", "") or expression

    if action == "read":
        return _read_pptx(file_path or kwargs.get("file_path", ""), sandbox_dir=kwargs.get("sandbox_dir"))
    elif action == "create":
        return _create_pptx(kwargs)
    elif action == "edit":
        return _edit_pptx(kwargs)
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


def _read_pptx(file_path: str, sandbox_dir: str = None) -> str:
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 PPTX 文件路径"},
                          ensure_ascii=False)
    try:
        from pptx import Presentation
        path = _resolve_path(file_path, sandbox_dir)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        prs = Presentation(str(path))
        slides_data = []
        for i, slide in enumerate(prs.slides, 1):
            texts = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = para.text.strip()
                        if t:
                            texts.append(t)
                if shape.has_table:
                    table = shape.table
                    rows_data = []
                    for row in table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        rows_data.append(cells)
                    texts.append("[TABLE] " + json.dumps(rows_data, ensure_ascii=False))
            slides_data.append({"slide": i, "texts": texts})
        return json.dumps({"success": True, "file": path.name, "slides": slides_data,
                           "total": len(slides_data)}, ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-pptx: pip install python-pptx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"读取失败: {e}"},
                          ensure_ascii=False)


def _create_pptx(data: dict) -> str:
    slides = data.get("slides", [])
    # 兼容多种输出文件名参数
    output = data.get("output") or data.get("filename") or data.get("output_path") or "presentation.pptx"
    title = data.get("title", "Presentation")
    sandbox_dir = data.get("sandbox_dir")
    if not slides:
        # Single slide with content
        content = data.get("content", "")
        slides = [{"title": title, "content": content}]
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        for slide_data in slides:
            slide_title = slide_data.get("title", "")
            content = slide_data.get("content", "")
            slide_layout = prs.slide_layouts[1]  # Title and Content
            slide = prs.slides.add_slide(slide_layout)
            if slide_title:
                slide.shapes.title.text = slide_title
            if content:
                body = slide.shapes.placeholders[1]
                tf = body.text_frame
                for line in content.split("\n"):
                    if line.strip():
                        p = tf.add_paragraph()
                        p.text = line.strip()
        out_path = _resolve_path(output, sandbox_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out_path))
        return json.dumps({"success": True, "output": str(out_path), "slides": len(slides)},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-pptx: pip install python-pptx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"创建失败: {e}"},
                          ensure_ascii=False)


def _edit_pptx(data: dict) -> str:
    file_path = data.get("file_path", "")
    output = data.get("output", "edited.pptx")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 PPTX 文件路径"},
                          ensure_ascii=False)
    try:
        from pptx import Presentation
        path = _resolve_path(file_path, sandbox_dir)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        prs = Presentation(str(path))
        # Add a new slide with content
        content = data.get("content", "")
        if content:
            slide_layout = prs.slide_layouts[1]
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.title.text = data.get("title", "New Slide")
            if content:
                body = slide.shapes.placeholders[1]
                tf = body.text_frame
                for line in content.split("\n"):
                    if line.strip():
                        p = tf.add_paragraph()
                        p.text = line.strip()
        out_path = _resolve_path(output, sandbox_dir)
        prs.save(str(out_path))
        return json.dumps({"success": True, "output": str(out_path)},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 python-pptx: pip install python-pptx"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"编辑失败: {e}"},
                          ensure_ascii=False)
