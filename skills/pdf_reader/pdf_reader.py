"""PDF reader skill — extract text from PDF files and return as Markdown."""

import os
import json
from pathlib import Path

from app.utils.settings import get_setting_int
MAX_CHARS = lambda: get_setting_int("pdf_extract_max_chars", 30000)  # max output size to avoid overwhelming context


def run(expression: str = "", action: str = "", file_path: str = "",
        path: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Args:
        expression: file path or JSON with {action, file_path}
        action: "extract" or "read"
        file_path: path to PDF file
        path: alternative parameter name
        sandbox_dir: 沙箱目录（由系统自动传入）
    """
    # Parse from JSON expression
    if expression and expression.strip().startswith("{"):
        try:
            args = json.loads(expression)
            action = args.get("action", action)
            file_path = args.get("file_path", args.get("path", file_path))
        except json.JSONDecodeError:
            # Treat expression as file path
            if not file_path and not action.startswith("{"):
                file_path = expression

    # Resolve from kwargs
    file_path = file_path or path or kwargs.get("file_path", "") or expression
    action = action or "extract"
    sandbox_dir = kwargs.get("sandbox_dir")

    if not file_path or file_path.startswith("{"):
        return json.dumps({
            "success": False,
            "error": "请提供 PDF 文件路径。用法: run(file_path='/path/to/file.pdf')",
        }, ensure_ascii=False)

    # Resolve path（支持沙箱目录）
    pdf_path = Path(file_path)
    if not pdf_path.is_absolute():
        if sandbox_dir:
            pdf_path = Path(sandbox_dir) / file_path
        else:
            # Try relative to project root
            project_root = Path(__file__).resolve().parent.parent.parent
            pdf_path = project_root / file_path
    if not pdf_path.exists():
        return json.dumps({
            "success": False,
            "error": f"文件不存在: {file_path}",
        }, ensure_ascii=False)
    if pdf_path.suffix.lower() != ".pdf":
        return json.dumps({
            "success": False,
            "error": f"不是 PDF 文件: {pdf_path.name}",
        }, ensure_ascii=False)

    try:
        from pypdf import PdfReader
    except ImportError:
        return json.dumps({
            "success": False,
            "error": "需要安装 pypdf 库。请运行: pip install pypdf",
        }, ensure_ascii=False)

    # ── Extract ──────────────────────────────────────────────────────
    try:
        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        lines = [
            f"# PDF: {pdf_path.name}",
            f"**页数**: {total_pages}",
            "",
        ]
        char_count = len("".join(lines))

        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if not text or not text.strip():
                continue
            page_header = f"## 第 {i} 页"
            page_content = text.strip()
            block = f"{page_header}\n\n{page_content}\n\n---\n"
            current_max = MAX_CHARS() if callable(MAX_CHARS) else MAX_CHARS
            if char_count + len(block) > current_max:
                lines.append(f"## 第 {i} 页\n\n*（内容已截断，共 {total_pages} 页）*")
                break
            lines.append(block)
            char_count += len(block)

        result = "\n".join(lines).strip()
        return json.dumps({
            "success": True,
            "file_name": pdf_path.name,
            "total_pages": total_pages,
            "extracted_pages": i,
            "char_count": len(result),
            "content": result,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"PDF 解析失败: {e}",
        }, ensure_ascii=False)


# Action aliases for SkillExecutor
extract = run
read = run
