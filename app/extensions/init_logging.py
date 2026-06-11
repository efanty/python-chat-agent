import os
import logging
from flask import Flask, request
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pytz

basedir = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

class CustomFormatter(logging.Formatter):
    """自定义日志格式类，使用东八区时间"""
    def formatTime(self, record, datefmt=None):
        # 获取东八区时间
        tz = pytz.timezone('Asia/Shanghai')
        dt = datetime.now(tz)
        # 格式化为字符串，毫秒保留3位
        return dt.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]  # 移除最后3位微秒，保留毫秒

def init_logging(app: Flask):
    # 确保日志目录存在
    log_dir = os.path.join(basedir, 'logs')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 设置应用日志级别
    app.logger.setLevel(logging.INFO)
    
    # 创建文件处理器
    log_file = os.path.join(log_dir, 'log.log')
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding='utf-8'  # 确保支持中文
    )
    
    # 设置格式化器
    formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # 移除可能已存在的相同类型的处理器，避免重复
    for handler in app.logger.handlers[:]:
        if isinstance(handler, RotatingFileHandler):
            app.logger.removeHandler(handler)
    
    # 添加文件处理器
    app.logger.addHandler(file_handler)
    
    # 同时添加控制台处理器用于调试
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    app.logger.addHandler(console_handler)
