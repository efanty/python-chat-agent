from app.utils.time_utils import beijing_now
from app.extensions.init_sqlalchemy import db

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mold_number = db.Column(db.Text)
    body = db.Column(db.Text)
    done = db.Column(db.Boolean, default=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    author = db.relationship('User', back_populates='items')
    due_date = db.Column(db.Date, nullable=True)
    timestamp = db.Column(db.DateTime, default=lambda: beijing_now())