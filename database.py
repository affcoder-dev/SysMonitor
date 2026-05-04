import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'sysmonitor.db')

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=20)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")
    
    # Table for active window changes
    c.execute('''
        CREATE TABLE IF NOT EXISTS window_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            window_title TEXT NOT NULL,
            duration_seconds INTEGER DEFAULT 0
        )
    ''')
    
    # Table for new process creations
    c.execute('''
        CREATE TABLE IF NOT EXISTS process_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            process_name TEXT NOT NULL,
            pid INTEGER,
            exe_path TEXT
        )
    ''')
    
    # Table for USB connections/disconnections
    c.execute('''
        CREATE TABLE IF NOT EXISTS usb_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            event_type TEXT NOT NULL, -- 'Connected' or 'Disconnected'
            device_name TEXT NOT NULL,
            device_id TEXT
        )
    ''')
    
    # Table for file access/locker events
    c.execute('''
        CREATE TABLE IF NOT EXISTS file_access_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_name TEXT NOT NULL,
            event_type TEXT NOT NULL, -- 'Locked', 'Unlock_Success', 'Unlock_Failed'
            details TEXT
        )
    ''')
    
    # Table to store locked files
    c.execute('''
        CREATE TABLE IF NOT EXISTS file_locks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT NOT NULL,
            locked_path TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    try:
        c.execute("ALTER TABLE file_locks ADD COLUMN unlock_expiry DATETIME DEFAULT NULL")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    
    # Table for global settings (e.g., master password)
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')

    # Table for authorized USB devices
    c.execute('''
        CREATE TABLE IF NOT EXISTS authorized_devices (
            device_id TEXT PRIMARY KEY,
            device_name TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Do NOT insert a default password here.
    # setup_complete=0 triggers the first-run setup wizard.
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('setup_complete', '0')")
    
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print(f"Database initialized at {DB_PATH}")
