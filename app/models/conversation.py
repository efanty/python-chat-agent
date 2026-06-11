from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(256), default="新对话")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_configs.id"), nullable=True)
    model_id = db.Column(db.Integer, db.ForeignKey("llm_models.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    # Relations
    messages = db.relationship("Message", backref="conversation", lazy="dynamic",
                              cascade="all, delete-orphan", order_by="Message.created_at")
    agent = db.relationship("AgentConfig", foreign_keys=[agent_id])
    model = db.relationship("LLMModel", foreign_keys=[model_id])

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.messages.count(),
        }

    def __repr__(self):
        return f"<Conversation {self.id}: {self.title}>"


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversations.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user, assistant, system, tool
    content = db.Column(db.Text, nullable=True)
    content_type = db.Column(db.String(32), default="text")  # text, image, file
    file_path = db.Column(db.String(512), nullable=True)
    file_name = db.Column(db.String(256), nullable=True)
    token_count = db.Column(db.Integer, default=0)
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cost = db.Column(db.Float, default=0.0)
    model_id_str = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "content_type": self.content_type,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "token_count": self.token_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "model_id_str": self.model_id_str,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Message {self.id}: {self.role}>"
