# 插件管理相关函数
import zipfile
import os
import tempfile
import json
import shutil
import re
from flask import abort, current_app, request, jsonify
from app.plugins import enable_plugin
from app.extensions.init_sqlalchemy import db
from app.models import Setting
from functools import wraps


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            abort(403)
        return f(*args, **kwargs)

    return wrapper
    

def validate_plugin_zip(zip_path):
    """
    验证插件ZIP文件是否符合要求
    
    参数:
        zip_path: ZIP文件路径
        
    返回:
        (success, message, plugin_info)
        success: 布尔值，表示验证是否通过
        message: 验证结果消息
        plugin_info: 插件信息字典（如果验证通过）
    """
    
    try:
        # 检查是否为有效的ZIP文件
        if not zipfile.is_zipfile(zip_path):
            return False, "文件不是有效的ZIP格式", None
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 获取ZIP文件中的所有文件
            file_list = zip_ref.namelist()
            
            # 检查是否包含 __init__.json 文件
            init_json_files = [f for f in file_list if f.endswith('__init__.json')]
            if not init_json_files:
                return False, "ZIP文件中缺少 __init__.json 文件", None
            
            # 读取第一个 __init__.json 文件
            init_json_path = init_json_files[0]
            try:
                with zip_ref.open(init_json_path) as f:
                    plugin_info = json.loads(f.read().decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                return False, f"无法解析 __init__.json 文件: {str(e)}", None
            
            # 检查必需的字段
            required_fields = ['plugin_name', 'plugin_version', 'plugin_description']
            for field in required_fields:
                if field not in plugin_info:
                    return False, f"__init__.json 中缺少必需的字段: {field}", None
            
            plugin_name = plugin_info['plugin_name']
            
            # 检查插件名称是否合法（允许字母、数字、下划线、连字符、点号）
            # 有效的Python包名：可以包含字母、数字、下划线、连字符，但通常建议使用小写字母和下划线
            # 我们放宽限制，允许连字符和点号，但必须以字母开头
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_\-\.]*$', plugin_name):
                return False, "插件名称只能包含字母、数字、下划线、连字符(-)和点号(.)，且必须以字母开头", None
            
            # 检查是否为系统保留名称（基础插件）
            core_plugins = current_app.config.get('CORE_PLUGINS', [])
            if plugin_name in core_plugins:
                return False, f"插件名称 '{plugin_name}' 是系统保留名称，请使用其他名称", None
            
            # 检查插件文件夹结构
            # 插件应该在一个以插件名称命名的文件夹中
            expected_folder = f"{plugin_name}/"
            has_correct_structure = False
            
            for file_path in file_list:
                if file_path.startswith(expected_folder):
                    has_correct_structure = True
                    break
                elif '/' not in file_path:
                    # 如果文件不在任何文件夹中，使用插件名称作为文件夹
                    has_correct_structure = True
                    break
            
            if not has_correct_structure:
                return False, f"ZIP文件应该包含一个名为 '{plugin_name}' 的文件夹，或者所有文件都在根目录", None
            
            # 检查是否包含 main.py 文件
            main_py_files = [f for f in file_list if f.endswith('main.py')]
            if not main_py_files:
                return False, "ZIP文件中缺少 main.py 文件", None
            
            # 检查是否包含 __init__.py 文件
            init_py_files = [f for f in file_list if f.endswith('__init__.py')]
            if not init_py_files:
                return False, "ZIP文件中缺少 __init__.py 文件", None
            
            # 检查插件是否已存在
            # 正确的插件目录路径：noteapp/plugins
            current_file = __file__
            noteapp_dir = os.path.dirname(os.path.dirname(current_file))  # app目录
            plugins_dir = os.path.join(noteapp_dir, 'plugins')
            plugin_dir = os.path.join(plugins_dir, plugin_name)
            if os.path.exists(plugin_dir):
                return False, f"插件 '{plugin_name}' 已存在", None
            
            return True, "插件验证通过", plugin_info
            
    except Exception as e:
        return False, f"验证插件时发生错误: {str(e)}", None


