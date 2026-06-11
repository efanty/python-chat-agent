from flask import Flask
from .init_sqlalchemy import init_databases
from .init_loginmanager import init_loginManager
from .init_csrf import init_csrf
from .init_bootstrap import init_bootstrap
from .init_error_views import init_errors
from .init_limiter import init_limiter
from .init_logging import init_logging
from .init_mail import init_mail
from .init_migrate import init_migrate
from .init_security import init_security


def init_extensions(app: Flask) -> None:
    init_loginManager(app)
    init_databases(app)
    init_csrf(app)
    init_bootstrap(app)
    init_errors(app)
    init_limiter(app)
    init_logging(app)
    init_mail(app)
    init_migrate(app)
    init_security(app)
    