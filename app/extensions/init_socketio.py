"""
Flask-SocketIO 初始化模块。

用于实时语音识别（Vosk 流式识别）的 WebSocket 通信。
"""

from flask_socketio import SocketIO

# 全局 SocketIO 实例
socketio = SocketIO()


def init_socketio(app):
    """初始化 SocketIO。"""
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",  # 使用线程模式，兼容现有 Flask 应用
        logger=False,
        engineio_logger=False,
    )
    return socketio
