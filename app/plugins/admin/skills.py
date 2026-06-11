import os
import io
import re
import yaml
import zipfile
import shutil
import tempfile
from pathlib import Path
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.utils.settings import get_setting_int as _get_setting_int
from app.models.skill import Skill
from app.utils.plugin_utils import require_plugin


# ============ Skills Management ============

@bp.route("/skills")
@admin_required
@require_plugin(blueprint_name)
def skills_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", _get_setting_int("admin_per_page", 20), type=int)
    pagination = Skill.query.order_by(Skill.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    skills = pagination.items
    return render_template("admin/skills.html", skills=skills, pagination=pagination)


@bp.route("/skills/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def skill_add():
    data = request.form
    skill = Skill(
        name=data.get("name"),
        description=data.get("description"),
        folder_name=data.get("folder_name"),
        is_active=data.get("is_active") == "true",
    )
    db.session.add(skill)
    db.session.commit()
    log_admin("Skill已添加 — name=%s", skill.name)
    flash("Skill添加成功。", "success")
    return redirect(url_for("admin.skills_list"))


@bp.route("/skills/<int:skill_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def skill_edit(skill_id):
    skill = Skill.query.get_or_404(skill_id)
    data = request.form

    skill.name = data.get("name", skill.name)
    skill.description = data.get("description", skill.description)
    skill.folder_name = data.get("folder_name", skill.folder_name)
    skill.is_active = data.get("is_active") == "true"

    db.session.commit()
    log_admin("Skill已编辑 — skill_id=%d, name=%s", skill.id, skill.name)
    flash("Skill更新成功。", "success")
    return redirect(url_for("admin.skills_list"))


@bp.route("/skills/upload", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def skill_upload():
    """Upload a skill as ZIP archive and install it."""
    file = request.files.get("file")
    if not file or not file.filename:
        flash("请选择 ZIP 文件。", "danger")
        return redirect(url_for("admin.skills_list"))

    if not file.filename.lower().endswith(".zip"):
        flash("仅支持 .zip 格式。", "danger")
        return redirect(url_for("admin.skills_list"))

    # 文件大小校验（从数据库读取上限）
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_mb = _get_setting_int("max_upload_size_mb", 16)
    if size > max_mb * 1024 * 1024:
        flash(f"文件过大（{size / 1024 / 1024:.1f}MB），超过限制 {max_mb}MB", "danger")
        return redirect(url_for("admin.skills_list"))

    # Extract to a temp dir first for validation
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(file) as zf:
                # Security: reject zip bombs / path traversal
                for info in zf.infolist():
                    name = info.filename
                    if ".." in name or name.startswith("/") or name.startswith("\\"):
                        flash("压缩包包含非法路径，已拒绝。", "danger")
                        return redirect(url_for("admin.skills_list"))
                    if info.file_size > 10 * 1024 * 1024:
                        flash("压缩包内文件过大（超过 10MB）。", "danger")
                        return redirect(url_for("admin.skills_list"))

                zf.extractall(tmpdir)

            # Find SKILL.md — must be in top-level folder or root
            tmp_path = Path(tmpdir)
            skill_md_path = tmp_path / "SKILL.md"
            if not skill_md_path.exists():
                # Maybe inside a subfolder
                folders = [d for d in tmp_path.iterdir() if d.is_dir()]
                for folder in folders:
                    candidate = folder / "SKILL.md"
                    if candidate.exists():
                        skill_md_path = candidate
                        break
            if not skill_md_path.exists():
                flash("ZIP 中未找到 SKILL.md 文件。", "danger")
                return redirect(url_for("admin.skills_list"))

            # Parse frontmatter
            md_content = skill_md_path.read_text(encoding="utf-8", errors="replace")
            skill_name = skill_md_path.parent.name
            description = ""
            if md_content.startswith("---"):
                parts = md_content.split("---", 2)
                if len(parts) >= 2:
                    try:
                        fm = yaml.safe_load(parts[1]) or {}
                        skill_name = fm.get("name", skill_name)
                        description = fm.get("description", "") or ""
                    except Exception:
                        pass

            folder_name = skill_name.strip().lower().replace(" ", "_").replace("-", "_")
            if not folder_name:
                flash("无法确定文件夹名称。", "danger")
                return redirect(url_for("admin.skills_list"))

            # Check if folder already exists
            skills_dir = Path(current_app.config.get("SKILLS_DIR", "skills"))
            target_dir = skills_dir / folder_name
            if target_dir.exists():
                flash(f"Skills/{folder_name}/ 文件夹已存在。请先删除或重命名。", "danger")
                return redirect(url_for("admin.skills_list"))

            # Copy files to skills/
            src_dir = skill_md_path.parent
            shutil.copytree(str(src_dir), str(target_dir))
            log_admin("Skill ZIP 已解压 — folder=%s", folder_name)

            # Register in database
            existing = Skill.query.filter_by(name=skill_name).first()
            if existing:
                flash(f"Skill「{skill_name}」已存在于数据库。", "danger")
                return redirect(url_for("admin.skills_list"))

            skill = Skill(
                name=skill_name,
                description=description,
                folder_name=folder_name,
            )
            db.session.add(skill)
            db.session.commit()
            log_admin("Skill 已通过 ZIP 安装 — name=%s, folder=%s", skill_name, folder_name)
            flash(f"Skill「{skill_name}」安装成功！", "success")

    except zipfile.BadZipFile:
        flash("无效的 ZIP 文件。", "danger")
    except Exception as e:
        log_error("Skill ZIP 安装失败: %s", str(e))
        flash(f"安装失败: {e}", "danger")

    return redirect(url_for("admin.skills_list"))


@bp.route("/skills/<int:skill_id>/download")
@login_required
@admin_required
@require_plugin(blueprint_name)
def skill_download(skill_id):
    """打包下载 Skill 文件夹为 ZIP。"""
    skill = Skill.query.get_or_404(skill_id)
    if not skill.folder_name:
        flash("该 Skill 没有关联的文件夹。", "danger")
        return redirect(url_for("admin.skills_list"))

    skills_dir = current_app.config.get("SKILLS_DIR", "skills")
    skill_dir = os.path.join(skills_dir, skill.folder_name)

    if not os.path.isdir(skill_dir):
        flash(f"文件夹 skills/{skill.folder_name}/ 不存在。", "danger")
        return redirect(url_for("admin.skills_list"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(skill_dir):
            for fn in files:
                fpath = os.path.join(root, fn)
                arcname = os.path.relpath(fpath, skills_dir)
                zf.write(fpath, arcname)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{skill.folder_name}.zip",
    )


@bp.route("/skills/<int:skill_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def skill_delete(skill_id):
    log_admin("Skill已删除 — skill_id=%d", skill_id)
    skill = Skill.query.get_or_404(skill_id)
    db.session.delete(skill)
    db.session.commit()
    flash("Skill已删除。", "success")
    return redirect(url_for("admin.skills_list"))
