from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class UserMemory(db.Model):
    __tablename__ = "user_memories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    key = db.Column(db.String(128), nullable=False)
    value = db.Column(db.Text, nullable=True)
    memory_type = db.Column(db.String(32), default="general")  # general, preference, fact, context
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    __table_args__ = (
        db.UniqueConstraint("user_id", "key", name="uq_user_memory_key"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "memory_type": self.memory_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<UserMemory {self.key}>"
