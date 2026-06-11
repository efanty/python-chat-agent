import os
import tempfile
from flask import render_template, Blueprint, url_for, flash, request, redirect, current_app, jsonify, send_file
import io
from flask_login import login_required
from app.extensions.init_loginmanager import admin_required
from app.utils.plugin_utils import validate_plugin_zip, extract_and_enable_plugin, is_core_plugin, get_plugin_info
import zipfile
import shutil
from werkzeug.utils import secure_filename
import json
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int


plugin_manager_bp = Blueprint('plugin_manager', __name__, template_folder='templates', url_prefix='/plugin_manager')


@plugin_manager_bp.route('/', strict_slashes=False, methods=['GET', 'POST'])
@login_required
@admin_required
def index():
    """插件管理主页面"""
    # 获取所有插件信息
    plugins_info = []
    core_plugins = current_app.config.get('CORE_PLUGINS', [])
    plugin_folders = current_app.config.get('PLUGIN_ENABLE_FOLDERS', [])
    
    # 获取基础插件信息
    for plugin_name in core_plugins:
        plugin_info = get_plugin_info(plugin_name)
        if plugin_info:
            plugin_info['is_core'] = True
            plugin_info['is_enabled'] = True  # 基础插件始终启用
            plugins_info.append(plugin_info)
    
    # 获取用户插件信息（排除基础插件）
    # 正确的插件目录路径：noteapp/plugins
    current_dir = os.path.dirname(__file__)  # noteapp/plugins/plugin_manager
    plugins_dir = os.path.dirname(current_dir)  # noteapp/plugins
    
    if os.path.exists(plugins_dir):
        for item in os.listdir(plugins_dir):
            plugin_dir = os.path.join(plugins_dir, item)
            if os.path.isdir(plugin_dir) and item not in core_plugins:
                plugin_info = get_plugin_info(item)
                if plugin_info:
                    plugin_info['is_core'] = False
                    plugin_info['is_enabled'] = item in plugin_folders
                    plugins_info.append(plugin_info)
    
    if request.method == "POST":
        # 处理插件上传
        if 'file' not in request.files:
            flash('请选择要上传的文件', 'danger')
            return render_template('plugin.html', plugins=plugins_info)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('请选择要上传的文件', 'danger')
            return render_template('plugin.html', plugins=plugins_info)
        
        # 检查文件扩展名
        if not file.filename.lower().endswith('.zip'):
            flash('只支持ZIP格式的文件', 'danger')
            return render_template('plugin.html', plugins=plugins_info)
        
        # 创建临时文件保存上传的ZIP
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            file.save(tmp_file.name)
            temp_zip_path = tmp_file.name
        
        try:
            # 验证插件ZIP文件
            success, message, plugin_info = validate_plugin_zip(temp_zip_path)
            
            if not success:
                flash(f'插件验证失败: {message}', 'danger')
                return render_template('plugin.html', plugins=plugins_info)
            
            # 解压并启用插件
            success, message = extract_and_enable_plugin(temp_zip_path, plugin_info)
            
            if success:
                flash(f'插件安装成功: {message}', 'success')
                # 重新加载页面以显示新插件
                return redirect(url_for('plugin_manager.index'))
            else:
                flash(f'插件安装失败: {message}', 'danger')
                return render_template('plugin.html', plugins=plugins_info)
                
        except Exception as e:
            flash(f'处理插件时发生错误: {str(e)}', 'danger')
            return render_template('plugin.html', plugins=plugins_info)
        finally:
            # 清理临时文件
            if os.path.exists(temp_zip_path):
                os.unlink(temp_zip_path)
    
    # Pagination for plugins (file-system based list)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    total = len(plugins_info)
    offset = (page - 1) * per_page
    page_plugins = plugins_info[offset:offset + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)
    
    return render_template('plugin.html', plugins=page_plugins, total=total, page=page, per_page=per_page, total_pages=total_pages)


