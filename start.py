import subprocess
import sys
import os
from threading import Thread

# 安装依赖：pip install pystray pillow

def run_server():
    # 启动你的服务
    subprocess.Popen(
        [os.path.join("venv", "Scripts", "python.exe"), "run.py"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

def quit_app(icon, item):
    icon.stop()
    os._exit(0)

def main():
    import pystray
    from PIL import Image, ImageDraw
    
    # 创建图标
    image = Image.new('RGB', (64, 64), color='#1890ff')
    draw = ImageDraw.Draw(image)
    draw.rectangle([16, 16, 48, 48], fill='white')
    
    # 创建托盘菜单
    icon = pystray.Icon(
        "DeepAgent",
        image,
        "DeepAgent Server",
        menu=pystray.Menu(
            pystray.MenuItem("服务运行中...", lambda: None, enabled=False),
            pystray.MenuItem("退出", quit_app)
        )
    )
    
    # 启动服务
    run_server()
    
    # 显示托盘图标
    icon.run()

if __name__ == "__main__":
    main()