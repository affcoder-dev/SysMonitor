import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), 'sysmonitor.db')

def check_and_reset_if_needed():
    """
    If the DB exists but has no valid admin credentials,
    reset setup_complete to 0 so the setup wizard is shown.
    This handles the case where a pre-configured DB was bundled.
    """
    if not os.path.exists(DB_PATH):
        return  # Fresh install, database.py will create it

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT value FROM settings WHERE key='admin_username'")
        row_user = c.fetchone()

        c.execute("SELECT value FROM settings WHERE key='master_password_hash'")
        row_pwd = c.fetchone()

        # If credentials are missing, reset setup flag
        if not row_user or not row_user[0] or not row_pwd or not row_pwd[0]:
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('setup_complete', '0')")
            conn.commit()
            print("[OK] Kurulum sifirlandı - ilk kurulum ekrani acilacak.")

        conn.close()
    except Exception as e:
        print(f"[WARN] DB kontrol hatası: {e}")

if __name__ == '__main__':
    check_and_reset_if_needed()
    print("DB kontrol tamamlandı.")
