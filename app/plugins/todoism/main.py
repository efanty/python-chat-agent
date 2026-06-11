# -*- coding: utf-8 -*-

from flask import render_template, request, Blueprint, jsonify, session, redirect,url_for
from flask_login import current_user, login_required
import datetime
from app.extensions.init_sqlalchemy import db
from app.models.todo import Todo
from sqlalchemy import or_, and_
from sqlalchemy import func as sa_func

bp = Blueprint('todoism', __name__, static_folder='static', template_folder='templates', url_prefix="/todoism")

@bp.route('/', methods=['GET','POST'])
@bp.route('/app', methods=['GET','POST'])
@login_required
def app():
    date = datetime.date.today().strftime("%Y-%m-%d")
    # session['date'] = date
    if request.method == 'POST':
        # Try to get JSON data, but don't fail if Content-Type is not application/json
        data = request.get_json(silent=True)
        if data and 'search-item-timestamp' in data:
            date = data['search-item-timestamp']
            session['date'] = date
            # print(session['date'])
    
    # 优先级: ?date= 查询参数 > session > 今天
    date = request.args.get('date') or session.get('date', date)

    items = Todo.query.with_parent(current_user).filter(sa_func.date(Todo.timestamp) == date).all()
    all_count = Todo.query.with_parent(current_user).filter(sa_func.date(Todo.timestamp) == date).count()
    active_count = Todo.query.with_parent(current_user).filter(and_(Todo.done==False, sa_func.date(Todo.timestamp) == date)).count()
    completed_count = Todo.query.with_parent(current_user).filter(and_(Todo.done==True, sa_func.date(Todo.timestamp) == date)).count()
    return render_template('_app.html', items=items, all_count=all_count, active_count=active_count, completed_count=completed_count, date=date, now=datetime.datetime.now())

@bp.route('/actives', methods=['GET'])
@login_required
def actives():

    items = Todo.query.with_parent(current_user).all()
    all_count = Todo.query.with_parent(current_user).count()
    active_count = Todo.query.with_parent(current_user).filter_by(done=False).count()
    completed_count = Todo.query.with_parent(current_user).filter_by(done=True).count()
    return render_template('_actives.html', items=items, all_count=all_count, active_count=active_count, completed_count=completed_count, now=datetime.datetime.now())


@bp.route('/items/new', methods=['POST'])
@login_required
def new_item():
    # Use date from session if available, else today
    date = session.get('date', datetime.date.today().strftime("%Y-%m-%d"))
    data = request.get_json(silent=True)
    print(f"[DEBUG] new_item data: {data}, date={date}")  # Debug
    if data is None or 'body' not in data or data['body'].strip() == '':
        return jsonify(message='无效的项目内容。'), 400
    # 转换字符串日期为 datetime 对象（timestamp 字段是 db.DateTime）
    try:
        ts = datetime.datetime.strptime(date, "%Y-%m-%d")
    except (ValueError, TypeError):
        ts = datetime.datetime.now()
    due_date_str = data.get('due_date', '')
    due_date_val = None
    if due_date_str:
        try:
            due_date_val = datetime.datetime.strptime(due_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    item = Todo(body=data['body'], author=current_user._get_current_object(), timestamp=ts, due_date=due_date_val)
    db.session.add(item)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(message='保存失败，请重试'), 500
    return jsonify(html=render_template('_item.html', item=item, now=datetime.datetime.now()), message='+1')


@bp.route('/item/<int:item_id>/edit', methods=['PUT', 'POST'])
@login_required
def edit_item(item_id):
    # 清除可能残留的 session 挂起状态
    db.session.rollback()
    try:
        item = Todo.query.get_or_404(item_id)
        if current_user != item.author:
            return jsonify(message='权限不足。'), 403

        data = request.get_json(silent=True)
        if data is None or 'body' not in data or data['body'].strip() == '':
            return jsonify(message='无效的项目内容。'), 400
        item.body = data['body']
        if 'due_date' in data:
            dd_str = data['due_date']
            if dd_str:
                try:
                    item.due_date = datetime.datetime.strptime(dd_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
            else:
                item.due_date = None
        db.session.commit()
        return jsonify(message='项目已更新。')
    except Exception as e:
        db.session.rollback()
        return jsonify(message='服务器内部错误。'), 500


@bp.route('/item/<int:item_id>/toggle', methods=['PATCH', 'POST'])
@login_required
def toggle_item(item_id):
    db.session.rollback()
    item = Todo.query.get_or_404(item_id)
    if current_user != item.author:
        return jsonify(message='权限不足。'), 403

    item.done = not item.done
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(message='操作失败'), 500
    return jsonify(message='项目状态已切换。')


@bp.route('/item/<int:item_id>/delete', methods=['DELETE', 'POST'])
@login_required
def delete_item(item_id):
    db.session.rollback()
    item = Todo.query.get_or_404(item_id)
    if current_user != item.author:
        return jsonify(message='权限不足。'), 403

    db.session.delete(item)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify(message='删除失败'), 500
    return jsonify(message='项目已删除。')


@bp.route('/item/clear', methods=['DELETE'])
@login_required
def clear_items():
    items = Todo.query.with_parent(current_user).filter_by(done=True).all()
    for item in items:
        db.session.delete(item)
    db.session.commit()
    return jsonify(message='全部清除！')


@bp.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    active_count = []
    completed_count = []
    name = ""
    
    if request.method == 'GET':
        # GET method: get search term from query parameter 'q'
        name = request.args.get('q', '').strip()
    elif request.method == 'POST':
        # POST method (keep for compatibility)
        data = request.get_json(silent=True)
        if data is None or 'body' not in data or data['body'].strip() == '':
            return render_template('_search_result.html', items=None, all_count=0, active_count=0, completed_count=0, now=datetime.datetime.now())
        name = data['body']
    
    # If name is empty, return empty results (no items)
    if name == "":
        return render_template('_search_result.html', items=None, all_count=0, active_count=0, completed_count=0, now=datetime.datetime.now())
    
    # Debug: print search term
    print(f"[DEBUG] search term: '{name}'")
    
    # Execute query and convert to list to avoid consuming the query
    items_query = Todo.query.with_parent(current_user).filter(Todo.body.like('%%%s%%' % name)).order_by(Todo.timestamp.desc())
    items = items_query.all()  # Convert to list
    
    print(f"[DEBUG] found {len(items)} items")
    
    for item in items:
        if item.done == True:
            completed_count.append(item)
        else:
            active_count.append(item)
    all_count = active_count + completed_count
    
    return render_template('_search_result.html', items=items, all_count=len(all_count), active_count=len(active_count), completed_count=len(completed_count), now=datetime.datetime.now())
