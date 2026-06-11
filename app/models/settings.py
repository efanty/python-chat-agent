from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db


class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=lambda: beijing_now(),
                           onupdate=lambda: beijing_now())

    @staticmethod
    def get(key, default=None):
        """Get a setting value by key."""
        s = Setting.query.filter_by(key=key).first()
        return s.value if s else default

    @staticmethod
    def set(key, value, description=None):
        """Set a setting value."""
        s = Setting.query.filter_by(key=key).first()
        if s:
            s.value = value
            if description:
                s.description = description
        else:
            s = Setting(key=key, value=value, description=description)
            db.session.add(s)
        db.session.commit()
        return s

    @staticmethod
    def get_all_dict():
        """Get all settings as a dict."""
        settings = Setting.query.all()
        return {s.key: s.value for s in settings}

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"