@plugin_manager_bp.route('/remove', strict_slashes=False, methods=['POST'])
@login_required
@admin_required
def remove():
    """删除插件"""
    plugin_name = request.form.get('plug', '').strip()
    
    if not plugin_name:
        flash('请指定要删除的插件', 'danger')
        return redirect(url_for('plugin_manager.index'))
    
    # 检查是否为基础插件
    if is_core_plugin(plugin_name):
        flash(f'基础插件 "{plugin_name}" 不可删除', 'danger')
        return redirect(url_for('plugin_manager.index'))
    
    # 检查插件是否存在 - 使用正确的路径
    current_dir = os.path.dirname(__file__)  # noteapp/plugins/plugin_manager
    plugins_dir = os.path.dirname(current_dir)  # noteapp/plugins
    plugin_dir = os.path.join(plugins_dir, plugin_name)
    
    if not os.path.exists(plugin_dir):
        flash(f'插件 "{plugin_name}" 不存在', 'danger')
        return redirect(url_for('plugin_manager.index'))
    
    try:
        # 从启用的插件列表中移除（使用数据库函数）
        from app.plugins import disable_plugin
        success, message = disable_plugin(plugin_name)
        
        # 删除插件目录
        shutil.rmtree(plugin_dir)
        
        flash(f'插件 "{plugin_name}" 已成功删除', 'success')
        
    except Exception as e:
        flash(f'删除插件时发生错误: {str(e)}', 'danger')
    
    return redirect(url_for('plugin_manager.index'))


@plugin_manager_bp.route('/toggle', strict_slashes=False, methods=['POST'])
@login_required
@admin_required
def toggle():
    """启用/停用插件"""
    plugin_name = request.form.get('plug', '').strip()
    action = request.form.get('action', '').strip()  # 'enable' 或 'disable'
    
    if not plugin_name or not action:
        return jsonify({'success': False, 'message': '参数错误'})
    
    # 检查是否为基础插件
    if is_core_plugin(plugin_name):
        return jsonify({'success': False, 'message': f'基础插件 "{plugin_name}" 不可停用'})
    
    # 检查插件是否存在 - 使用正确的路径
    current_dir = os.path.dirname(__file__)  # noteapp/plugins/plugin_manager
    plugins_dir = os.path.dirname(current_dir)  # noteapp/plugins
    plugin_dir = os.path.join(plugins_dir, plugin_name)
    
    if not os.path.exists(plugin_dir):
        return jsonify({'success': False, 'message': f'插件 "{plugin_name}" 不存在'})
    
    try:
        from app.plugins import enable_plugin, disable_plugin
        
        if action == 'enable':
            if enable_plugin(plugin_name):
                return jsonify({'success': True, 'message': f'插件 "{plugin_name}" 已启用'})
            else:
                return jsonify({'success': True, 'message': f'插件 "{plugin_name}" 已经是启用状态'})
        
        elif action == 'disable':
            success, message = disable_plugin(plugin_name)
            if success:
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': message})
        
        else:
            return jsonify({'success': False, 'message': '无效的操作'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'操作失败: {str(e)}'})


@plugin_manager_bp.route('/download/<plugin_name>', strict_slashes=False)
@login_required
@admin_required
def download_plugin(plugin_name):
    """打包下载插件目录为 ZIP 文件。"""
    current_dir = os.path.dirname(__file__)
    plugins_dir = os.path.dirname(current_dir)
    plugin_dir = os.path.join(plugins_dir, plugin_name)
    if not os.path.isdir(plugin_dir):
        flash(f'插件目录 "{plugin_name}" 不存在', 'danger')
        return redirect(url_for('plugin_manager.index'))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(plugin_dir):
            for fn in files:
                fpath = os.path.join(root, fn)
                arcname = os.path.relpath(fpath, plugins_dir)
                zf.write(fpath, arcname)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{plugin_name}.zip'
    )


@plugin_manager_bp.route('/info/<plugin_name>', strict_slashes=False)
@login_required
@admin_required
def plugin_info(plugin_name):
    """获取插件详细信息"""
    plugin_info_data = get_plugin_info(plugin_name)
    
    if not plugin_info_data:
        return jsonify({'success': False, 'message': '插件不存在'})
    
    # 获取插件文件列表 - 使用正确的路径
    # __file__ 是 noteapp/plugins/plugin_manager/main.py
    # 我们需要获取 noteapp/plugins 目录
    current_dir = os.path.dirname(__file__)  # noteapp/plugins/plugin_manager
    plugins_dir = os.path.dirname(current_dir)  # noteapp/plugins
    plugin_dir = os.path.join(plugins_dir, plugin_name)
    
    file_list = []
    if os.path.exists(plugin_dir):
        for root, dirs, files in os.walk(plugin_dir):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, plugin_dir)
                # 跳过 __pycache__ 目录和 .pyc 文件
                if '__pycache__' not in relative_path and not relative_path.endswith('.pyc'):
                    file_list.append(relative_path)
    
    plugin_info_data['files'] = sorted(file_list)
    
    return jsonify({'success': True, 'plugin': plugin_info_data})
