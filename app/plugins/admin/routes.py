"""Admin blueprint - module loader.
Routes register onto admin_bp when submodules are imported.
"""
from . import dashboard  # noqa: F401 — register routes on bp
from . import agents
from . import users
from . import models
from . import tools
from . import api_endpoints
from . import skills
from . import kb
from . import settings
from . import search
from . import security  # noqa: F401 — IP blocklist management
