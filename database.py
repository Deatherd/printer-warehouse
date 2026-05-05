import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE = os.environ.get('DATABASE_PATH', 'inventory.db')
REGISTRATION_CODE = '420300'

def get_db():
    db_dir = os.path.dirname(DATABASE)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            os.chmod(db_dir, 0o777)
        except Exception as e:
            print(f"Warning: Could not create directory {db_dir}: {e}")
    
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError:
        fallback_db = 'inventory.db'
        conn = sqlite3.connect(fallback_db)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS write_off_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            quantity INTEGER DEFAULT 0,
            min_quantity INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE SET NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER,
            write_off_point_id INTEGER,
            operation_type TEXT NOT NULL,
            quantity INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE SET NULL,
            FOREIGN KEY (write_off_point_id) REFERENCES write_off_points (id) ON DELETE SET NULL
        )
    ''')
    
    conn.commit()
    conn.close()

def register_user(username, password, registration_code):
    if registration_code != REGISTRATION_CODE:
        return False, "Неверный код регистрации"
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    if cursor.fetchone():
        conn.close()
        return False, "Пользователь уже существует"
    
    password_hash = generate_password_hash(password)
    cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)',
                   (username, password_hash))
    conn.commit()
    conn.close()
    return True, "Регистрация успешна"

def verify_user(username, password):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        from models import User
        return User(user['id'], user['username'], user['password_hash'])
    return None

def reset_password(username, registration_code, new_password):
    if registration_code != REGISTRATION_CODE:
        return False, "Неверный код регистрации"
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return False, "Пользователь не найден"
    
    password_hash = generate_password_hash(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE username = ?', 
                   (password_hash, username))
    
    cursor.execute('''
        INSERT INTO operations_log 
        (user_id, item_id, operation_type, quantity, description) 
        VALUES (?, NULL, 'password_reset', 0, ?)
    ''', (user['id'], f'Сброс пароля пользователя {username}'))
    
    conn.commit()
    conn.close()
    return True, f"Пароль пользователя {username} успешно изменен"

def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, created_at FROM users ORDER BY username')
    users = cursor.fetchall()
    conn.close()
    return users

def get_all_items():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.*, COALESCE(c.name, 'Без категории') as category_name
        FROM items i
        LEFT JOIN categories c ON i.category_id = c.id
        ORDER BY c.name, i.name
    ''')
    items = cursor.fetchall()
    conn.close()
    return items

def get_all_categories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories ORDER BY name')
    categories = cursor.fetchall()
    conn.close()
    return categories

def delete_item(item_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def delete_category(category_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE items SET category_id = NULL WHERE category_id = ?', (category_id,))
    cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()

def delete_log(log_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM operations_log WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()

def get_all_write_off_points():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM write_off_points ORDER BY name')
    points = cursor.fetchall()
    conn.close()
    return points

def add_write_off_point(name):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO write_off_points (name) VALUES (?)', (name,))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def rename_item(item_id, new_name):
    """Переименовать позицию"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE items SET name = ? WHERE id = ?', (new_name, item_id))
    conn.commit()
    conn.close()

def delete_write_off_point(point_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE operations_log SET write_off_point_id = NULL WHERE write_off_point_id = ?', (point_id,))
    cursor.execute('DELETE FROM write_off_points WHERE id = ?', (point_id,))
    conn.commit()
    conn.close()