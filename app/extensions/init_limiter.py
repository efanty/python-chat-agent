from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 使用内存存储速率限制计数器。
# 生产环境使用 gunicorn/uwsgi 等 WSGI 服务器时无双进程问题。
# 如需多 worker 部署，请改为 redis:// 存储。
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200/hour", "50/minute"])

def init_limiter(app: Flask):
    limiter.init_app(app)
