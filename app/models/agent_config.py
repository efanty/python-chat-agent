from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


# Association tables for many-to-many relationships
agent_mcp_tools = db.Table(
    "agent_mcp_tools",
    db.Column("agent_id", db.Integer, db.ForeignKey("agent_configs.id"), primary_key=True),
    db.Column("mcp_tool_id", db.Integer, db.ForeignKey("mcp_tools.id"), primary_key=True),
)

agent_api_endpoints = db.Table(
    "agent_api_endpoints",
    db.Column("agent_id", db.Integer, db.ForeignKey("agent_configs.id"), primary_key=True),
    db.Column("api_endpoint_id", db.Integer, db.ForeignKey("api_endpoints.id"), primary_key=True),
)

agent_skills = db.Table(
    "agent_skills",
    db.Column("agent_id", db.Integer, db.ForeignKey("agent_configs.id"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id"), primary_key=True),
)

agent_knowledge_bases = db.Table(
    "agent_knowledge_bases",
    db.Column("agent_id", db.Integer, db.ForeignKey("agent_configs.id"), primary_key=True),
    db.Column("kb_id", db.Integer, db.ForeignKey("knowledge_bases.id"), primary_key=True),
)


class AgentConfig(db.Model):
    __tablename__ = "agent_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    system_prompt = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    allowed_roles = db.Column(db.String(128), default="all")  # comma-separated: user,vip,admin or "all"
    default_model_id = db.Column(db.Integer, db.ForeignKey("llm_models.id"), nullable=True)

    # Configuration
    max_iterations = db.Column(db.Integer, default=10)
    temperature = db.Column(db.Float, default=0.7)
    enable_sandbox = db.Column(db.Boolean, default=True)
    enable_file_upload = db.Column(db.Boolean, default=True)
    enable_web_search = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    # Relations
    default_model = db.relationship("LLMModel", foreign_keys=[default_model_id])
    mcp_tools = db.relationship("MCPTool", secondary=agent_mcp_tools, backref="agents")
    api_endpoints = db.relationship("APIEndpoint", secondary=agent_api_endpoints, backref="agents")
    skills = db.relationship("Skill", secondary=agent_skills, backref="agents")
    knowledge_bases = db.relationship("KnowledgeBase", secondary=agent_knowledge_bases, backref="agents")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "is_active": self.is_active,
            "allowed_roles": self.allowed_roles,
            "max_iterations": self.max_iterations,
            "temperature": self.temperature,
            "enable_sandbox": self.enable_sandbox,
            "enable_file_upload": self.enable_file_upload,
            "enable_web_search": self.enable_web_search,
        }

    def __repr__(self):
        return f"<AgentConfig {self.name}>"
