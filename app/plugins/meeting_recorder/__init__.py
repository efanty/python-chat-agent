"""
会议录音插件 — 初始化
"""
import os
from flask import Flask
from .main import bp
from . import routes  # noqa: F401

dir_path = os.path.dirname(__file__).replace("\\", "/")
folder_name = dir_path[dir_path.rfind("/") + 1:]

def event_init(app: Flask):
    """初始化完成时会调用这里"""
    app.register_blueprint(bp)
