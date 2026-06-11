"""
Vosk 流式语音识别服务。

用于实时语音输入/字幕场景，通过 WebSocket (Socket.IO) 接收浏览器 PCM 音频流，
使用 Vosk 进行流式识别，实时返回中间结果。

保留 FunASR 用于录音文件离线批量转写（高准确率）。
"""

import os
import json
import queue
import threading
import time
import wave
import struct
import io
from pathlib import Path
from flask import current_app

# 全局 Vosk 模型实例（延迟加载，只初始化一次）
_vosk_model = None
_vosk_model_lock = None

# 活跃的识别会话
_active_sessions = {}
_active_sessions_lock = threading.Lock()


def _get_vosk_model_path() -> str:
    """获取 Vosk 中文模型路径。

    优先使用环境变量 VOSK_MODEL_PATH，否则在项目目录下查找 vosk-model-cn-* 目录。
    """
    env_path = os.environ.get("VOSK_MODEL_PATH")
    if env_path and os.path.isdir(env_path):
        return env_path

    # 在项目根目录查找
    project_root = Path(__file__).resolve().parent.parent.parent
    for p in project_root.iterdir():
        if p.is_dir() and p.name.startswith("vosk-model"):
            return str(p)

    # 在 app 目录下查找
    app_dir = Path(__file__).resolve().parent.parent
    for p in app_dir.iterdir():
        if p.is_dir() and p.name.startswith("vosk-model"):
            return str(p)

    return ""


def _get_vosk_model():
    """获取或初始化 Vosk 模型（单例模式）。"""
    global _vosk_model, _vosk_model_lock

    if _vosk_model is not None:
        return _vosk_model

    if _vosk_model_lock is None:
        _vosk_model_lock = threading.Lock()

    with _vosk_model_lock:
        if _vosk_model is not None:
            return _vosk_model

        try:
            import vosk

            model_path = _get_vosk_model_path()
            if not model_path:
                # 自动下载中文模型
                current_app.logger.info("未找到 Vosk 中文模型，正在自动下载 vosk-model-cn-0.22 ...")
                vosk.SetLogLevel(-1)
                _vosk_model = vosk.Model(lang="cn")
                current_app.logger.info("Vosk 中文模型自动下载完成")
            else:
                current_app.logger.info(f"正在加载 Vosk 模型: {model_path}")
                vosk.SetLogLevel(-1)
                _vosk_model = vosk.Model(model_path)
                current_app.logger.info("Vosk 模型加载完成")

            return _vosk_model

        except Exception as e:
            current_app.logger.error(f"Vosk 模型加载失败: {str(e)}")
            raise RuntimeError(f"Vosk 模型加载失败: {str(e)}")


class VoskSession:
    """单个 Vosk 识别会话。

    每个 WebSocket 连接对应一个会话，包含独立的识别器。
    """

    def __init__(self, session_id: str, sample_rate: int = 16000):
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.model = _get_vosk_model()
        self.recognizer = vosk.KaldiRecognizer(self.model, sample_rate)
        self.recognizer.SetWords(True)  # 启用词级时间戳
        self.buffer = b""
        self.last_result = ""
        self.created_at = time.time()
        self.last_active = time.time()

    def process_audio(self, audio_data: bytes) -> dict:
        """处理一段 PCM 音频数据，返回识别结果。

        Returns:
            dict: {"text": str, "partial": bool, "final": bool}
        """
        self.last_active = time.time()
        self.buffer += audio_data

        result = {"text": "", "partial": True, "final": False}

        if self.recognizer.AcceptWaveform(audio_data):
            # 最终结果（一句话结束）
            final_json = json.loads(self.recognizer.Result())
            text = final_json.get("text", "").strip()
            if text:
                self.last_result = text
                result = {"text": text, "partial": False, "final": True}
        else:
            # 中间结果（正在说的部分）
            partial_json = json.loads(self.recognizer.PartialResult())
            text = partial_json.get("partial", "").strip()
            if text:
                result = {"text": text, "partial": True, "final": False}

        return result

    def get_final(self) -> str:
        """获取最终识别结果（清空识别器缓冲区）。"""
        final_json = json.loads(self.recognizer.FinalResult())
        text = final_json.get("text", "").strip()
        if text:
            self.last_result = text
        return self.last_result

    def is_expired(self, timeout: int = 300) -> bool:
        """检查会话是否超时（默认 5 分钟无活动）。"""
        return (time.time() - self.last_active) > timeout


def create_session(session_id: str, sample_rate: int = 16000) -> VoskSession:
    """创建新的识别会话。"""
    session = VoskSession(session_id, sample_rate)
    with _active_sessions_lock:
        # 清理过期会话
        _cleanup_expired_sessions()
        _active_sessions[session_id] = session
    return session


def get_session(session_id: str) -> VoskSession:
    """获取识别会话，不存在则创建。"""
    with _active_sessions_lock:
        if session_id in _active_sessions:
            return _active_sessions[session_id]
    return create_session(session_id)


def remove_session(session_id: str):
    """移除识别会话。"""
    with _active_sessions_lock:
        _active_sessions.pop(session_id, None)


def _cleanup_expired_sessions():
    """清理过期会话。"""
    now = time.time()
    expired = [
        sid for sid, sess in _active_sessions.items()
        if sess.is_expired()
    ]
    for sid in expired:
        _active_sessions.pop(sid, None)


def process_audio_chunk(session_id: str, audio_data: bytes, sample_rate: int = 16000) -> dict:
    """处理一段音频数据并返回识别结果。

    这是供外部调用的便捷函数。

    Args:
        session_id: 会话 ID
        audio_data: PCM 16kHz 16bit mono 音频数据
        sample_rate: 采样率，默认 16000

    Returns:
        dict: {"text": str, "partial": bool, "final": bool}
    """
    session = get_session(session_id)
    return session.process_audio(audio_data)


def get_final_result(session_id: str) -> str:
    """获取会话的最终识别结果。"""
    session = get_session(session_id)
    return session.get_final()
