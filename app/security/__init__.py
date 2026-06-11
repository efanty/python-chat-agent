"""
Security module — LLM-powered attack detection and automated defense.

Provides:
- run_analysis: Analyze app logs for attack patterns using LLM
- start_analysis / stop_analysis: Background analysis loop control
- block_ip / is_blocked / unblock_ip: IP blocklist management
- send_alert_email: Send security alert email to admin users
- execute_defense: Execute defensive actions based on analysis results
- init_middleware: Register request pre-processing hooks
"""
from .analyzer import run_analysis, start_analysis, stop_analysis
from .defender import (block_ip, is_blocked, unblock_ip, get_blocked_ips,
                       send_alert_email, execute_defense)
from .middleware import init_middleware

__all__ = [
    "run_analysis", "start_analysis", "stop_analysis",
    "block_ip", "is_blocked", "unblock_ip", "get_blocked_ips",
    "send_alert_email", "execute_defense",
    "init_middleware",
]
