from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db
from app.utils.crypto import EncryptedString


class LLMModel(db.Model):
    __tablename__ = "llm_models"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    provider = db.Column(db.String(64), nullable=False)  # openai, anthropic, deepseek, etc.
    model_type = db.Column(db.String(32), nullable=False)  # text, embedding, multimodal
    model_id = db.Column(db.String(128), nullable=False)  # e.g., gpt-4o, claude-3-5-sonnet
    api_key = db.Column(EncryptedString(512), nullable=True)
    api_base = db.Column(db.String(256), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    allowed_roles = db.Column(db.String(128), default="all")
    max_tokens = db.Column(db.Integer, default=4096)
    supports_vision = db.Column(db.Boolean, default=False)
    supports_files = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text, nullable=True)
    # Pricing: CNY per 1M tokens
    input_price = db.Column(db.Float, default=0.0)
    output_price = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "model_type": self.model_type,
            "model_id": self.model_id,
            "is_active": self.is_active,
            "allowed_roles": self.allowed_roles,
            "max_tokens": self.max_tokens,
            "supports_vision": self.supports_vision,
            "supports_files": self.supports_files,
            "description": self.description,
            "input_price": self.input_price,
            "output_price": self.output_price,
        }

    def __repr__(self):
        return f"<LLMModel {self.name}>"
