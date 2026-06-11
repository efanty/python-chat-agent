"""
Security management — IP blocklist management for admin panel.

Provides:
- View currently blocked IPs with remaining time
- Unblock specific IPs
- Clear all blocked IPs
"""
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required
from app.extensions.init_loginmanager import admin_required
from app.utils.plugin_utils import require_plugin
from app.logger import log_admin
from .main import bp

blueprint_name = "admin"


@bp.route("/security/blocked-ips")
@login_required
@admin_required
@require_plugin(blueprint_name)
def blocked_ips():
    """Show list of currently blocked IPs."""
    from app.security import get_blocked_ips
    ips = get_blocked_ips()
    return render_template("admin/blocked_ips.html", blocked_ips=ips)


@bp.route("/security/blocked-ips/unblock", methods=["POST"])
@login_required
@admin_required
@require_plugin(blueprint_name)
def unblock_ip():
    """Unblock a specific IP address."""
    from app.security import unblock_ip as _unblock
    ip = request.form.get("ip", "").strip()
    if not ip:
        flash("请提供要解封的 IP 地址。", "danger")
        return redirect(url_for("admin.blocked_ips"))

    _unblock(ip)
    log_admin("管理员手动解封IP — ip=%s", ip)
    flash(f"IP {ip} 已解封。", "success")
    return redirect(url_for("admin.blocked_ips"))


@bp.route("/security/blocked-ips/unblock-all", methods=["POST"])
@login_required
@admin_required
@require_plugin(blueprint_name)
def unblock_all_ips():
    """Clear all blocked IPs."""
    from app.security.defender import _blocked_ips, _blocklist_lock
    with _blocklist_lock:
        count = len(_blocked_ips)
        _blocked_ips.clear()
    log_admin("管理员一键解封所有IP — count=%d", count)
    flash(f"已解封全部 {count} 个 IP。", "success")
    return redirect(url_for("admin.blocked_ips"))


@bp.route("/security/blocked-ips/api")
@login_required
@admin_required
@require_plugin(blueprint_name)
def blocked_ips_api():
    """Return blocked IPs as JSON (for AJAX refresh)."""
    from app.security import get_blocked_ips
    ips = get_blocked_ips()
    return jsonify({"blocked_ips": ips, "count": len(ips)})
