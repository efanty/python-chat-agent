"""PDF skill — merge, split, rotate, watermark, create PDFs."""

import os
import json
from pathlib import Path
from io import BytesIO


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Actions:
      merge    — merge multiple PDFs into one
      split    — split PDF into separate pages
      rotate   — rotate PDF pages
      extract_table — extract tables from PDF (requires pdfplumber)
      create   — create a simple PDF from text content (requires reportlab)
    """
    action = kwargs.get("action", action) or "merge"

    if action == "merge":
        return _merge_pdfs(kwargs)
    elif action == "split":
        return _split_pdf(kwargs)
    elif action == "rotate":
        return _rotate_pdf(kwargs)
    elif action == "watermark":
        return _add_watermark(kwargs)
    elif action == "create":
        return _create_pdf(kwargs)
    elif action == "extract_table":
        return _extract_tables(kwargs)
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


def _merge_pdfs(data: dict) -> str:
    files = data.get("files", data.get("file_paths", []))
    output = data.get("output", "merged.pdf")
    sandbox_dir = data.get("sandbox_dir")
    if not files or not isinstance(files, list):
        return json.dumps({"success": False, "error": "请提供要合并的 PDF 文件列表 (files)"},
                          ensure_ascii=False)
    try:
        from pypdf import PdfWriter, PdfReader
        writer = PdfWriter()
        for f in files:
            path = _resolve_path(f, sandbox_dir)
            if not path.exists():
                return json.dumps({"success": False, "error": f"文件不存在: {f}"},
                                  ensure_ascii=False)
            reader = PdfReader(str(path))
            for page in reader.pages:
                writer.add_page(page)
        out_path = _resolve_path(output, sandbox_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(out_path), "wb") as f:
            writer.write(f)
        return json.dumps({"success": True, "output": str(out_path), "pages": len(writer.pages)},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"合并失败: {e}"},
                          ensure_ascii=False)


def _split_pdf(data: dict) -> str:
    file_path = data.get("file_path", "")
    output_dir = data.get("output_dir", ".")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 PDF 文件路径"},
                          ensure_ascii=False)
    try:
        from pypdf import PdfReader, PdfWriter
        path = _resolve_path(file_path, sandbox_dir)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        reader = PdfReader(str(path))
        out_dir = _resolve_path(output_dir, sandbox_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        pages = []
        for i, page in enumerate(reader.pages, 1):
            writer = PdfWriter()
            writer.add_page(page)
            out_file = out_dir / f"{path.stem}_p{i:03d}.pdf"
            with open(str(out_file), "wb") as f:
                writer.write(f)
            pages.append(str(out_file))
        return json.dumps({"success": True, "pages": pages, "total": len(pages)},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"拆分失败: {e}"},
                          ensure_ascii=False)


def _rotate_pdf(data: dict) -> str:
    file_path = data.get("file_path", "")
    angle = int(data.get("angle", 90))
    pages_spec = data.get("pages", "all")
    output = data.get("output", "rotated.pdf")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 PDF 文件路径"},
                          ensure_ascii=False)
    try:
        from pypdf import PdfReader, PdfWriter
        path = _resolve_path(file_path, sandbox_dir)
        reader = PdfReader(str(path))
        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if pages_spec == "all" or str(i + 1) in pages_spec.split(","):
                page.rotate(angle)
            writer.add_page(page)
        out_path = _resolve_path(output, sandbox_dir)
        with open(str(out_path), "wb") as f:
            writer.write(f)
        return json.dumps({"success": True, "output": str(out_path)},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"旋转失败: {e}"},
                          ensure_ascii=False)


def _add_watermark(data: dict) -> str:
    file_path = data.get("file_path", "")
    watermark_path = data.get("watermark", "")
    output = data.get("output", "watermarked.pdf")
    sandbox_dir = data.get("sandbox_dir")
    if not file_path or not watermark_path:
        return json.dumps({"success": False, "error": "请提供 file_path 和 watermark"},
                          ensure_ascii=False)
    try:
        from pypdf import PdfReader, PdfWriter
        path = _resolve_path(file_path, sandbox_dir)
        wm_path = _resolve_path(watermark_path, sandbox_dir)
        reader = PdfReader(str(path))
        watermark = PdfReader(str(wm_path)).pages[0]
        writer = PdfWriter()
        for page in reader.pages:
            page.merge_page(watermark)
            writer.add_page(page)
        out_path = _resolve_path(output, sandbox_dir)
        with open(str(out_path), "wb") as f:
            writer.write(f)
        return json.dumps({"success": True, "output": str(out_path)},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"添加水印失败: {e}"},
                          ensure_ascii=False)


def _extract_tables(data: dict) -> str:
    file_path = data.get("file_path", "")
    pages = data.get("pages", None)
    if not file_path:
        return json.dumps({"success": False, "error": "请提供 PDF 文件路径"},
                          ensure_ascii=False)
    try:
        import pdfplumber
        path = _resolve_path(file_path)
        if not path.exists():
            return json.dumps({"success": False, "error": f"文件不存在: {file_path}"},
                              ensure_ascii=False)
        results = []
        with pdfplumber.open(str(path)) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                if pages and str(i) not in pages.split(","):
                    continue
                tables = page.extract_tables()
                for j, table in enumerate(tables):
                    results.append({"page": i, "table": j + 1, "rows": table or []})
        return json.dumps({"success": True, "tables": results, "total": len(results)},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 pdfplumber: pip install pdfplumber"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"表格提取失败: {e}"},
                          ensure_ascii=False)


def _create_pdf(data: dict) -> str:
    content = data.get("content", data.get("text", ""))
    output = data.get("output", "output.pdf")
    title = data.get("title", "Document")
    sandbox_dir = data.get("sandbox_dir")
    if not content:
        return json.dumps({"success": False, "error": "请提供文本内容"},
                          ensure_ascii=False)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet

        out_path = _resolve_path(output, sandbox_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(str(out_path), pagesize=letter)
        styles = getSampleStyleSheet()
        story = [Paragraph(title, styles['Title']), Spacer(1, 12)]
        for line in content.split("\n"):
            if line.strip():
                story.append(Paragraph(line.strip(), styles['Normal']))
                story.append(Spacer(1, 6))
        doc.build(story)
        return json.dumps({"success": True, "output": str(out_path), "pages": len(doc.page_template) if hasattr(doc, 'page_template') else 1},
                          ensure_ascii=False)
    except ImportError:
        return json.dumps({"success": False, "error": "需要 reportlab: pip install reportlab"},
                          ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"创建 PDF 失败: {e}"},
                          ensure_ascii=False)
