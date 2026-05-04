import sqlite3
db = r'c:\Users\affan\.gemini\antigravity\scratch\SysMonitor\sysmonitor.db'
conn = sqlite3.connect(db)
c = conn.cursor()
c.execute("DELETE FROM settings WHERE key IN ('setup_complete','admin_username','master_password_hash')")
c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('setup_complete','0')")
conn.commit()
conn.close()
print('Kurulum sifirlandı! Simdi run.bat calistirin.')
conn2 = sqlite3.connect(db)
c2 = conn2.cursor()
c2.execute('SELECT key,value FROM settings')
for r in c2.fetchall():
    print(r)
conn2.close()
