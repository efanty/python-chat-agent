import os, threading, time, uuid, tempfile, urllib.request
from pathlib import Path
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, Response
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.models.settings import Setting
from app.models.memory import UserMemory
from app.extensions.init_sqlalchemy import db
from app.utils.settings import get_setting_int as _get_setting_int, clear_settings_cache, coerce_setting_value
from app.logger import log_admin, log_error
from app.extensions.init_loginmanager import admin_required
from app.utils.plugin_utils import require_plugin
from app.extensions.init_csrf import csrf_protected
from app.utils.upgrade import (get_current_version, get_backup_list, online_upgrade,
    run_offline_upgrade, get_logs, clear_logs, rollback, get_last_upgrade_backup,
    check_update, restore_backup, run_db_migrate, _log, clean_bak_files,
    db_backup, db_restore, get_version_from_zip, _compare_versions,
    store_pending_upgrade, pop_pending_upgrade, _do_upgrade, DOWNLOAD_DIR, create_backup)
from app.utils.time_utils import clear_tz_cache


# ============ Site Settings / Memory Management ============

@bp.route("/settings", methods=["GET", "POST"])
@admin_required
@require_plugin(blueprint_name)
def site_settings():
    if request.method == "POST":
        # Checkbox must be set to false when unchecked (browser omits them)
        for key in ("maintenance_mode", "registration_enabled", "email_verification_required",
                     "security_enabled", "security_middleware_enabled", "security_alert_low_send_email"):
            if key not in request.form:
                Setting.set(key, "false")
                current_app.config[key] = False
        for key, value in request.form.items():
            if key not in ("csrf_token",):
                Setting.set(key, value)
                current_app.config[key] = coerce_setting_value(key, value)
        # 时区更改立即生效
        if "app_timezone" in request.form:
            clear_tz_cache()
        clear_settings_cache()
        log_admin("网站设置已更新 — keys=%s", list(request.form.keys()))
        flash("设置已更新。", "success")
        return redirect(url_for("admin.site_settings"))

    settings = Setting.get_all_dict()
    return render_template("admin/settings.html", settings=settings)


# ============ System Upgrade ============

@bp.route("/settings/upgrade")
@admin_required
@require_plugin(blueprint_name)
def upgrade():
    """System upgrade page (online + offline)."""
    return render_template(
        "admin/upgrade.html",
        current_version=get_current_version(),
        backups=get_backup_list(),
    )


@bp.route("/settings/upgrade/online", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_online():
    """Start online upgrade with version check.
    First request: download ZIP, compare version.
    If new version is higher → auto-upgrade.
    If not → return needs_confirmation with upgrade_token.
    Second request (force=1 + upgrade_token): proceed with stored ZIP.
    """

    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "请提供下载地址"})

    force = data.get("force", False)
    token = data.get("upgrade_token", "")

    if force and token:
        # User confirmed — use previously downloaded ZIP
        zip_path = pop_pending_upgrade(token)
        if not zip_path or not os.path.exists(zip_path):
            return jsonify({"ok": False, "error": "升级会话已过期，请重新下载"})
        clear_logs()
        t = threading.Thread(target=_do_upgrade, args=(zip_path,), daemon=True)
        t.start()
        log_admin("在线升级已启动（强制） url=%s", url)
        return jsonify({"ok": True})

    # First request: download ZIP
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"upgrade_{uuid.uuid4().hex[:8]}.zip"
    zip_path = DOWNLOAD_DIR / zip_name

    try:
        urllib.request.urlretrieve(url, str(zip_path))
    except Exception as e:
        return jsonify({"ok": False, "error": f"下载失败: {e}"})

    # 版本对比
    current_ver = get_current_version()
    new_ver = get_version_from_zip(str(zip_path))

    if new_ver and not _compare_versions(new_ver, current_ver):
        token = store_pending_upgrade(str(zip_path))
        log_admin("版本未升级，等待用户确认 — current=%s, new=%s", current_ver, new_ver)
        return jsonify({
            "ok": False,
            "needs_confirmation": True,
            "upgrade_token": token,
            "current_version": current_ver,
            "new_version": new_ver,
        })

    # 版本符合，直接升级
    clear_logs()
    t = threading.Thread(target=_do_upgrade, args=(str(zip_path),), daemon=True)
    t.start()
    log_admin("在线升级已启动 url=%s", url)
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/offline", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_offline():
    """Start offline upgrade (upload ZIP -> backup -> extract -> pip -> migrate)."""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "请选择 ZIP 文件"})
    if not file.filename.lower().endswith(".zip"):
        return jsonify({"ok": False, "error": "仅支持 .zip 格式"})

    # 文件大小校验（从数据库读取上限）
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    max_mb = _get_setting_int("max_upload_size_mb", 16)
    if size > max_mb * 1024 * 1024:
        return jsonify({
            "ok": False,
            "error": f"文件过大（{size / 1024 / 1024:.1f}MB），超过限制 {max_mb}MB"
        })

    # Save to temp file before request ends (FileStream closes after return)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    file.save(tmp.name)
    tmp.close()

    # 版本对比：仅在新版本更高时自动升级，否则等待用户确认
    current_ver = get_current_version()
    new_ver = get_version_from_zip(tmp.name)
    force = request.form.get("force", "0") in ("1", "true")

    if new_ver and not _compare_versions(new_ver, current_ver) and not force:
        log_admin("版本未升级，等待用户确认 — current=%s, new=%s", current_ver, new_ver)
        tmp.close()
        return jsonify({
            "ok": False,
            "needs_confirmation": True,
            "current_version": current_ver,
            "new_version": new_ver,
        })

    clear_logs()
    t = threading.Thread(target=run_offline_upgrade, args=(tmp.name,), daemon=True)
    t.start()
    log_admin("离线升级已启动 file=%s", file.filename)
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/logs")
@admin_required
@require_plugin(blueprint_name)
def upgrade_logs():
    """Poll upgrade logs."""
    since = request.args.get("since", 0, type=int)
    lines = get_logs(since)
    return jsonify({"lines": lines, "next": since + len(lines), "done": False})


