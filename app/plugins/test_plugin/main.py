from flask import Blueprint, render_template
from app.utils.plugin_utils import require_plugin

bp = Blueprint('test_plugin', __name__, template_folder='templates', url_prefix='/test_plugin')

blueprint_name = "test_plugin"

@bp.route('/', strict_slashes=False)
@require_plugin(blueprint_name)
def index():
    return "测试插件已加载！!"

