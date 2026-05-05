import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE = os.environ.get('DATABASE_PATH', 'inventory.db')
REGISTRATION_CODE = '420300'

def get_db():
    # Создаем директорию для базы данных, если её нет
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
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            quantity INTEGER DEFAULT 0,
            min_quantity INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER,
            operation_type TEXT NOT NULL,
            quantity INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (item_id) REFERENCES items (id)
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
    """Сброс пароля пользователя по коду регистрации"""
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
    """Получить список всех пользователей"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, created_at FROM users ORDER BY username')
    users = cursor.fetchall()
    conn.close()
    return users