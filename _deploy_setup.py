"""
Deployment helper — called by deploy.bat.
Ensures .env has a valid SECRET_KEY and initializes the database.
"""
import os
import re
import sys
import secrets

_project_root = os.path.dirname(os.path.abspath(__file__))
os.chdir(_project_root)

# Load existing .env
from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"), override=True)

# ── Ensure SECRET_KEY ─────────────────────────────────────────
env_path = os.path.join(_project_root, ".env")
current_key = os.environ.get("SECRET_KEY", "")

if not current_key or current_key == "change-this-to-a-random-secret-key-in-production":
    new_key = secrets.token_hex(32)
    print(f"  生成新的 SECRET_KEY: {new_key[:8]}...")

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        if re.search(r"^SECRET_KEY=", content, re.MULTILINE):
            content = re.sub(r"^SECRET_KEY=.*", f"SECRET_KEY={new_key}", content, flags=re.MULTILINE)
        else:
            content += f"\nSECRET_KEY={new_key}\n"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.environ["SECRET_KEY"] = new_key
        print("  SECRET_KEY 已写入 .env")
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"SECRET_KEY={new_key}\n")
        os.environ["SECRET_KEY"] = new_key
        print("  .env 已创建，SECRET_KEY 已设置")
else:
    print(f"  SECRET_KEY 已存在，保留")

# ── Create DB tables ─────────────────────────────────────────
print("  初始化数据库...")
sys.path.insert(0, _project_root)
from app import create_app
app = create_app()
print("  数据库表已创建")
