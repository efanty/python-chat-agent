from flask import Flask, current_app
from flask import Blueprint
import json
import os
import traceback
import importlib
from app.extensions.init_sqlalchemy import db
from app.models.settings import Setting

plugin_bp = Blueprint('plugin', __name__, url_prefix='/plugin')
PLUGIN_ENABLE_FOLDERS = []
_registered_at_startup = set()


def register_plugin(app, plugin_folder):
    """动态注册插件蓝图（安装或启用后立即生效，无需重启）。

    导入插件模块并调用 event_init(app) 来注册蓝图。
    如果 app 已处理过第一个请求（register_blueprint 会失败），
    则直接调用 bp.register(app) 绕过注册限制。
    """
    plugin_info = {}
    try:
        with open(os.path.join(app.root_path, "plugins", plugin_folder, "__init__.json"), "r", encoding='utf-8') as f:
            plugin_info = json.loads(f.read())
        mod = importlib.import_module('app.plugins.' + plugin_folder)
        if hasattr(mod, 'event_init'):
            try:
                mod.event_init(app)
            except RuntimeError:
                # After first request, register_blueprint fails -> register bp directly
                if hasattr(mod, 'bp'):
                    mod.bp.register(app, {})
                    app.logger.info(f"Plugin registered via bp.register: {plugin_folder}")
                else:
                    raise
        print(f" * Plugin: Registered: {plugin_info.get('plugin_name', plugin_folder)} .")
    except BaseException as e:
        print(f" * Plugin: Failed to register {plugin_folder}: {e}")


def init_plugins(app: Flask):
    global PLUGIN_ENABLE_FOLDERS
    app.register_blueprint(plugin_bp)
    
    # 延迟加载插件启用状态，在第一个请求时或稍后初始化
    # 这里先使用默认配置，稍后在应用上下文中更新
    PLUGIN_ENABLE_FOLDERS = app.config.get('PLUGIN_ENABLE_FOLDERS', [])
    
    # 使用一个标志来确保只加载一次
    plugin_settings_loaded = False
    
    # 在启动时从 DB 加载完整插件列表（含离线安装的）并注册
    try:
        db_plugins = get_enabled_plugins_from_db(app)
        PLUGIN_ENABLE_FOLDERS = db_plugins
        app.config['PLUGIN_ENABLE_FOLDERS'] = db_plugins
        print(f" * Plugin: Loaded plugin settings from database: {db_plugins}")
    except Exception as e:
        print(f" * Plugin: Error loading plugin settings at startup: {e}")

    # 仅在有新插件需要注册时设置 before_request（更新 config 用）
    @app.before_request
    def load_plugin_settings():
        nonlocal plugin_settings_loaded
        if not plugin_settings_loaded:
            global PLUGIN_ENABLE_FOLDERS
            try:
                db_plugins = get_enabled_plugins_from_db(app)
                if set(db_plugins) != set(PLUGIN_ENABLE_FOLDERS):
                    PLUGIN_ENABLE_FOLDERS = db_plugins
                    app.config['PLUGIN_ENABLE_FOLDERS'] = PLUGIN_ENABLE_FOLDERS
                    print(f" * Plugin: Updated plugin settings: {PLUGIN_ENABLE_FOLDERS}")
                plugin_settings_loaded = True
            except Exception as e:
                print(f" * Plugin: Error loading plugin settings: {e}")
                plugin_settings_loaded = True
    
    # 载入插件过程
    _registered_at_startup.clear()
    for plugin_folder in PLUGIN_ENABLE_FOLDERS:
        register_plugin(app, plugin_folder)
        _registered_at_startup.add(plugin_folder)


def get_enabled_plugins_from_db(app):
    """从数据库获取启用的插件列表"""
    try:
        # 在应用上下文中操作数据库
        with app.app_context():
            # 首先确保数据库表存在
            db.create_all()
            
            # 尝试从数据库读取插件设置
            setting = Setting.query.filter_by(key='PLUGIN_ENABLE_FOLDERS').first()
            
            if setting:
                # 从数据库读取插件列表
                try:
                    plugin_list = json.loads(setting.value)
                    # 确保基础插件始终在列表中
                    core_plugins = app.config.get('CORE_PLUGINS', [])
                    for plugin in core_plugins:
                        if plugin not in plugin_list:
                            plugin_list.append(plugin)
                    return plugin_list
                except (json.JSONDecodeError, ValueError) as json_err:
                    print(f"JSON解析错误: {json_err}, 原始值: {setting.value}")
                    # 如果JSON解析失败，使用默认配置
                    pass
            
            # 如果数据库中没有设置，使用默认配置
            default_plugins = app.config.get('PLUGIN_ENABLE_FOLDERS', [])
            
            # 保存到数据库
            save_enabled_plugins_to_db(default_plugins)
            
            return default_plugins
    except Exception as e:
        # 如果出现任何错误，返回默认配置
        print(f"Error reading plugin settings from database: {e}")
        return app.config.get('PLUGIN_ENABLE_FOLDERS', [])


def save_enabled_plugins_to_db(plugin_list):
    """保存启用的插件列表到数据库"""
    try:
        # 获取当前应用
        app = current_app._get_current_object()
        
        with app.app_context():
            setting = Setting.query.filter_by(key='PLUGIN_ENABLE_FOLDERS').first()
            
            if setting:
                # 更新现有设置
                setting.value = json.dumps(plugin_list)
            else:
                # 创建新设置
                setting = Setting(key='PLUGIN_ENABLE_FOLDERS', value=json.dumps(plugin_list))
                db.session.add(setting)
            
            db.session.commit()
            return True
    except Exception as e:
        print(f"Error saving plugin settings to database: {e}")
        db.session.rollback()
        return False


def enable_plugin(plugin_name):
    """启用插件（立即生效）"""
    try:
        app = current_app._get_current_object()
        # 获取当前启用的插件列表
        plugin_list = get_enabled_plugins_from_db(app)
        
        # 如果插件不在列表中，添加它
        if plugin_name not in plugin_list:
            plugin_list.append(plugin_name)
            
            # 保存到数据库
            if save_enabled_plugins_to_db(plugin_list):
                # 更新当前应用的配置
                app.config['PLUGIN_ENABLE_FOLDERS'] = plugin_list
                # 动态注册蓝图，立即生效
                register_plugin(app, plugin_name)
                return True
        
        return False
    except Exception as e:
        print(f"Error enabling plugin {plugin_name}: {e}")
        return False


def disable_plugin(plugin_name):
    """停用插件（基础插件不能停用）"""
    try:
        # 检查是否为基础插件
        core_plugins = current_app.config.get('CORE_PLUGINS', [])
        if plugin_name in core_plugins:
            return False, "基础插件不能停用"
        
        # 获取当前启用的插件列表
        plugin_list = get_enabled_plugins_from_db(current_app._get_current_object())
        
        # 如果插件在列表中，移除它
        if plugin_name in plugin_list:
            plugin_list.remove(plugin_name)
            
            # 保存到数据库
            if save_enabled_plugins_to_db(plugin_list):
                # 更新当前应用的配置
                current_app.config['PLUGIN_ENABLE_FOLDERS'] = plugin_list
                return True, "插件已停用"
        
        return False, "插件未启用"
    except Exception as e:
        error_msg = f"Error disabling plugin {plugin_name}: {e}"
        print(error_msg)
        return False, error_msg
