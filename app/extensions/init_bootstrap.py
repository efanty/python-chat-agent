from flask import Flask
from flask_bootstrap import Bootstrap4

bootstrap = Bootstrap4()
def init_bootstrap(app: Flask):
    bootstrap.init_app(app)