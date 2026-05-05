import pkgutil
import importlib
import os

# Исправление для совместимости с новыми версиями Python
if not hasattr(pkgutil, 'get_loader'):
    pkgutil.get_loader = importlib.util.find_spec

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from database import init_db, get_db, register_user, verify_user, get_user_by_id, get_all_users
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
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
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
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Неверный логин или пароль', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
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
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username')
        registration_code = request.form.get('registration_code')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Проверки
        if not all([username, registration_code, new_password, confirm_password]):
            flash('Заполните все поля', 'error')
            return render_template('reset_password.html')
        
        if new_password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('reset_password.html')
        
        if len(new_password) < 4:
            flash('Пароль должен содержать минимум 4 символа', 'error')
            return render_template('reset_password.html')
        
        # Импортируем функцию сброса пароля
        from database import reset_password as do_reset_password
        success, message = do_reset_password(username, registration_code, new_password)
        
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

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем статистику
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

@app.route('/add-to-warehouse', methods=['GET', 'POST'])
@login_required
def add_to_warehouse():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        quantity = request.form.get('quantity')
        
        if not item_id or not quantity:
            flash('Заполните все поля', 'error')
            return redirect(url_for('add_to_warehouse'))
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                flash('Количество должно быть положительным числом', 'error')
                return redirect(url_for('add_to_warehouse'))
        except ValueError:
            flash('Некорректное количество', 'error')
            return redirect(url_for('add_to_warehouse'))
        
        # Обновляем количество
        cursor.execute('UPDATE items SET quantity = quantity + ? WHERE id = ?', 
                      (quantity, item_id))
        
        # Получаем название позиции для лога
        cursor.execute('SELECT name FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        
        # Записываем в лог
        cursor.execute('''
            INSERT INTO operations_log 
            (user_id, item_id, operation_type, quantity, description) 
            VALUES (?, ?, 'add', ?, ?)
        ''', (current_user.id, item_id, quantity, 
              f'Добавлено на склад: {quantity} шт. {item["name"] if item else ""}'))
        
        conn.commit()
        flash(f'Товар добавлен на склад (+{quantity} шт.)', 'success')
        return redirect(url_for('dashboard'))
    
    # Получаем список товаров для формы
    cursor.execute('''
        SELECT i.id, i.name, i.quantity, i.min_quantity, 
               COALESCE(c.name, 'Без категории') as category_name 
        FROM items i 
        LEFT JOIN categories c ON i.category_id = c.id 
        ORDER BY c.name, i.name
    ''')
    items = cursor.fetchall()
    conn.close()
    
    return render_template('add_to_warehouse.html', items=items)

@app.route('/write-off', methods=['GET', 'POST'])
@login_required
def write_off():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        quantity = request.form.get('quantity')
        description = request.form.get('description', '')
        
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
        
        # Проверяем наличие на складе
        cursor.execute('SELECT id, name, quantity FROM items WHERE id = ?', (item_id,))
        item = cursor.fetchone()
        
        if not item:
            flash('Позиция не найдена', 'error')
            return redirect(url_for('write_off'))
            
        if item['quantity'] >= quantity:
            # Списание
            cursor.execute('UPDATE items SET quantity = quantity - ? WHERE id = ?', 
                          (quantity, item_id))
            
            # Записываем в лог
            log_description = f'Списание: {quantity} шт. {item["name"]}'
            if description:
                log_description += f'. Причина: {description}'
                
            cursor.execute('''
                INSERT INTO operations_log 
                (user_id, item_id, operation_type, quantity, description) 
                VALUES (?, ?, 'write_off', ?, ?)
            ''', (current_user.id, item_id, quantity, log_description))
            
            conn.commit()
            flash(f'Списано: {quantity} шт. {item["name"]}', 'success')
        else:
            flash(f'Недостаточно товара на складе! В наличии: {item["quantity"]} шт.', 'error')
        
        return redirect(url_for('dashboard'))
    
    # Получаем список товаров для формы (только те, что в наличии)
    cursor.execute('''
        SELECT i.id, i.name, i.quantity, i.min_quantity,
               COALESCE(c.name, 'Без категории') as category_name 
        FROM items i 
        LEFT JOIN categories c ON i.category_id = c.id 
        WHERE i.quantity > 0
        ORDER BY c.name, i.name
    ''')
    items = cursor.fetchall()
    conn.close()
    
    return render_template('write_off.html', items=items)

@app.route('/add-item', methods=['GET', 'POST'])
@login_required
def add_item():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        name = request.form.get('name')
        category_id = request.form.get('category_id')
        quantity = request.form.get('quantity', '0')
        min_quantity = request.form.get('min_quantity', '5')
        
        if not name:
            flash('Введите название позиции', 'error')
            return redirect(url_for('add_item'))
        
        try:
            quantity = int(quantity)
            min_quantity = int(min_quantity)
            if quantity < 0 or min_quantity < 1:
                flash('Некорректные значения количества', 'error')
                return redirect(url_for('add_item'))
        except ValueError:
            flash('Некорректные числовые значения', 'error')
            return redirect(url_for('add_item'))
        
        # Если выбрана новая категория
        if category_id == 'new':
            new_category = request.form.get('new_category')
            if not new_category:
                flash('Введите название новой категории', 'error')
                return redirect(url_for('add_item'))
            
            # Проверяем, существует ли уже такая категория
            cursor.execute('SELECT id FROM categories WHERE name = ?', (new_category,))
            existing = cursor.fetchone()
            if existing:
                category_id = existing['id']
            else:
                cursor.execute('INSERT INTO categories (name) VALUES (?)', (new_category,))
                category_id = cursor.lastrowid
        
        # Добавляем позицию
        cursor.execute('''
            INSERT INTO items (name, category_id, quantity, min_quantity) 
            VALUES (?, ?, ?, ?)
        ''', (name, category_id, quantity, min_quantity))
        
        item_id = cursor.lastrowid
        
        # Записываем в лог
        cursor.execute('''
            INSERT INTO operations_log 
            (user_id, item_id, operation_type, quantity, description) 
            VALUES (?, ?, 'add_new_item', ?, ?)
        ''', (current_user.id, item_id, quantity, 
              f'Добавлена новая позиция: {name} (начальное количество: {quantity})'))
        
        conn.commit()
        flash(f'Новая позиция "{name}" успешно добавлена', 'success')
        return redirect(url_for('dashboard'))
    
    cursor.execute('SELECT * FROM categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()
    
    return render_template('add_item.html', categories=categories)

@app.route('/logs')
@login_required
def logs():
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем параметры фильтрации
    operation_type = request.args.get('type', '')
    user_id = request.args.get('user_id', '')
    
    query = '''
        SELECT 
            ol.created_at,
            u.username,
            i.name as item_name,
            COALESCE(c.name, '—') as category_name,
            ol.operation_type,
            ol.quantity,
            ol.description
        FROM operations_log ol
        JOIN users u ON ol.user_id = u.id
        LEFT JOIN items i ON ol.item_id = i.id
        LEFT JOIN categories c ON i.category_id = c.id
        WHERE 1=1
    '''
    params = []
    
    if operation_type:
        query += ' AND ol.operation_type = ?'
        params.append(operation_type)
    
    if user_id:
        query += ' AND ol.user_id = ?'
        params.append(user_id)
    
    query += ' ORDER BY ol.created_at DESC LIMIT 200'
    
    cursor.execute(query, params)
    logs = cursor.fetchall()
    
    # Получаем список пользователей для фильтра
    cursor.execute('SELECT id, username FROM users ORDER BY username')
    users = cursor.fetchall()
    
    conn.close()
    
    return render_template('logs.html', logs=logs, users=users, 
                         current_type=operation_type, current_user_id=user_id)

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

@app.route('/admin/users')
@login_required
def admin_users():
    """Страница управления пользователями (только для админов)"""
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