"""Send email skill — SMTP client using project .env configuration."""

import os
import json
import smtplib
from email.header import Header
from email.utils import getaddresses, formataddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path

# Resolve project root (3 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

# Load .env manually if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

_MIME_MAP = {
    ".pdf": ("application", "pdf"),
    ".png": ("image", "png"), ".jpg": ("image", "jpeg"), ".jpeg": ("image", "jpeg"),
    ".gif": ("image", "gif"), ".webp": ("image", "webp"),
    ".txt": ("text", "plain"), ".csv": ("text", "csv"),
    ".html": ("text", "html"), ".htm": ("text", "html"),
    ".doc": ("application", "msword"),
    ".docx": ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xls": ("application", "vnd.ms-excel"),
    ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".zip": ("application", "zip"),
    ".json": ("application", "json"),
}


def _get_config():
    """Read mail config from DB settings first, then .env as fallback."""
    try:
        from app.utils.settings import get_setting
        gs = lambda k, d: get_setting(k, os.getenv(k.upper(), d))
    except ImportError:
        gs = lambda k, d: os.getenv(k.upper(), d)
    return {
        "smtp_server": gs("mail_server", "localhost"),
        "smtp_port": int(gs("mail_port", "587")),
        "username": gs("mail_username", ""),
        "password": gs("mail_password", ""),
        "default_sender": gs("mail_default_sender", ""),
        "use_tls": os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes"),
        "use_ssl": os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes"),
    }


def run(expression: str = "", to: str = "", subject: str = "", body: str = "",
        content_type: str = "plain", cc: str = "", attachments: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Args are passed as keyword arguments. They can also come as a JSON string
    in `expression` (for compatibility with the generic skill call format).
    """
    # Parse from expression if it looks like JSON
    if expression and expression.strip().startswith("{"):
        try:
            args = json.loads(expression)
            to = args.get("to", args.get("to_emails", args.get("receiver",
                  args.get("recipients", args.get("recipient", args.get("to_email", to))))))
            subject = args.get("subject", subject)
            body = args.get("body", args.get("content", args.get("html_body", args.get("html", body))))
            content_type = args.get("content_type", content_type)
            cc = args.get("cc", args.get("cc_emails", cc))
            attachments = args.get("attachments", attachments)
        except json.JSONDecodeError:
            pass

    # Also accept direct keyword args (how SkillExecutor calls)
    to = to or kwargs.get("to_emails", "") or kwargs.get("receiver", "") or kwargs.get("recipients", "") or kwargs.get("recipient", "")
    body = body or kwargs.get("content", "") or kwargs.get("html_body", "") or kwargs.get("html", "")

    if not to or not subject or not body:
        return json.dumps(
            {"success": False, "error": "缺少必需参数：to（收件人）, subject（主题）, body（正文）"},
            ensure_ascii=False,
        )

    cfg = _get_config()
    if not cfg["username"] or not cfg["password"]:
        return json.dumps(
            {"success": False,
             "error": "系统未配置邮件服务器。请在 .env 中设置 MAIL_USERNAME 和 MAIL_PASSWORD"},
            ensure_ascii=False,
        )

    # Parse addresses: separate display names from bare emails
    addr_pairs = getaddresses([to])
    bare_to = [addr for _, addr in addr_pairs if addr and "@" in addr]
    to_header = ", ".join(
        formataddr((name, addr)) for name, addr in addr_pairs if addr and "@" in addr
    )

    cc_pairs = getaddresses([cc]) if cc else []
    bare_cc = [addr for _, addr in cc_pairs if addr and "@" in addr]
    cc_header = ", ".join(
        formataddr((name, addr)) for name, addr in cc_pairs if addr and "@" in addr
    ) if bare_cc else None

    att_list = [p.strip() for p in attachments.split(",") if p.strip()] if attachments else None

    if not bare_to:
        return json.dumps(
            {"success": False, "error": "未解析到有效的收件人地址"},
            ensure_ascii=False,
        )

    try:
        from_addr = cfg["default_sender"] or cfg["username"]
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"] = to_header
        # Encode Subject header for Chinese/non-ASCII support
        msg["Subject"] = Header(subject, "utf-8")
        if cc_header:
            msg["Cc"] = cc_header

        msg.attach(MIMEText(body, "html" if content_type == "html" else "plain", "utf-8"))

        if att_list:
            _uid = kwargs.get("_user_id", "0")
            for fp in att_list:
                p = Path(fp)

                # Step 1: Strip /chat/sandbox/ URL prefix used by gen_image etc.
                fp_stripped = fp
                if fp_stripped.startswith("/chat/sandbox/"):
                    fp_stripped = fp_stripped[len("/chat/sandbox/"):]
                    p = Path(fp_stripped)

                # Step 2: If still a URL path (starts with /), strip leading /
                if fp_stripped.startswith("/"):
                    fp_stripped = fp_stripped.lstrip("/")
                    p = Path(fp_stripped)

                # Step 3: Resolve non-absolute paths against known directories
                if not p.is_absolute():
                    # Check if path already contains user_id prefix (e.g. "1/gen_xxx.png")
                    # If so, don't double-prefix with _uid
                    parts = p.parts
                    if len(parts) >= 2 and parts[0].isdigit():
                        # Path already has user_id prefix, try sandbox/<path> directly
                        candidates = [
                            _PROJECT_ROOT / "sandbox" / p,
                            _PROJECT_ROOT / "uploads" / p,
                            Path.cwd() / p,
                        ]
                    else:
                        candidates = [
                            _PROJECT_ROOT / "sandbox" / str(_uid) / p,
                            _PROJECT_ROOT / "uploads" / p,
                            Path.cwd() / p,
                        ]
                    for cand in candidates:
                        if cand.is_file():
                            p = cand
                            break

                # Step 4: Try sandbox root as last resort (no user_id prefix)
                if not p.is_file() and not p.is_absolute():
                    cand_sandbox_root = _PROJECT_ROOT / "sandbox" / p
                    if cand_sandbox_root.is_file():
                        p = cand_sandbox_root

                if not p.is_file():
                    return json.dumps({"success": False, "error": f"附件不存在: {fp}"}, ensure_ascii=False)
                if p.stat().st_size > 10 * 1024 * 1024:
                    return json.dumps({"success": False, "error": f"附件过大(>10MB): {p.name}"}, ensure_ascii=False)
                mt, st = _MIME_MAP.get(p.suffix.lower(), ("application", "octet-stream"))
                with open(p, "rb") as f:
                    part = MIMEApplication(f.read(), subtype=st)
                # RFC 2231 encoding for non-ASCII filenames (Chinese, etc.)
                part.add_header("Content-Disposition", "attachment",
                                filename=("utf-8", "", p.name))
                msg.attach(part)

        all_rcpt = bare_to + bare_cc
        if cfg["use_ssl"] or cfg["smtp_port"] == 465:
            server = smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"])
        else:
            server = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
            if cfg["use_tls"]:
                server.starttls()

        server.login(cfg["username"], cfg["password"])
        # Encode to UTF-8 bytes before sendmail — smtplib defaults to ASCII
        # and will crash on Chinese/full-width characters otherwise.
        server.sendmail(from_addr, all_rcpt, msg.as_string().encode("utf-8"))
        server.quit()

        return json.dumps(
            {"success": True, "message": f"邮件已发送至 {', '.join(bare_to)}"},
            ensure_ascii=False,
        )
    except smtplib.SMTPAuthenticationError:
        return json.dumps({"success": False, "error": "SMTP 认证失败，请检查账号密码"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"发送失败: {e}"}, ensure_ascii=False)
