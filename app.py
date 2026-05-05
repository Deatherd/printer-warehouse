import pkgutil
import importlib
import os

if not hasattr(pkgutil, 'get_loader'):
    pkgutil.get_loader = importlib.util.find_spec

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from database import *
from models import User
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return get_user_by_id(user_id)

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('write_off'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('write_off'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Введите логин и пароль', 'error')
            return render_template('login.html')
        
        user = verify_user(username, password)
        if user:
            user_obj = User(user['id'], user['username'], user['password_hash'])
            login_user(user_obj)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('write_off'))
        else:
            flash('Неверный логин или пароль', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('write_off'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        registration_code = request.form.get('registration_code')
        
        if not username or not password:
            flash('Заполните все поля', 'error')
            return render_template('register.html')
        
        success, message = register_user(username, password, registration_code)
        if success:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('register.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password_route():
    if request.method == 'POST':
        username = request.form.get('username')
        registration_code = request.form.get('registration_code')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, registration_code, new_password, confirm_password]):
            flash('Заполните все поля', 'error')
            return render_template('reset_password.html')
        
        if new_password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('reset_password.html')
        
        if len(new_password) < 4:
            flash('Пароль должен содержать минимум 4 символа', 'error')
            return render_template('reset_password.html')
        
        success, message = reset_password(username, registration_code, new_password)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'error')
    
    return render_template('reset_password.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/write-off', methods=['GET', 'POST'])
@login_required
def write_off():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        quantity = request.form.get('quantity')
        description = request.form.get('description', '')
        point_id = request.form.get('point_id')
        
        if not item_id or not quantity:
            flash('Заполните все обязательные поля', 'error')
            return redirect(url_for('write_off'))
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                flash('Количество должно быть положительным числом', 'error')
                return redirect(url_for('write_off'))
        except ValueError:
            flash('Некорректное количество', 'error')
            return redirect(url_for('write_off'))
        
        if point_id == 'new':
            new_point = request.form.get('new_point')
            if new_point:
                new_id = add_write_off_point(new_point)
                point_id = new_id if new_id else None
        
        cursor.execute('SELECT id, name, quantity FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        
        if not item:
            flash('Позиция не найдена', 'error')
            return redirect(url_for('write_off'))
        
        cursor.execute('UPDATE items SET quantity = quantity - ? WHERE id = ?', 
                      (quantity, item_id))
        
        point_name = ''
        if point_id:
            cursor.execute('SELECT name FROM write_off_points WHERE id = ?', (point_id,))
            point = cursor.fetchone()
            point_name = f' для {point["name"]}' if point else ''
        
        log_description = f'Списание: {quantity} шт. {item["name"]}{point_name}'
        if description:
            log_description += f'. Причина: {description}'
            
        cursor.execute('''
            INSERT INTO operations_log 
            (user_id, item_id, write_off_point_id, operation_type, quantity, description) 
            VALUES (?, ?, ?, 'write_off', ?, ?)
        ''', (current_user.id, item_id, point_id, quantity, log_description))
        
        conn.commit()
        flash(f'Списано: {quantity} шт. {item["name"]}', 'success')
        return redirect(url_for('write_off'))
    
    cursor.execute('''
        SELECT i.id, i.name, i.quantity, i.min_quantity,
               COALESCE(c.name, 'Без категории') as category_name 
        FROM items i 
        LEFT JOIN categories c ON i.category_id = c.id 
        ORDER BY c.name, i.name
    ''')
    items = cursor.fetchall()
    
    points = get_all_write_off_points()
    
    conn.close()
    
    return render_template('write_off.html', items=items, points=points)

@app.route('/warehouse')
@login_required
def warehouse():
    items = get_all_items()
    categories = get_all_categories()
    points = get_all_write_off_points()
    return render_template('warehouse.html', items=items, categories=categories, points=points)

@app.route('/add-to-warehouse', methods=['POST'])
@login_required
def add_to_warehouse():
    item_id = request.form.get('item_id')
    quantity = request.form.get('quantity')
    
    if not item_id or not quantity:
        flash('Заполните все поля', 'error')
        return redirect(url_for('warehouse'))
    
    try:
        quantity = int(quantity)
        if quantity <= 0:
            flash('Количество должно быть положительным числом', 'error')
            return redirect(url_for('warehouse'))
    except ValueError:
        flash('Некорректное количество', 'error')
        return redirect(url_for('warehouse'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('UPDATE items SET quantity = quantity + ? WHERE id = ?', 
                  (quantity, item_id))
    
    cursor.execute('SELECT name FROM items WHERE id = ?', (item_id,))
    item = cursor.fetchone()
    
    cursor.execute('''
        INSERT INTO operations_log 
        (user_id, item_id, operation_type, quantity, description) 
        VALUES (?, ?, 'add', ?, ?)
    ''', (current_user.id, item_id, quantity, 
          f'Добавлено на склад: {quantity} шт. {item["name"] if item else ""}'))
    
    conn.commit()
    conn.close()
    
    flash(f'Товар добавлен на склад (+{quantity} шт.)', 'success')
    return redirect(url_for('warehouse'))

@app.route('/add-item', methods=['POST'])
@login_required
def add_item():
    name = request.form.get('name')
    category_id = request.form.get('category_id')
    quantity = request.form.get('quantity', '0')
    min_quantity = request.form.get('min_quantity', '5')
    
    if not name:
        flash('Введите название позиции', 'error')
        return redirect(url_for('warehouse'))
    
    try:
        quantity = int(quantity)
        min_quantity = int(min_quantity)
    except ValueError:
        flash('Некорректные числовые значения', 'error')
        return redirect(url_for('warehouse'))
    
    conn = get_db()
    cursor = conn.cursor()
    
    if category_id == 'new':
        new_category = request.form.get('new_category')
        if new_category:
            cursor.execute('SELECT id FROM categories WHERE name = ?', (new_category,))
            existing = cursor.fetchone()
            if existing:
                category_id = existing['id']
            else:
                cursor.execute('INSERT INTO categories (name) VALUES (?)', (new_category,))
                category_id = cursor.lastrowid
    
    cursor.execute('''
        INSERT INTO items (name, category_id, quantity, min_quantity) 
        VALUES (?, ?, ?, ?)
    ''', (name, category_id, quantity, min_quantity))
    
    item_id = cursor.lastrowid
    
    cursor.execute('''
        INSERT INTO operations_log 
        (user_id, item_id, operation_type, quantity, description) 
        VALUES (?, ?, 'add_new_item', ?, ?)
    ''', (current_user.id, item_id, quantity, 
          f'Добавлена новая позиция: {name}'))
    
    conn.commit()
    conn.close()
    
    flash(f'Новая позиция "{name}" успешно добавлена', 'success')
    return redirect(url_for('warehouse'))

@app.route('/delete-item/<int:item_id>', methods=['POST'])
@login_required
def delete_item_route(item_id):
    delete_item(item_id)
    flash('Позиция удалена', 'success')
    return redirect(url_for('warehouse'))

@app.route('/delete-category/<int:category_id>', methods=['POST'])
@login_required
def delete_category_route(category_id):
    delete_category(category_id)
    flash('Категория удалена', 'success')
    return redirect(url_for('warehouse'))

@app.route('/delete-log/<int:log_id>', methods=['POST'])
@login_required
def delete_log_route(log_id):
    delete_log(log_id)
    flash('Запись лога удалена', 'success')
    return redirect(url_for('logs'))

@app.route('/delete-point/<int:point_id>', methods=['POST'])
@login_required
def delete_point_route(point_id):
    delete_write_off_point(point_id)
    flash('Точка списания удалена', 'success')
    return redirect(url_for('warehouse'))

@app.route('/logs')
@login_required
def logs():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            ol.id,
            ol.created_at,
            u.username,
            i.name as item_name,
            COALESCE(c.name, '—') as category_name,
            COALESCE(wp.name, '—') as point_name,
            ol.operation_type,
            ol.quantity,
            ol.description
        FROM operations_log ol
        JOIN users u ON ol.user_id = u.id
        LEFT JOIN items i ON ol.item_id = i.id
        LEFT JOIN categories c ON i.category_id = c.id
        LEFT JOIN write_off_points wp ON ol.write_off_point_id = wp.id
        ORDER BY ol.created_at DESC
        LIMIT 200
    ''')
    
    logs = cursor.fetchall()
    conn.close()
    
    return render_template('logs.html', logs=logs)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total_items FROM items')
    total_items = cursor.fetchone()['total_items']
    
    cursor.execute('SELECT COALESCE(SUM(quantity), 0) as total_quantity FROM items')
    total_quantity = cursor.fetchone()['total_quantity']
    
    cursor.execute('''
        SELECT i.id, i.name, i.quantity, i.min_quantity, 
               COALESCE(c.name, 'Без категории') as category_name 
        FROM items i 
        LEFT JOIN categories c ON i.category_id = c.id 
        WHERE i.quantity <= i.min_quantity
        ORDER BY i.quantity ASC
    ''')
    low_stock = cursor.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         total_items=total_items,
                         total_quantity=total_quantity,
                         low_stock=low_stock)

@app.route('/api/low-stock')
@login_required
def low_stock_api():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT i.name, i.quantity, i.min_quantity, 
               COALESCE(c.name, 'Без категории') as category_name 
        FROM items i 
        LEFT JOIN categories c ON i.category_id = c.id 
        WHERE i.quantity <= i.min_quantity
        ORDER BY i.quantity ASC
    ''')
    
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify(items)

@app.route('/rename-item/<int:item_id>', methods=['POST'])
@login_required
def rename_item_route(item_id):
    new_name = request.form.get('new_name')
    if not new_name:
        flash('Введите новое название', 'error')
        return redirect(url_for('warehouse'))
    
    rename_item(item_id, new_name)
    flash('Позиция переименована', 'success')
    return redirect(url_for('warehouse'))

@app.route('/admin/users')
@login_required
def admin_users():
    users = get_all_users()
    return render_template('admin_users.html', users=users)

@app.errorhandler(404)
def not_found_error(error):
    return render_template('base.html', error='Страница не найдена'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('base.html', error='Внутренняя ошибка сервера'), 500

if __name__ == '__main__':
    init_db()
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)