def extract_and_enable_plugin(zip_path, plugin_info):
    """
    解压并启用插件
    
    参数:
        zip_path: ZIP文件路径
        plugin_info: 插件信息字典
        
    返回:
        (success, message)
    """

    
    try:
        plugin_name = plugin_info['plugin_name']
        # 正确的插件目录路径：noteapp/plugins
        current_file = __file__
        noteapp_dir = os.path.dirname(os.path.dirname(current_file))  # app目录
        plugins_dir = os.path.join(noteapp_dir, 'plugins')
        plugin_dir = os.path.join(plugins_dir, plugin_name)
        
        # 创建插件目录
        os.makedirs(plugin_dir, exist_ok=True)
        
        # 解压ZIP文件
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # 获取所有文件
            file_list = zip_ref.namelist()
            
            # 检查文件结构，确定是否需要创建插件名称文件夹
            has_plugin_folder = any(f.startswith(f"{plugin_name}/") for f in file_list)
            
            if has_plugin_folder:
                # 如果ZIP文件中已经包含插件名称文件夹，直接解压到插件目录
                for file_path in file_list:
                    if file_path.startswith(f"{plugin_name}/"):
                        # 移除插件名称前缀
                        relative_path = file_path[len(f"{plugin_name}/"):]
                        if relative_path:  # 跳过空路径（文件夹本身）
                            target_path = os.path.join(plugin_dir, relative_path)
                            # 确保目标目录存在
                            os.makedirs(os.path.dirname(target_path), exist_ok=True)
                            # 解压文件
                            with zip_ref.open(file_path) as source, open(target_path, 'wb') as target:
                                target.write(source.read())
            else:
                # 如果ZIP文件中没有插件名称文件夹，直接解压所有文件到插件目录
                zip_ref.extractall(plugin_dir)
        
        # 验证解压后的文件
        required_files = ['__init__.json', 'main.py', '__init__.py']
        for file in required_files:
            file_path = os.path.join(plugin_dir, file)
            if not os.path.exists(file_path):
                # 尝试在子目录中查找
                found = False
                for root, dirs, files in os.walk(plugin_dir):
                    if file in files:
                        found = True
                        break
                if not found:
                    # 清理已解压的文件
                    shutil.rmtree(plugin_dir, ignore_errors=True)
                    return False, f"解压后缺少必需的文件: {file}"
        
        # 添加到启用的插件列表 - 使用数据库函数
        if enable_plugin(plugin_name):
            return True, f"插件 '{plugin_name}' 已成功安装并启用"
        else:
            # 插件可能已经启用，但安装成功
            return True, f"插件 '{plugin_name}' 已成功安装（已启用）"
        
    except Exception as e:
        # 清理已解压的文件
        current_file = __file__
        noteapp_dir = os.path.dirname(os.path.dirname(current_file))
        plugin_dir = os.path.join(noteapp_dir, 'plugins', plugin_info['plugin_name'])
        shutil.rmtree(plugin_dir, ignore_errors=True)
        return False, f"安装插件时发生错误: {str(e)}"


def is_core_plugin(plugin_name):
    """检查插件是否为基础插件"""
    core_plugins = current_app.config.get('CORE_PLUGINS', [])
    return plugin_name in core_plugins


def get_plugin_info(plugin_name):
    """获取插件信息"""
    # 正确的插件目录路径：app/plugins
    current_file = __file__
    # 获取app目录的路径
    noteapp_dir = os.path.dirname(os.path.dirname(current_file))  # app目录
    plugins_dir = os.path.join(noteapp_dir, 'plugins')
    plugin_dir = os.path.join(plugins_dir, plugin_name)
    init_json_path = os.path.join(plugin_dir, '__init__.json')
    
    if not os.path.exists(init_json_path):
        return None
    
    try:
        with open(init_json_path, 'r', encoding='utf-8') as f:
            plugin_info = json.load(f)
            plugin_info['is_core'] = is_core_plugin(plugin_name)
            plugin_info['is_enabled'] = plugin_name in current_app.config.get('PLUGIN_ENABLE_FOLDERS', [])
            plugin_info['has_main_py'] = os.path.exists(os.path.join(plugin_dir, 'main.py'))
            return plugin_info
    except Exception as e:
        current_app.logger.error(f"读取插件信息失败 {plugin_name}: {str(e)}")
        return None

def require_plugin(blueprint_name):
    """
    简化的插件启用检查装饰器
    需要在Flask应用上下文中使用
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 这里假设有一个helper函数来检查插件状态
            if not is_plugin_enabled(blueprint_name):
                # 如果是API请求，返回JSON
                if request.path.startswith('/api/'):
                    return jsonify({
                        'success': False,
                        'error': 'Plugin not enabled',
                        'message': f'The plugin {blueprint_name} is not enabled.'
                    }), 403
                # 否则返回错误页面
                abort(403, description=f"插件 {blueprint_name} 未启用")
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# 辅助函数：检查插件是否启用
def is_plugin_enabled(blueprint_name):
    """
    检查指定的blueprint是否启用
    
    Returns:
        bool: 如果启用返回True，否则返回False
    """
    
    try:
        setting = Setting.query.filter_by(key='PLUGIN_ENABLE_FOLDERS').first()
        if not setting:
            return False
        
        # 支持多种存储格式：逗号分隔、JSON数组、Python列表字符串
        value = setting.value
        
        # 尝试解析为JSON
        try:
            enabled_plugins = json.loads(value)
        except json.JSONDecodeError:
            # 如果不是JSON，尝试按逗号分割
            enabled_plugins = [p.strip() for p in value.split(',')]
        
        return blueprint_name in enabled_plugins
    except Exception as e:
        current_app.logger.error(f"检查插件状态失败: {str(e)}")
        return False