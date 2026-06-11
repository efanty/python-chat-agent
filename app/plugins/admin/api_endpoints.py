from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.models.api_endpoint import APIEndpoint
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int



# ============ API Endpoint Management ============

@bp.route("/api-endpoints")
@admin_required
@require_plugin(blueprint_name)
def api_endpoints():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    pagination = APIEndpoint.query.order_by(APIEndpoint.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    api_endpoints = pagination.items
    return render_template("admin/api_endpoints.html", api_endpoints=api_endpoints, pagination=pagination)


@bp.route("/api-endpoints/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def api_endpoint_add():
    data = request.form
    ep = APIEndpoint(
        name=data.get("name"),
        description=data.get("description"),
        url=data.get("url"),
        method=data.get("method", "GET"),
        headers=data.get("headers"),
        auth_type=data.get("auth_type", "none"),
        auth_value=data.get("auth_value"),
        is_active=data.get("is_active") == "true",
    )
    db.session.add(ep)
    db.session.commit()
    log_admin("API接口已添加 — name=%s", ep.name)
    flash("API接口添加成功。", "success")
    return redirect(url_for("admin.api_endpoints"))


@bp.route("/api-endpoints/<int:ep_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def api_endpoint_edit(ep_id):
    ep = APIEndpoint.query.get_or_404(ep_id)
    data = request.form

    ep.name = data.get("name", ep.name)
    ep.description = data.get("description", ep.description)
    ep.url = data.get("url", ep.url)
    ep.method = data.get("method", ep.method)
    ep.headers = data.get("headers", ep.headers)
    ep.auth_type = data.get("auth_type", ep.auth_type)
    ep.auth_value = data.get("auth_value", ep.auth_value)
    ep.is_active = data.get("is_active") == "true"

    db.session.commit()
    log_admin("API接口已编辑 — ep_id=%d, name=%s", ep.id, ep.name)
    flash("API接口更新成功。", "success")
    return redirect(url_for("admin.api_endpoints"))


@bp.route("/api-endpoints/<int:ep_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def api_endpoint_delete(ep_id):
    log_admin("API接口已删除 — ep_id=%d", ep_id)
    ep = APIEndpoint.query.get_or_404(ep_id)
    db.session.delete(ep)
    db.session.commit()
    flash("API接口已删除。", "success")
    return redirect(url_for("admin.api_endpoints"))

