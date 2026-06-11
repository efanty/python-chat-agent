"""
LogAnalyzer — periodically analyzes app logs for attack patterns using LLM.

Uses the same LLM infrastructure as the rest of the application
(call_llm_chat, resolve_api_key) to analyze recent log entries
and detect potential security attacks.

The analysis runs on a background thread every N minutes (configurable).
Results are passed to Defender for automated response.
"""
import os
import re
import json
import time
import threading
from pathlib import Path
from flask import current_app
from app.logger import log_admin, log_error
from app.utils.settings import get_setting, get_setting_int
from app.utils.llm_utils import resolve_api_key, call_llm_chat


# ── Constants ──────────────────────────────────────────────────────────────

_LOG_FILE = None  # Will be resolved on first use
_ANALYSIS_INTERVAL = 300  # Default: 5 minutes
_RUNNING = False
_THREAD = None
_LOCK = threading.Lock()

# Severity keywords to extract suspicious log entries
_SUSPICIOUS_PATTERNS = [
    # Authentication failures
    r"登录失败",
    r"认证失败",
    r"验证失败",
    r"密码错误",
    r"token.*无效",
    r"token.*expired",
    # Rate limit hits
    r"rate limit",
    r"频率限制",
    r"too many",
    r"429",
    # Error patterns
    r"错误.*SQL",
    r"错误.*注入",
    r"错误.*XSS",
    r"错误.*路径",
    r"错误.*遍历",
    # Permission violations
    r"权限不足",
    r"403",
    r"未授权",
    r"unauthorized",
    # CSRF
    r"CSRF",
    r"csrf",
]


def _get_log_file() -> str:
    """Get the path to the app log file."""
    global _LOG_FILE
    if _LOG_FILE is None:
        # __file__ = app/security/analyzer.py, need 3x dirname to reach project root
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs"
        )
        _LOG_FILE = os.path.join(log_dir, "app.log")
    return _LOG_FILE


def _extract_suspicious_entries(since_line: int = 0) -> tuple[list[str], int]:
    """Extract suspicious log entries from the app log file.

    Args:
        since_line: Line number to start reading from (0 = start of file).

    Returns:
        (suspicious_lines, total_lines_read)
    """
    log_file = _get_log_file()
    if not os.path.exists(log_file):
        return [], 0

    suspicious = []
    total_lines = 0

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i < since_line:
                    continue
                total_lines = i + 1
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # Check if line matches any suspicious pattern
                for pattern in _SUSPICIOUS_PATTERNS:
                    if re.search(pattern, line_stripped, re.IGNORECASE):
                        suspicious.append(line_stripped)
                        break
    except Exception as e:
        log_error("安全日志读取失败: %s", str(e))
        return [], since_line

    return suspicious, total_lines


def _build_analysis_prompt(suspicious_entries: list[str]) -> str:
    """Build the LLM prompt for security analysis."""
    entries_text = "\n".join(suspicious_entries[-50:])  # Limit to last 50 entries
    if not entries_text:
        entries_text = "（无异常日志）"

    return f"""你是一个网站安全分析专家。以下是网站最近的安全相关日志条目：

{entries_text}

请分析这些日志，判断是否存在攻击行为。如果存在攻击，请提供详细信息。

请严格按照以下JSON格式输出分析结果（不要包含其他文字）：

{{
    "has_attack": true/false,
    "attack_type": "攻击类型（如：暴力破解/SQL注入/XSS/爬虫/CC攻击/未知等）",
    "severity": "严重程度（low/medium/high/critical）",
    "attacker_ip": "攻击者IP地址（如无法确定则填空字符串）",
    "details": "攻击详情描述",
    "suggested_action": "建议的应对措施"
}}

注意：
- 如果不存在攻击行为，has_attack 设为 false
- 仅根据日志内容分析，不要臆测不存在的信息
- 攻击类型要具体"""


def _parse_llm_response(response_text: str) -> dict:
    """Parse LLM response into a structured analysis dict."""
    if not response_text:
        return {"has_attack": False, "attack_type": "", "severity": "low",
                "attacker_ip": "", "details": "LLM未返回有效分析结果",
                "suggested_action": ""}

    # Try to extract JSON from the response
    # Handle cases where LLM wraps JSON in markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find JSON object directly
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
        else:
            return {"has_attack": False, "attack_type": "", "severity": "low",
                    "attacker_ip": "", "details": "无法解析LLM响应",
                    "suggested_action": ""}

    try:
        result = json.loads(json_str)
        # Ensure all required keys exist
        required_keys = ["has_attack", "attack_type", "severity", "attacker_ip",
                         "details", "suggested_action"]
        for key in required_keys:
            if key not in result:
                result[key] = "" if key != "has_attack" else False
        return result
    except json.JSONDecodeError:
        return {"has_attack": False, "attack_type": "", "severity": "low",
                "attacker_ip": "", "details": "LLM返回了无效的JSON格式",
                "suggested_action": ""}


def _get_llm_config() -> tuple[str, str, str]:
    """Get LLM configuration for security analysis.

    Uses a dedicated security analysis model if configured,
    otherwise falls back to the default model settings.

    Returns:
        (api_key, model_id, api_base)
    """
    # Try security-specific model settings first
    api_key = get_setting("security_llm_api_key", "")
    model_id = get_setting("security_llm_model", "")
    api_base = get_setting("security_llm_api_base", "")

    if api_key and model_id:
        return api_key, model_id, api_base

    # Fallback: try to find any configured model
    try:
        from app.models.llm_model import LLMModel
        model = LLMModel.query.filter(
            LLMModel.is_active == True,
            LLMModel.model_type.in_(["text"])
        ).first()
        if model:
            resolved_key = resolve_api_key(model)
            if resolved_key:
                return resolved_key, model.model_id, model.api_base or ""
    except Exception:
        pass

    # Last resort: try environment variables
    env_key = os.getenv("SECURITY_LLM_API_KEY", "")
    env_model = os.getenv("SECURITY_LLM_MODEL", "")
    if env_key and env_model:
        return env_key, env_model, os.getenv("SECURITY_LLM_API_BASE", "")

    return "", "", ""


