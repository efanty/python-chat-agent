import os
import time
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.models.llm_model import LLMModel
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int
import requests as _requests

# ============ LLM Model Management ============

@bp.route("/models")
@admin_required
@require_plugin(blueprint_name)
def models():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    pagination = LLMModel.query.order_by(LLMModel.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    models = pagination.items
    return render_template("admin/models.html", models=models, pagination=pagination)


@bp.route("/models/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def model_add():
    data = request.form
    model = LLMModel(
        name=data.get("name"),
        provider=data.get("provider"),
        model_type=data.get("model_type"),
        model_id=data.get("model_id"),
        api_key=data.get("api_key"),
        api_base=data.get("api_base"),
        is_active=data.get("is_active") == "true",
        allowed_roles=data.get("allowed_roles", "all"),
        max_tokens=data.get("max_tokens", 4096, type=int),
        supports_vision=data.get("supports_vision", "false") == "true",
        supports_files=data.get("supports_files", "false") == "true",
        description=data.get("description"),
        input_price=data.get("input_price", 0.0, type=float),
        output_price=data.get("output_price", 0.0, type=float),
    )
    db.session.add(model)
    db.session.commit()
    log_admin("LLM模型已添加 — name=%s, provider=%s", model.name, model.provider)
    flash("LLM模型添加成功。", "success")
    return redirect(url_for("admin.models"))


@bp.route("/models/<int:model_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def model_edit(model_id):
    model = LLMModel.query.get_or_404(model_id)
    data = request.form

    model.name = data.get("name", model.name)
    model.provider = data.get("provider", model.provider)
    model.model_type = data.get("model_type", model.model_type)
    model.model_id = data.get("model_id", model.model_id)
    model.api_key = data.get("api_key", model.api_key)
    model.api_base = data.get("api_base", model.api_base)
    model.is_active = data.get("is_active") == "true"
    model.allowed_roles = data.get("allowed_roles", model.allowed_roles)
    model.max_tokens = data.get("max_tokens", model.max_tokens, type=int)
    model.supports_vision = data.get("supports_vision", "false") == "true"
    model.supports_files = data.get("supports_files", "false") == "true"
    model.description = data.get("description", model.description)
    model.input_price = data.get("input_price", model.input_price, type=float)
    model.output_price = data.get("output_price", model.output_price, type=float)

    db.session.commit()
    log_admin("LLM模型已编辑 — model_id=%d, name=%s", model.id, model.name)
    flash("LLM模型更新成功。", "success")
    return redirect(url_for("admin.models"))


@bp.route("/models/<int:model_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def model_delete(model_id):
    log_admin("LLM模型已删除 — model_id=%d", model_id)
    model = LLMModel.query.get_or_404(model_id)
    db.session.delete(model)
    db.session.commit()
    flash("LLM模型已删除。", "success")
    return redirect(url_for("admin.models"))


def _balance_request(url: str, api_key: str, timeout: int = 15) -> dict:
    """Make a GET request with Bearer auth and return parsed JSON.
    Uses requests library with automatic SSL handling."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "DeepAgent-BalanceCheck/1.0",
        "Accept": "application/json",
    }
    resp = _requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


@bp.route("/models/<int:model_id>/balance")
@admin_required
@require_plugin(blueprint_name)
def model_balance(model_id):
    """查询 LLM 模型对应 API 账户余额。

    支持的提供商:
      - DeepSeek:  GET https://api.deepseek.com/user/balance
      - 智谱 GLM:   GET https://open.bigmodel.cn/api/paas/v4/api/account/balance
      - OpenAI:     GET https://api.openai.com/dashboard/billing/subscription
      - OpenAI 兼容: 尝试 {api_base}/dashboard/billing/subscription
    """
    model = LLMModel.query.get_or_404(model_id)
    api_key = model.api_key or ""
    api_base = (model.api_base or "").rstrip("/")
    provider = (model.provider or "").lower()

    if not api_key:
        return jsonify({"success": False, "error": "未配置 API Key"})

    result = {"provider": model.provider or "Unknown", "model_name": model.name}

    try:
        start = time.time()

        # ── DeepSeek ───────────────────────────────────────────────
        if provider == "deepseek" or "deepseek" in api_base.lower():
            data = _balance_request("https://api.deepseek.com/user/balance", api_key)
            latency = round((time.time() - start) * 1000)

            info = {"is_available": data.get("is_available")}
            if data.get("balance_infos"):
                info.update(data["balance_infos"][0])
            else:
                info["balance"] = data.get("balance", "0")
                info["currency"] = data.get("currency", "CNY")

            result.update({"success": True, "latency_ms": latency, "balance_info": info})

        # ── 智谱 GLM ──────────────────────────────────────────────
        elif any(kw in provider for kw in ("zhipu", "glm", "chatglm")) or \
             any(kw in api_base.lower() for kw in ("bigmodel", "zhipuai")):
            url = "https://bigmodel.cn/api/biz/account/query-customer-account-report"
            try:
                data = _balance_request(url, api_key)
            except _requests.exceptions.HTTPError as auth_err:
                if auth_err.response.status_code in (401, 403):
                    # Fallback: API Key in URL query param
                    resp = _requests.get(
                        f"{url}?Authorization={api_key}",
                        headers={"User-Agent": "DeepAgent-BalanceCheck/1.0", "Accept": "application/json"},
                        timeout=15,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    raise

            latency = round((time.time() - start) * 1000)

            if not data.get("success") and data.get("code", 0) != 200:
                err_msg = data.get("msg") or str(data.get("code", "未知错误"))
                return jsonify({"success": False, "error": f"智谱API错误: {err_msg}"})

            d = data.get("data", {})
            result.update({
                "success": True,
                "latency_ms": latency,
                "balance_info": {
                    "balance": d.get("balance"),
                    "available_balance": d.get("availableBalance"),
                    "recharge_amount": d.get("rechargeAmount"),
                    "give_amount": d.get("giveAmount"),
                    "total_spend": d.get("totalSpendAmount"),
                    "today_spend": d.get("todaySpendAmount"),
                    "frozen_balance": d.get("frozenBalance"),
                    "credit_status": d.get("creditStatus"),
                },
            })

        # ── 阿里云 (Alibaba Cloud BSS) ──────────────────────────────
        elif provider == "aliyun":
            try:
                from alibabacloud_bssopenapi20171214.client import Client as BssClient
                from alibabacloud_credentials.client import Client as CredClient
                from alibabacloud_tea_openapi import models as open_api_models
                from alibabacloud_credentials.models import Config as CredConfig
                from alibabacloud_tea_util import models as util_models

                ak_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
                ak_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
                if not ak_id or not ak_secret:
                    return jsonify({"success": False, "error": "未配置阿里云AccessKey, 请在.env中设置ALIBABA_CLOUD_ACCESS_KEY_ID和ALIBABA_CLOUD_ACCESS_KEY_SECRET"})

                cred_cfg = CredConfig(type="access_key", access_key_id=ak_id, access_key_secret=ak_secret)
                cred_client = CredClient(cred_cfg)
                config = open_api_models.Config(credential=cred_client)
                config.endpoint = "business.aliyuncs.com"
                client = BssClient(config)
                runtime = util_models.RuntimeOptions()
                resp = client.query_account_balance_with_options(runtime)
                latency = round((time.time() - start) * 1000)

                body = resp.body if hasattr(resp, 'body') else resp
                data_attr = getattr(body, 'data', None)
                avail = getattr(data_attr, 'available_amount', '0') if data_attr else '0'
                credit = getattr(data_attr, 'credit_status', '') if data_attr else ''
                result.update({
                    "success": True,
                    "latency_ms": latency,
                    "balance_info": {
                        "total_balance": avail,
                        "currency": "CNY",
                        "available_amount": avail,
                        "credit_status": credit,
                    },
                })
            except ImportError:
                return jsonify({"success": False, "error": "阿里云SDK未安装, 请执行: pip install alibabacloud_bssopenapi20171214"})
            except Exception as e:
                err_msg = str(e)
                if hasattr(e, 'message') and e.message:
                    err_msg = e.message
                return jsonify({"success": False, "error": f"阿里云API错误: {err_msg}"})

        # ── OpenAI / 兼容 ──────────────────────────────────────────
        elif provider == "openai" or (api_base and "/v1" in api_base):
            billing_url = "https://api.openai.com/dashboard/billing/subscription"
            if api_base and "openai.com" not in api_base:
                billing_url = f"{api_base.rstrip('/')}/dashboard/billing/subscription"
            data = _balance_request(billing_url, api_key)
            latency = round((time.time() - start) * 1000)

            hard_limit = data.get("hard_limit_usd", 0) or 0
            total_usage = data.get("total_usage_usd", 0) or 0
            remaining = (data.get("remaining_usd") or 0) or (hard_limit - total_usage)

            result.update({
                "success": True,
                "latency_ms": latency,
                "balance_info": {
                    "hard_limit_usd": round(hard_limit, 4),
                    "total_usage_usd": round(total_usage, 4),
                    "remaining_usd": round(remaining, 4),
                },
            })

        else:
            return jsonify({"success": False, "error": f"不支持的提供商: {provider}"})

        return jsonify(result)

    except _requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = e.response.text[:200] if e.response is not None else ""
        return jsonify({"success": False, "error": f"HTTP {status}: {body}"})
    except _requests.exceptions.ConnectionError as e:
        return jsonify({"success": False, "error": f"连接失败: {e}"})
    except _requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "请求超时"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

