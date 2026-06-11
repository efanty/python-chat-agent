import pyotp
import qrcode
import base64
from io import BytesIO
from functools import lru_cache
from app.utils.time_utils import beijing_now
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions.init_sqlalchemy import db
from app.extensions.init_loginmanager import login_manager
from app.models.settings import Setting



class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nickname = db.Column(db.String(64), nullable=True)
    email = db.Column(db.String(128), unique=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user", comment='admin,vip,user')  # user, vip, admin
    is_active = db.Column(db.Boolean, default=True)
    totp_enabled = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(64), nullable=True)
    totp_required = db.Column(db.Boolean, default=False)  # Admin override: force TOTP
    avatar = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: beijing_now())
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())
    last_login = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)
    # 账号锁定
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    # Preferences
    preferred_model_id = db.Column(db.Integer, db.ForeignKey("llm_models.id"), nullable=True)
    preferred_agent_id = db.Column(db.Integer, db.ForeignKey("agent_configs.id"), nullable=True)

    # Relations
    conversations = db.relationship("Conversation", backref="user", lazy="dynamic",
                                   cascade="all, delete-orphan")
    memories = db.relationship("UserMemory", backref="user", lazy="dynamic",
                              cascade="all, delete-orphan")

    items = db.relationship('Todo', back_populates='author', cascade='all')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_totp_secret(self):
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret

    def get_totp_uri(self):
        if not self.totp_secret:
            return None
        return pyotp.totp.TOTP(self.totp_secret).provisioning_uri(
            name=self.email, issuer_name="DeepAgent Chat"
        )

    def get_totp_qrcode(self):
        uri = self.get_totp_uri()
        if not uri:
            return None
        img = qrcode.make(uri)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def verify_totp(self, code):
        if not self.totp_secret:
            return False
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(code)

    def is_totp_required(self):
        """Check if TOTP is required for this user."""
        global_required = Setting.get("totp_global_required", "false") == "true"
        return global_required or self.totp_required or self.totp_enabled

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_vip(self):
        return self.role in ("vip", "admin")

    @property
    def role_name(self):
        name = ''
        if self.role == "admin":
            name = '管理员'
        elif self.role == "VIP":
            name = 'VIP会员'
        elif self.role == "user":
            name = '普通会员'
        else:
            name = "未知"
        return name

    def can_use_model(self, model):
        """Check if user can use a specific model."""
        if model.allowed_roles == "all":
            return True
        allowed = model.allowed_roles.split(",") if model.allowed_roles else ["all"]
        return self.role in allowed

    def can_use_agent(self, agent):
        """Check if user can use a specific agent."""
        if agent.allowed_roles == "all":
            return True
        allowed = agent.allowed_roles.split(",") if agent.allowed_roles else ["all"]
        return self.role in allowed

    def to_dict(self, include_email=False):
        """Return user info as dict, password excluded."""
        data = {
            "id": self.id,
            "username": self.username,
            "nickname": self.nickname,
            "role": self.role,
            "is_active": self.is_active,
            "avatar": self.avatar,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }
        if include_email:
            data["email"] = self.email
            data["email_verified"] = self.email_verified
        return data

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
@lru_cache(maxsize=256)
def load_user(user_id):
    return User.query.get(int(user_id))