def _rule_based_analysis(suspicious: list[str]) -> dict:
    """Run rule-based analysis on suspicious log entries without LLM.

    Extracts attacker IPs from log entries and determines if
    there are enough repeated failures to warrant blocking.

    Returns:
        Analysis result dict (same format as LLM analysis).
    """
    # Count login failures per IP
    ip_failures: dict[str, int] = {}
    for entry in suspicious:
        # Extract IP from log format: "... | IP | ..."
        parts = entry.split(" | ")
        for part in parts:
            part = part.strip()
            # Match IPv4 addresses
            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", part):
                ip_failures[part] = ip_failures.get(part, 0) + 1
                break

    # Find the most aggressive attacker
    if ip_failures:
        worst_ip = max(ip_failures, key=ip_failures.get)
        worst_count = ip_failures[worst_ip]

        if worst_count >= 10:
            return {"has_attack": True, "attack_type": "暴力破解",
                    "severity": "high", "attacker_ip": worst_ip,
                    "details": f"IP {worst_ip} 在日志中有 {worst_count} 次失败记录",
                    "suggested_action": "自动封禁该IP"}
        elif worst_count >= 5:
            return {"has_attack": True, "attack_type": "可疑访问",
                    "severity": "medium", "attacker_ip": worst_ip,
                    "details": f"IP {worst_ip} 在日志中有 {worst_count} 次可疑记录",
                    "suggested_action": "临时封禁该IP"}

    return {"has_attack": False, "attack_type": "", "severity": "low",
            "attacker_ip": "", "details": "规则分析未发现攻击",
            "suggested_action": ""}


def run_analysis() -> dict:
    """Run a single security analysis cycle.

    First tries rule-based analysis for immediate detection.
    If LLM is configured, also runs LLM analysis for deeper inspection.

    Returns:
        Analysis result dict (same format as _parse_llm_response output).
    """
    # Extract suspicious entries from log
    suspicious, _ = _extract_suspicious_entries()
    if not suspicious:
        return {"has_attack": False, "attack_type": "", "severity": "low",
                "attacker_ip": "", "details": "未发现可疑日志条目",
                "suggested_action": ""}

    # Step 1: Rule-based analysis (always runs, no LLM needed)
    rule_result = _rule_based_analysis(suspicious)
    if rule_result.get("has_attack"):
        log_admin("规则分析检测到攻击 — type=%s, severity=%s, ip=%s",
                  rule_result.get("attack_type"), rule_result.get("severity"),
                  rule_result.get("attacker_ip"))
        return rule_result

    # Step 2: LLM analysis (only if configured)
    api_key, model_id, api_base = _get_llm_config()
    if not api_key or not model_id:
        log_admin("安全分析LLM未配置 — 规则分析未发现攻击")
        return {"has_attack": False, "attack_type": "", "severity": "low",
                "attacker_ip": "", "details": "规则分析未发现攻击，LLM未配置",
                "suggested_action": ""}

    # Build prompt and call LLM
    prompt = _build_analysis_prompt(suspicious)
    try:
        response = call_llm_chat(
            api_key=api_key,
            model_id=model_id,
            messages=[{"role": "user", "content": prompt}],
            api_base=api_base or None,
            max_tokens=1024,
            temperature=0.1,  # Low temperature for consistent analysis
            timeout=30,
        )
        result = _parse_llm_response(response)
        log_admin("安全分析完成 — has_attack=%s, type=%s, severity=%s, ip=%s",
                  result.get("has_attack"), result.get("attack_type"),
                  result.get("severity"), result.get("attacker_ip"))
        return result
    except Exception as e:
        log_error("安全分析LLM调用失败: %s", str(e))
        return {"has_attack": False, "attack_type": "", "severity": "low",
                "attacker_ip": "", "details": f"LLM调用失败: {e}",
                "suggested_action": ""}


# ── Background scheduler ───────────────────────────────────────────────────

def _analysis_loop(app):
    """Background loop that periodically runs security analysis."""
    global _RUNNING
    interval = get_setting_int("security_analysis_interval", 300)  # Default: 5 min

    while _RUNNING:
        try:
            with app.app_context():
                result = run_analysis()
                if result.get("has_attack"):
                    from .defender import execute_defense
                    execute_defense(result)
        except Exception as e:
            log_error("安全分析循环异常: %s", str(e))

        # Sleep for the configured interval
        for _ in range(interval):
            if not _RUNNING:
                break
            time.sleep(1)


def start_analysis(app, interval_seconds: int = 300) -> None:
    """Start the background security analysis loop.

    Args:
        app: Flask application instance.
        interval_seconds: Analysis interval in seconds (default: 300).
    """
    global _RUNNING, _THREAD, _ANALYSIS_INTERVAL

    with _LOCK:
        if _RUNNING:
            log_admin("安全分析已在运行中")
            return

        _ANALYSIS_INTERVAL = interval_seconds
        _RUNNING = True
        _THREAD = threading.Thread(
            target=_analysis_loop,
            args=(app,),
            daemon=True,
            name="security-analyzer",
        )
        _THREAD.start()
        log_admin("安全分析已启动 — interval=%ds", interval_seconds)


def stop_analysis() -> None:
    """Stop the background security analysis loop."""
    global _RUNNING
    with _LOCK:
        _RUNNING = False
    log_admin("安全分析已停止")
