# eventlet monkey_patch 必须在任何其他导入之前执行（如果使用 eventlet）
import os
import sys


from app import create_app
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path, override=True)

app = create_app(os.getenv("FLASK_ENV", "development"))


if __name__ == "__main__":
    # 开发环境：启用多线程处理并发请求
    # 生产环境建议用 Waitress: pip install waitress && waitress-serve --host=0.0.0.0 --port=5000 run:app
    use_debug = os.getenv("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=5001, debug=use_debug, threaded=True)
