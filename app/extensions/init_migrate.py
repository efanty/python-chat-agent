from flask import Flask
from flask_migrate import Migrate

migrate = Migrate()

def init_migrate(app: Flask):
    migrate.init_app(app)
    
