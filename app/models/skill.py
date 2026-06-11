from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    folder_name = db.Column(db.String(128), nullable=False)  # Folder name under skills/
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "folder_name": self.folder_name,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<Skill {self.name}>"
