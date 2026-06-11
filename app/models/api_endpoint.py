from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db
from app.utils.crypto import EncryptedString


class APIEndpoint(db.Model):
    __tablename__ = "api_endpoints"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    url = db.Column(db.String(512), nullable=False)
    method = db.Column(db.String(10), default="GET")  # GET, POST, PUT, DELETE
    headers = db.Column(db.Text, nullable=True)  # JSON string
    auth_type = db.Column(db.String(32), default="none")  # none, api_key, bearer, basic
    auth_value = db.Column(EncryptedString(512), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "method": self.method,
            "is_active": self.is_active,
        }

    def __repr__(self):
        return f"<APIEndpoint {self.name}>"
