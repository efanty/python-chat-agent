"""
One-time migration: encrypt existing plaintext API keys in the database.

Usage:
    cd project-root && python -m app.utils.migrate_encrypt

IMPORTANT: sets the plaintext value on the model attribute and lets
SQLAlchemy's EncryptedString TypeDecorator handle the actual encryption.
Do NOT call encrypt() before setattr() — that would cause double-encryption.
"""
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"), override=True)

from app import create_app
from app.extensions import db
from app.utils.crypto import _get_fernet
from cryptography.fernet import InvalidToken
import sqlalchemy as sa


def _is_encrypted_from_raw(value: str) -> bool:
    """Check raw DB value — is it a valid Fernet token?"""
    if not value:
        return False
    try:
        _get_fernet().decrypt(value.encode())
        return True
    except (InvalidToken, Exception):
        return False


def run():
    app = create_app()
    with app.app_context():
        total_up = 0
        total_skip = 0

        # ── 1. LLMModel.api_key ──
        rows = db.session.execute(
            sa.text("SELECT id, api_key FROM llm_models")
        ).fetchall()
        up = 0
        skip = 0
        for row in rows:
            raw = row.api_key
            if not raw:
                skip += 1
                continue
            if _is_encrypted_from_raw(raw):
                skip += 1
                continue
            # Read model via ORM (decrypts), set plaintext, let TypeDecorator encrypt
            from app.models.llm_model import LLMModel
            m = db.session.get(LLMModel, row.id)
            m.api_key = raw  # plaintext — TypeDecorator will encrypt on commit
            up += 1
        db.session.flush()
        total_up += up
        total_skip += skip
        print(f"  LLMModel.api_key: {up} encrypted, {skip} skipped")

        # ── 2. APIEndpoint.auth_value ──
        rows = db.session.execute(
            sa.text("SELECT id, auth_value FROM api_endpoints")
        ).fetchall()
        up = 0
        skip = 0
        for row in rows:
            raw = row.auth_value
            if not raw:
                skip += 1
                continue
            if _is_encrypted_from_raw(raw):
                skip += 1
                continue
            from app.models.api_endpoint import APIEndpoint
            e = db.session.get(APIEndpoint, row.id)
            e.auth_value = raw
            up += 1
        db.session.flush()
        total_up += up
        total_skip += skip
        print(f"  APIEndpoint.auth_value: {up} encrypted, {skip} skipped")

        # ── 3. MCPTool.env_vars ──
        rows = db.session.execute(
            sa.text("SELECT id, env_vars FROM mcp_tools")
        ).fetchall()
        up = 0
        skip = 0
        for row in rows:
            raw = row.env_vars
            if not raw:
                skip += 1
                continue
            if _is_encrypted_from_raw(raw):
                skip += 1
                continue
            from app.models.mcp_tool import MCPTool
            t = db.session.get(MCPTool, row.id)
            t.env_vars = raw
            up += 1
        db.session.flush()
        total_up += up
        total_skip += skip
        print(f"  MCPTool.env_vars: {up} encrypted, {skip} skipped")

        db.session.commit()
        print(f"\nDone. {total_up} fields encrypted, {total_skip} skipped.")


if __name__ == "__main__":
    run()
