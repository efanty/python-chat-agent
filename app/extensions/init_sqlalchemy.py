import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from app.utils.settings import coerce_setting_value

db = SQLAlchemy()

def load_settings_from_db(app: Flask):
    """从数据库加载设置到应用配置中"""
    with app.app_context():
        from app.models import Setting
        try:
            settings = Setting.query.all()
            for setting in settings:
                value = coerce_setting_value(setting.key, setting.value)
                app.config[setting.key] = value
                
                # 特殊处理：将 BOOTSWATCH_THEMES 的值也设置到 BOOTSTRAP_BOOTSWATCH_THEME
                if setting.key == 'BOOTSWATCH_THEMES' and value:
                    app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = value
                
                app.logger.info(f"Loaded setting from DB: {setting.key} = {value}")
            
            # 确保 BOOTSTRAP_BOOTSWATCH_THEME 被正确设置
            if 'BOOTSTRAP_BOOTSWATCH_THEME' not in app.config or not app.config['BOOTSTRAP_BOOTSWATCH_THEME']:
                if 'BOOTSWATCH_THEMES' in app.config and app.config['BOOTSWATCH_THEMES']:
                    app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = app.config['BOOTSWATCH_THEMES']
                else:
                    app.config['BOOTSTRAP_BOOTSWATCH_THEME'] = 'cosmo'
            
            app.logger.info(f"Final BOOTSTRAP_BOOTSWATCH_THEME: {app.config['BOOTSTRAP_BOOTSWATCH_THEME']}")
                    
        except Exception as e:
            app.logger.error(f"Failed to load settings from database: {str(e)}")


def _migrate_users_table():
    """迁移 users 表：添加 login_attempts 和 locked_until 列（如不存在）"""
    from sqlalchemy import inspect, text
    from app.extensions.init_sqlalchemy import db

    inspector = inspect(db.engine)
    columns = [c["name"] for c in inspector.get_columns("users")]

    with db.engine.connect() as conn:
        if "login_attempts" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN login_attempts INTEGER DEFAULT 0"))
        if "locked_until" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN locked_until DATETIME"))
        conn.commit()


def _migrate_mcp_tools_table():
    """迁移 mcp_tools 表：添加 transport 列（如不存在）"""
    from sqlalchemy import inspect, text
    from app.extensions.init_sqlalchemy import db

    inspector = inspect(db.engine)
    try:
        columns = [c["name"] for c in inspector.get_columns("mcp_tools")]
        with db.engine.connect() as conn:
            if "transport" not in columns:
                conn.execute(text("ALTER TABLE mcp_tools ADD COLUMN transport VARCHAR(32) DEFAULT 'stdio'"))
                conn.commit()
    except Exception:
        pass  # Table may not exist yet


def init_databases(app: Flask):
    db.init_app(app)
    # 创建所有表（如不存在）
    with app.app_context():
        db.create_all()
        # 迁移 users 表（添加新列）
        try:
            _migrate_users_table()
        except Exception as e:
            app.logger.error(f"数据库迁移失败: {str(e)}")
        # 迁移 mcp_tools 表（添加 transport 列）
        try:
            _migrate_mcp_tools_table()
        except Exception as e:
            app.logger.error(f"MCP工具表迁移失败: {str(e)}")
    # 在应用启动时加载数据库设置
    load_settings_from_db(app)
