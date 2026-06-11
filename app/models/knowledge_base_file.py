from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class KnowledgeBaseFile(db.Model):
    __tablename__ = "knowledge_base_files"

    id = db.Column(db.Integer, primary_key=True)
    kb_id = db.Column(db.Integer, db.ForeignKey("knowledge_bases.id"), nullable=False)
    filename = db.Column(db.String(256), nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    file_size = db.Column(db.Integer, default=0)
    chunk_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())

    knowledge_base = db.relationship(
        "KnowledgeBase",
        backref=db.backref("files", lazy="dynamic", cascade="all, delete-orphan"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "kb_id": self.kb_id,
            "filename": self.filename,
            "file_size": self.file_size,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def file_size_display(self):
        """Return human-readable file size."""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / 1024 / 1024:.1f} MB"
