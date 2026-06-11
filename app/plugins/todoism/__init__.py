"""
初始化插件：待办清单
"""
import os
from flask import Flask
from .main import bp


# 获取插件所在的目录（结尾没有分割符号）
dir_path = os.path.dirname(__file__).replace("\\", "/")
folder_name = dir_path[dir_path.rfind("/") + 1:]  # 插件文件夹名称

def event_init(app: Flask):
    app.register_blueprint(bp)
        
