from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class KnowledgeBase(db.Model):
    __tablename__ = "knowledge_bases"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    collection_name = db.Column(db.String(128), unique=True, nullable=False)
    embedding_model_id = db.Column(db.Integer, db.ForeignKey("llm_models.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    document_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    embedding_model = db.relationship("LLMModel", foreign_keys=[embedding_model_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "collection_name": self.collection_name,
            "document_count": self.document_count,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<KnowledgeBase {self.name}>"
