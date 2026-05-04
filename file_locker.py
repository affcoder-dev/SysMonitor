import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import hashlib
import sqlite3
import sys

# Get the database path
DB_PATH = os.path.join(os.path.dirname(__file__), 'sysmonitor.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def log_file_event(file_name, event_type, details=""):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO file_access_events (file_name, event_type, details) VALUES (?, ?, ?)", 
                  (file_name, event_type, details))
        conn.commit()
    except Exception as e:
        print(f"Log error: {e}")
    finally:
        conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def lock_file():
    file_path = filedialog.askopenfilename(title="Kilidlenecek Dosyayı Seçin")
    if not file_path:
        return
        
    if file_path.endswith('.sysmon_locked'):
        messagebox.showwarning("Uyarı", "Bu dosya zaten kilitli!")
        return

    locked_path = file_path + ".sysmon_locked"
    
    try:
        # Rename the file to lock it
        os.rename(file_path, locked_path)
        
        # Save to DB
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO file_locks (original_path, locked_path, password_hash) VALUES (?, ?, ?)",
                  (file_path, locked_path, 'use_master'))
        conn.commit()
        conn.close()
        
        log_file_event(os.path.basename(file_path), "Locked", "Masaüstü aracı ile kilitlendi (Ana Şifre).")
        messagebox.showinfo("Başarılı", f"Dosya başarıyla Ana Şifre ile kilitlendi!\n\nKilitli Dosya: {locked_path}")
        
    except Exception as e:
        messagebox.showerror("Hata", f"Dosya kilitlenirken hata oluştu: {str(e)}")

def register_extension():
    # Associate .sysmon_locked with unlocker.pyw in Registry
    import winreg
    try:
        pythonw_path = sys.executable.replace("python.exe", "pythonw.exe")
        unlocker_path = os.path.join(os.path.dirname(__file__), "unlocker.pyw")
        
        if not os.path.exists(unlocker_path):
            messagebox.showwarning("Uyarı", "unlocker.pyw bulunamadı, dosya uzantısı eşleşmesi yapılamadı.")
            return

        key_path = r"Software\Classes\.sysmon_locked"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "SysMonLockedFile")
        winreg.CloseKey(key)

        key_path = r"Software\Classes\SysMonLockedFile\shell\open\command"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        command = f'"{pythonw_path}" "{unlocker_path}" --file "%1"'
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        
        print("Uzantı eşleşmesi başarılı.")
    except Exception as e:
        print("Uzantı eşleşmesi hatası:", e)

def main():
    register_extension()
    root = tk.Tk()
    root.title("SysMonitor - File Locker")
    root.geometry("300x150")
    root.eval('tk::PlaceWindow . center')
    
    lbl = tk.Label(root, text="SysMonitor Dosya Kilitleyici", font=("Arial", 12, "bold"))
    lbl.pack(pady=10)
    
    btn = tk.Button(root, text="Dosya Seç ve Kilitle", command=lock_file, width=20, height=2, bg="#333", fg="white")
    btn.pack(pady=10)
    
    root.mainloop()

if __name__ == "__main__":
    main()
