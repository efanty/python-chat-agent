"""
Socket.IO 事件处理 — 实时语音识别。

浏览器通过 WebSocket 发送 PCM 音频数据，Vosk 流式识别后实时返回文字。
"""

import uuid
import logging
from flask import current_app, request
from flask_login import current_user
from app.extensions.init_socketio import socketio
from app.services.vosk_service import (
    process_audio_chunk,
    get_final_result,
    remove_session,
    create_session,
)

logger = logging.getLogger(__name__)


@socketio.on("connect", namespace="/ws/voice")
def on_connect():
    """客户端连接语音识别 WebSocket。"""
    session_id = str(uuid.uuid4())
    # 存储 session_id 到 flask 的 session 中
    from flask import session as flask_session
    flask_session["voice_session_id"] = session_id
    logger.info(f"语音识别客户端连接: session={session_id}")
    return {"session_id": session_id}


@socketio.on("disconnect", namespace="/ws/voice")
def on_disconnect():
    """客户端断开连接。"""
    from flask import session as flask_session
    session_id = flask_session.pop("voice_session_id", None)
    if session_id:
        remove_session(session_id)
        logger.info(f"语音识别客户端断开: session={session_id}")


@socketio.on("start", namespace="/ws/voice")
def on_start(data):
    """开始语音识别会话。

    浏览器发送: {"session_id": "xxx", "sample_rate": 16000}
    """
    session_id = data.get("session_id", "")
    sample_rate = int(data.get("sample_rate", 16000))

    if not session_id:
        session_id = str(uuid.uuid4())
        from flask import session as flask_session
        flask_session["voice_session_id"] = session_id

    create_session(session_id, sample_rate)
    logger.info(f"语音识别会话开始: session={session_id}, rate={sample_rate}")

    socketio.emit("started", {
        "session_id": session_id,
        "sample_rate": sample_rate,
    }, namespace="/ws/voice")


@socketio.on("audio", namespace="/ws/voice")
def on_audio(data):
    """接收浏览器发送的 PCM 音频数据，进行流式识别。

    浏览器发送: {"session_id": "xxx", "data": "<base64 PCM data>"}
    """
    import base64

    session_id = data.get("session_id", "")
    audio_b64 = data.get("data", "")

    if not session_id or not audio_b64:
        return

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        logger.warning(f"音频数据解码失败: session={session_id}")
        return

    if len(audio_bytes) < 64:  # 太短的数据跳过
        return

    try:
        result = process_audio_chunk(session_id, audio_bytes)

        # 只要有文本就 emit（包括 partial 中间结果）
        text = result.get("text", "").strip()
        if text:
            socketio.emit("result", {
                "session_id": session_id,
                "text": text,
                "partial": result.get("partial", True),
                "final": result.get("final", False),
            }, namespace="/ws/voice")
    except Exception as e:
        logger.error(f"语音识别处理失败: session={session_id}, error={str(e)}")


@socketio.on("stop", namespace="/ws/voice")
def on_stop(data):
    """停止语音识别，获取最终结果。

    浏览器发送: {"session_id": "xxx"}
    """
    session_id = data.get("session_id", "")

    if not session_id:
        return

    try:
        final_text = get_final_result(session_id)
        socketio.emit("final_result", {
            "session_id": session_id,
            "text": final_text,
        }, namespace="/ws/voice")
    except Exception as e:
        logger.error(f"获取最终结果失败: session={session_id}, error={str(e)}")
    finally:
        remove_session(session_id)
