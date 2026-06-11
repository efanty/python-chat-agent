from flask import Blueprint, render_template

bp = Blueprint('test_plugin', __name__, template_folder='templates', url_prefix='/test_plugin')

@bp.route('/', strict_slashes=False)
def index():
    return "测试插件已加载！"

