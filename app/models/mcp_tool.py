from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db
from app.utils.crypto import EncryptedString


class MCPTool(db.Model):
    __tablename__ = "mcp_tools"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    tool_type = db.Column(db.String(32), default="custom")  # custom, builtin, mcp_server
    transport = db.Column(db.String(32), default="stdio")  # stdio, sse, streamable_http
    command = db.Column(db.String(256), nullable=True)  # For stdio MCP servers
    args = db.Column(db.Text, nullable=True)  # JSON string of arguments
    env_vars = db.Column(EncryptedString, nullable=True)  # JSON string of env vars (encrypted)
    endpoint = db.Column(db.String(256), nullable=True)  # For SSE / Streamable HTTP MCP servers
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<MCPTool {self.name}>"
