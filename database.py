import sqlite3
import random
import time
import os

DB_NAME = 'bot.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица авторизованных пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    
    # Таблица кодов авторизации
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_codes (
            code TEXT PRIMARY KEY,
            created_at INTEGER
        )
    ''')
    
    # Таблица подписок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel TEXT,
            keyword TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def generate_auth_code():
    code = str(random.randint(100000, 999999))
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO auth_codes (code, created_at) VALUES (?, ?)', (code, int(time.time())))
    conn.commit()
    conn.close()
    return code

def verify_and_use_auth_code(code, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Очистка старых кодов (старше 15 минут = 900 секунд)
    cursor.execute('DELETE FROM auth_codes WHERE created_at < ?', (int(time.time()) - 900,))
    
    cursor.execute('SELECT * FROM auth_codes WHERE code = ?', (code,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute('DELETE FROM auth_codes WHERE code = ?', (code,))
        cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()
        return True
    
    conn.commit()
    conn.close()
    return False

def is_user_authorized(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def add_subscription(user_id, channel, keyword):
    channel = channel.lower()
    keyword = keyword.lower()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM subscriptions WHERE user_id = ? AND channel = ? AND keyword = ?', (user_id, channel, keyword))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO subscriptions (user_id, channel, keyword) VALUES (?, ?, ?)', (user_id, channel, keyword))
        conn.commit()
        conn.close()
        return True
    
    conn.close()
    return False

def remove_subscription(user_id, channel, keyword):
    channel = channel.lower()
    keyword = keyword.lower()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE user_id = ? AND channel = ? AND keyword = ?', (user_id, channel, keyword))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def remove_all_channel_subscriptions(user_id, channel):
    channel = channel.lower()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM subscriptions WHERE user_id = ? AND channel = ?', (user_id, channel))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_user_subscriptions(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT channel, keyword FROM subscriptions WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    subs = {}
    for ch, kw in rows:
        if ch not in subs:
            subs[ch] = []
        subs[ch].append(kw)
    return subs

def get_all_active_channels():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT channel FROM subscriptions')
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_users_for_channel(channel):
    channel = channel.lower()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, keyword FROM subscriptions WHERE channel = ?', (channel,))
    rows = cursor.fetchall()
    conn.close()
    
    users = {}
    for uid, kw in rows:
        if uid not in users:
            users[uid] = []
        users[uid].append(kw)
    return users
