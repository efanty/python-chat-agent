"""
Defender — executes defensive actions based on LLM analysis results.

Provides:
- IP blocking (in-memory cache with TTL)
- Rate limit adjustment
- Email alert to admin users
- Logging of all defensive actions
"""
import os
import time
import smtplib
import threading
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path
from flask import current_app
from app.logger import log_admin, log_error, log_auth
from app.utils.settings import get_setting, get_setting_int


# ── In-memory blocklist ────────────────────────────────────────────────────
# Key: IP address, Value: expiry timestamp
_blocked_ips: dict[str, float] = {}
_blocklist_lock = threading.Lock()

# Deduplication for email alerts: {alert_key: expiry_timestamp}
_email_sent: dict[str, float] = {}
_email_lock = threading.Lock()


# ── Public API ─────────────────────────────────────────────────────────────

def block_ip(ip: str, duration_seconds: int = 1800) -> None:
    """Block an IP address for a given duration (default: 30 minutes)."""
    expiry = time.time() + duration_seconds
    with _blocklist_lock:
        _blocked_ips[ip] = expiry
    log_admin("IP已封禁 — ip=%s, duration=%ds", ip, duration_seconds)


def unblock_ip(ip: str) -> None:
    """Remove an IP from the blocklist."""
    with _blocklist_lock:
        _blocked_ips.pop(ip, None)
    log_admin("IP已解封 — ip=%s", ip)


def is_blocked(ip: str) -> bool:
    """Check if an IP is currently blocked."""
    with _blocklist_lock:
        expiry = _blocked_ips.get(ip)
        if expiry is None:
            return False
        if time.time() > expiry:
            del _blocked_ips[ip]
            return False
        return True


def get_blocked_ips() -> list[dict]:
    """Return list of currently blocked IPs with remaining time."""
    now = time.time()
    result = []
    with _blocklist_lock:
        expired = [ip for ip, exp in _blocked_ips.items() if now > exp]
        for ip in expired:
            del _blocked_ips[ip]
        for ip, exp in _blocked_ips.items():
            result.append({
                "ip": ip,
                "remaining_seconds": int(exp - now),
            })
    return result


# ── Email alert ────────────────────────────────────────────────────────────

def _build_mail_cfg():
    """Read mail config from DB settings + app.config (safe for threads)."""
    c = current_app.config
    return {
        "MAIL_SERVER": get_setting("mail_server", c.get("MAIL_SERVER", "localhost")),
        "MAIL_PORT": get_setting("mail_port", c.get("MAIL_PORT", 587)),
        "MAIL_USERNAME": get_setting("mail_username", c.get("MAIL_USERNAME", "")),
        "MAIL_PASSWORD": get_setting("mail_password", c.get("MAIL_PASSWORD", "")),
        "MAIL_DEFAULT_SENDER": get_setting("mail_default_sender",
                                           c.get("MAIL_DEFAULT_SENDER", "noreply@agentapp.local")),
    }


def _send_email_async(cfg, to_addr, subject, html_body, log_label):
    """Send email via background thread using smtplib directly."""
    def _do_send():
        try:
            msg = MIMEText(html_body, "html", "utf-8")
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = cfg.get("MAIL_DEFAULT_SENDER", "noreply@agentapp.local")
            msg["To"] = to_addr

            server = cfg.get("MAIL_SERVER", "localhost")
            port = int(cfg.get("MAIL_PORT", 587))
            username = cfg.get("MAIL_USERNAME", "") or ""
            password = cfg.get("MAIL_PASSWORD", "") or ""
            use_tls = not (port == 465)
            use_ssl = (port == 465)

            if use_ssl:
                s = smtplib.SMTP_SSL(server, port, timeout=15)
            else:
                s = smtplib.SMTP(server, port, timeout=15)
                if use_tls:
                    s.starttls()

            if username:
                s.login(username, password)
            s.sendmail(msg["From"], [to_addr], msg.as_bytes())
            s.quit()
        except Exception as e:
            log_error("安全告警邮件发送失败 (%s): %s", to_addr, str(e))

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()


def _get_admin_emails() -> list[str]:
    """Get email addresses of all admin users."""
    try:
        from app.models.user import User
        admins = User.query.filter_by(role="admin", is_active=True).all()
        return [u.email for u in admins if u.email]
    except Exception:
        return []


def send_alert_email(attack_type: str, severity: str, attacker_ip: str,
                     details: str, suggested_action: str) -> None:
    """Send security alert email to all admin users.

    Deduplication: same attack_type + IP within 30 minutes only sends once.
    """
    # Deduplication key
    dedup_key = f"{attack_type}|{attacker_ip}"
    now = time.time()
    with _email_lock:
        existing = _email_sent.get(dedup_key)
        if existing and existing > now:
            return  # Already sent within cooldown period
        _email_sent[dedup_key] = now + 1800  # 30-minute cooldown

    cfg = _build_mail_cfg()
    admin_emails = _get_admin_emails()
    if not admin_emails:
        log_admin("安全告警邮件未发送（无管理员邮箱）— type=%s, ip=%s", attack_type, attacker_ip)
        return

    subject = f"[安全警告] 检测到{attack_type}攻击 - 严重程度: {severity}"
    html_body = f"""<h2>🔒 安全攻击告警</h2>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse; font-family:Arial;">
<tr><td><b>检测时间</b></td><td>{time.strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
<tr><td><b>攻击类型</b></td><td>{attack_type}</td></tr>
<tr><td><b>严重程度</b></td><td>{severity}</td></tr>
<tr><td><b>攻击者IP</b></td><td>{attacker_ip}</td></tr>
<tr><td><b>详细信息</b></td><td>{details}</td></tr>
<tr><td><b>建议措施</b></td><td>{suggested_action}</td></tr>
</table>
<p style="color:#888; font-size:12px;">此邮件由 DeepAgent Chat 安全系统自动发送</p>"""

    for email in admin_emails:
        _send_email_async(cfg, email, subject, html_body, "安全告警")


# ── Execute defense actions ────────────────────────────────────────────────

def execute_defense(analysis: dict) -> None:
    """Execute defensive actions based on LLM analysis result.

    Args:
        analysis: dict with keys:
            - has_attack (bool): whether an attack is detected
            - attack_type (str): type of attack
            - severity (str): low/medium/high/critical
            - attacker_ip (str): attacker IP address
            - details (str): detailed description
            - suggested_action (str): recommended action
    """
    if not analysis.get("has_attack"):
        return

    attack_type = analysis.get("attack_type", "未知")
    severity = analysis.get("severity", "low")
    attacker_ip = analysis.get("attacker_ip", "")
    details = analysis.get("details", "")
    suggested_action = analysis.get("suggested_action", "")

    # Log the attack
    log_auth("攻击检测 — type=%s, severity=%s, ip=%s, detail=%s",
             attack_type, severity, attacker_ip, details)

    # Execute actions based on severity
    if severity in ("critical", "high"):
        # Auto-block IP for 1 hour
        if attacker_ip:
            block_ip(attacker_ip, 3600)
        # Always send email for high/critical
        send_alert_email(attack_type, severity, attacker_ip, details, suggested_action)

    elif severity == "medium":
        # Auto-block IP for 15 minutes
        if attacker_ip:
            block_ip(attacker_ip, 900)
        # Send email alert
        send_alert_email(attack_type, severity, attacker_ip, details, suggested_action)

    else:  # low
        # Just log, no automatic blocking
        # Send email only if configured
        if get_setting("security_alert_low_send_email", "false") == "true":
            send_alert_email(attack_type, severity, attacker_ip, details, suggested_action)
