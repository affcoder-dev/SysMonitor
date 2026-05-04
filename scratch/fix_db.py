import sqlite3
import os

db_path = 'sysmonitor.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    try:
        c.execute('ALTER TABLE authorized_devices ADD COLUMN device_name TEXT')
        conn.commit()
        print("Column 'device_name' added successfully.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("Column already exists.")
        else:
            print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()
else:
    print("Database file not found.")