@bp.route("/settings/upgrade/clear-logs", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_clear_logs():
    """Clear upgrade log buffer."""
    clear_logs()
    return jsonify({"ok": True})

@bp.route("/settings/upgrade/backup-list")
@admin_required
@require_plugin(blueprint_name)
def upgrade_backup_list():
    """Return backup list as JSON for in-place table refresh."""
    return jsonify(get_backup_list())


@bp.route("/settings/upgrade/rollback", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_rollback():
    """One-click rollback to pre-upgrade state."""
    clear_logs()
    t = threading.Thread(target=rollback, daemon=True)
    t.start()
    log_admin("一键回滚已启动")
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/status")
@admin_required
@require_plugin(blueprint_name)
def upgrade_status():
    """Return upgrade/rollback status (backup path, version)."""
    backup = get_last_upgrade_backup()
    return jsonify({
        "last_backup": backup,
        "can_rollback": bool(backup and Path(backup).exists()),
        "current_version": get_current_version(),
    })


@bp.route("/settings/upgrade/restore", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_restore():
    """Restore project from a backup ZIP (runs in background thread)."""

    data = request.get_json() or {}
    backup_path = data.get("path", "").strip()
    if not backup_path:
        return jsonify({"ok": False, "error": "未指定备份文件"})

    clear_logs()

    def _do_restore():
        ok = restore_backup(backup_path)
        if ok:
            run_db_migrate()
            _log("=" * 50)
            _log("恢复完成，请重启应用使更改生效")
            _log("=" * 50)

    t = threading.Thread(target=_do_restore, daemon=True)
    t.start()
    log_admin("备份恢复已启动 path=%s", backup_path)
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/check-update", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_check_update():
    """Check remote version against current version."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "请提供版本检查地址"})
    result = check_update(url)
    return jsonify(result)


@bp.route("/settings/upgrade/logs/sse")
@admin_required
@require_plugin(blueprint_name)
def upgrade_logs_sse():
    """SSE endpoint for real-time upgrade logs."""

    def generate():
        since = 0
        yield "retry: 1000\n\n"
        while True:
            lines = get_logs(since)
            if lines:
                for line in lines:
                    yield f"data: {line}\n\n"
                since += len(lines)
            else:
                yield ": heartbeat\n\n"
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/settings/upgrade/clean-bak", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_clean_bak():
    """Remove .bak files left from upgrades."""
    clear_logs()
    t = threading.Thread(target=clean_bak_files, daemon=True)
    t.start()
    log_admin("清理 .bak 文件已启动")
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/db-backup", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_db_backup():
    """Backup database file (runs in background)."""
    clear_logs()
    t = threading.Thread(target=db_backup, daemon=True)
    t.start()
    log_admin("数据库备份已启动")
    return jsonify({"ok": True})




@bp.route("/settings/upgrade/system-backup", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_system_backup():
    """Backup entire project (runs in background)."""
    clear_logs()
    t = threading.Thread(target=create_backup, daemon=True)
    t.start()
    log_admin("系统备份已启动")
    return jsonify({"ok": True})


@bp.route("/settings/upgrade/db-restore", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def upgrade_db_restore():
    """Restore database from a backup file (runs in background)."""
    data = request.get_json() or {}
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"ok": False, "error": "未指定备份文件"})
    clear_logs()
    t = threading.Thread(target=db_restore, args=(path,), daemon=True)
    t.start()
    log_admin("数据库恢复已启动 path=%s", path)
    return jsonify({"ok": True})


@bp.route("/memories")
@admin_required
@require_plugin(blueprint_name)
def memories():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", _get_setting_int("admin_per_page", 20), type=int)
    pagination = UserMemory.query.order_by(UserMemory.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    memories = pagination.items
    return render_template("admin/memories.html", memories=memories, pagination=pagination)


@bp.route("/memories/<int:mem_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def memory_delete(mem_id):
    log_admin("记忆已删除 — mem_id=%d", mem_id)
    mem = UserMemory.query.get_or_404(mem_id)
    db.session.delete(mem)
    db.session.commit()
    flash("记忆已删除。", "success")
    return redirect(url_for("admin.memories"))