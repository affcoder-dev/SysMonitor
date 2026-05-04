import tkinter as tk
from tkinter import messagebox, simpledialog
import os
import sys
import hashlib
import sqlite3
import subprocess
import argparse

import win32event, win32api, winerror

# Singleton check to prevent multiple windows
mutex = win32event.CreateMutex(None, False, "SysMonitorUnlockerMutex")
if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
    sys.exit(0)

DB_PATH = os.path.join(os.path.dirname(__file__), 'sysmonitor.db')

def get_connection():
    return sqlite3.connect(DB_PATH, timeout=20)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def log_event(table, **kwargs):
    try:
        conn = get_connection()
        c = conn.cursor()
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?"] * len(kwargs))
        query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        c.execute(query, tuple(kwargs.values()))
        conn.commit()
    except Exception as e:
        print(f"Log error: {e}")
    finally:
        conn.close()

def get_master_password_hash():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='master_password_hash'")
    result = c.fetchone()
    conn.close()
    if result:
        return result[0]
    return hash_password("admin") # Fallback default

def unlock_file(locked_path):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT original_path, password_hash FROM file_locks WHERE locked_path = ?", (locked_path,))
    result = c.fetchone()
    conn.close()

    if not result:
        messagebox.showerror("Hata", "Bu dosya sistemde kayıtlı değil veya yolu değişmiş.")
        return

    original_path, pwd_hash = result
    
    class UnlockDialog:
        def __init__(self, parent, title, prompt):
            self.top = tk.Toplevel(parent)
            self.top.title(title)
            self.top.geometry("350x150")
            
            # Center the window
            self.top.update_idletasks()
            width = self.top.winfo_width()
            height = self.top.winfo_height()
            x = (self.top.winfo_screenwidth() // 2) - (width // 2)
            y = (self.top.winfo_screenheight() // 2) - (height // 2)
            self.top.geometry('{}x{}+{}+{}'.format(width, height, x, y))
            
            tk.Label(self.top, text=prompt).pack(pady=10)
            self.entry = tk.Entry(self.top, show="*", width=30)
            self.entry.pack(pady=5)
            self.entry.focus_set()
            
            btn_frame = tk.Frame(self.top)
            btn_frame.pack(pady=10)
            
            self.password = None
            self.action = None
            
            tk.Button(btn_frame, text="Kalıcı Aç", command=lambda: self.submit("permanent"), bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Geçici Aç (5 dk)", command=lambda: self.submit("temporary"), bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5)
            
        def submit(self, action):
            self.password = self.entry.get()
            self.action = action
            self.top.destroy()

    root = tk.Tk()
    root.withdraw()
    
    dialog = UnlockDialog(root, "Şifre Gerekli", f"{os.path.basename(original_path)}\niçin şifrenizi girin:")
    root.wait_window(dialog.top)
    
    password = dialog.password
    action = dialog.action
    
    if not password or not action:
        log_event("file_access_events", file_name=os.path.basename(original_path), event_type="Unlock_Failed", details="İptal edildi")
        return
        
    master_hash = get_master_password_hash()
        
    if hash_password(password) == master_hash or hash_password(password) == pwd_hash:
        try:
            conn = get_connection()
            c = conn.cursor()
            
            if action == 'permanent':
                if os.path.isdir(original_path) or (os.path.exists(locked_path) and os.path.getsize(locked_path) == 0):
                    # Folder: unhide and remove dummy file
                    subprocess.run(['attrib', '-h', '-s', original_path], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    if os.path.exists(locked_path):
                        os.remove(locked_path)
                else:
                    # File: rename back
                    os.rename(locked_path, original_path)
                
                c.execute("DELETE FROM file_locks WHERE locked_path = ?", (locked_path,))
                log_event("file_access_events", file_name=os.path.basename(original_path), event_type="Unlock_Success", details="Masaüstü: Kalıcı olarak açıldı.")
                
            elif action == 'temporary':
                if os.path.isdir(original_path) or (os.path.exists(locked_path) and os.path.getsize(locked_path) == 0):
                    # Folder: unhide, keep dummy file
                    subprocess.run(['attrib', '-h', '-s', original_path], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    # File: rename back
                    os.rename(locked_path, original_path)
                    
                c.execute("UPDATE file_locks SET unlock_expiry = datetime('now', '+5 minutes', 'localtime') WHERE locked_path = ?", (locked_path,))
                log_event("file_access_events", file_name=os.path.basename(original_path), event_type="Unlock_Success", details="Masaüstü: 5 dakikalığına açıldı.")

            conn.commit()
            conn.close()
            
            # Open the file
            os.startfile(original_path)
        except Exception as e:
            messagebox.showerror("Hata", f"Dosya açılırken bir hata oluştu: {str(e)}")
            log_event("file_access_events", file_name=os.path.basename(original_path), event_type="Unlock_Failed", details=f"Hata: {str(e)}")
    else:
        messagebox.showerror("Hata", "Yanlış Şifre!")
        log_event("file_access_events", file_name=os.path.basename(original_path), event_type="Unlock_Failed", details="Yanlış Şifre")

def get_serial(device_id):
    """Extracts a stable serial/identifier from a PnP InstanceId."""
    id_upper = device_id.upper()
    if "USBSTOR" in id_upper:
        parts = id_upper.split('#')
        if len(parts) >= 3:
            return parts[2].split('&')[0]
        return id_upper.split('\\')[-1].split('&')[0]
    parts = id_upper.split('\\')
    if len(parts) >= 2:
        return parts[-1]
    return id_upper

def unlock_usb(device_id):
    import wmi
    import pythoncom
    pythoncom.CoInitialize()
    w = wmi.WMI()
    
    # Try to get the friendly device name
    try:
        dev_query = w.query(f"SELECT Name, Description FROM Win32_PnPEntity WHERE DeviceID = '{device_id.replace(chr(92), chr(92)*2)}'")
        device_name = (dev_query[0].Name or dev_query[0].Description or "Bilinmeyen Cihaz") if dev_query else "Bilinmeyen Cihaz"
    except:
        device_name = "Bilinmeyen Cihaz"

    root = tk.Tk()
    root.withdraw()

    # Build the prompt window
    prompt_win = tk.Toplevel(root)
    prompt_win.title("Yeni USB Cihazı Algılandı")
    prompt_win.geometry("420x260")
    prompt_win.configure(bg="#1e1e2e")
    prompt_win.resizable(False, False)
    prompt_win.attributes("-topmost", True)
    
    # Center on screen
    prompt_win.update_idletasks()
    sw = prompt_win.winfo_screenwidth()
    sh = prompt_win.winfo_screenheight()
    x = (sw - 420) // 2
    y = (sh - 260) // 2
    prompt_win.geometry(f"420x260+{x}+{y}")
    
    icon_label = tk.Label(prompt_win, text="\u26a0\ufe0f Yeni USB Cihazı Algılandı",
                          font=("Segoe UI", 13, "bold"), fg="#f1c40f", bg="#1e1e2e")
    icon_label.pack(pady=(18, 4))

    name_label = tk.Label(prompt_win, text=device_name,
                          font=("Segoe UI", 10), fg="#cdd6f4", bg="#1e1e2e", wraplength=380)
    name_label.pack(pady=(0, 2))

    id_label = tk.Label(prompt_win, text=device_id[:60] + ("..." if len(device_id) > 60 else ""),
                        font=("Courier", 7), fg="#6c7086", bg="#1e1e2e")
    id_label.pack(pady=(0, 10))

    pw_label = tk.Label(prompt_win, text="Beyaz listeye eklemek i\u00e7in sistem \u015fifrenizi girin:",
                        font=("Segoe UI", 9), fg="#a6e3a1", bg="#1e1e2e")
    pw_label.pack()

    pw_entry = tk.Entry(prompt_win, show="*", width=30, font=("Segoe UI", 10),
                        bg="#313244", fg="#cdd6f4", insertbackground="white", relief="flat")
    pw_entry.pack(pady=(4, 12))
    pw_entry.focus_set()

    result = {"action": None}

    def on_authorize():
        result["action"] = "authorize"
        result["password"] = pw_entry.get()
        prompt_win.destroy()

    def on_block():
        result["action"] = "block"
        prompt_win.destroy()

    prompt_win.protocol("WM_DELETE_WINDOW", on_block)  # closing = block
    pw_entry.bind("<Return>", lambda e: on_authorize())

    btn_frame = tk.Frame(prompt_win, bg="#1e1e2e")
    btn_frame.pack()
    tk.Button(btn_frame, text="\u2714  Yetkilendir", command=on_authorize,
              bg="#a6e3a1", fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
              relief="flat", padx=12, pady=6).pack(side=tk.LEFT, padx=8)
    tk.Button(btn_frame, text="\u2718  Engelle", command=on_block,
              bg="#f38ba8", fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
              relief="flat", padx=12, pady=6).pack(side=tk.LEFT, padx=8)

    root.wait_window(prompt_win)

    if result.get("action") != "authorize":
        # User clicked Block or closed window — block the device
        print(f"[BLOCK] User denied: {device_id}")
        subprocess.run(f'pnputil /disable-device "{device_id}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_event("usb_events", event_type="Blocked", device_name=device_name, device_id=device_id)
        messagebox.showwarning("Engellendi", f"Cihaz engellendi:\n{device_name}")
        return

    # User clicked Authorize — validate password
    password = result.get("password", "")
    master_hash = get_master_password_hash()

    if hash_password(password) == master_hash:
        try:
            serial = get_serial(device_id)
            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO authorized_devices (device_id, device_name) VALUES (?, ?)",
                      (serial, device_name))
            conn.commit()
            conn.close()

            # Enable the device AND all related sub-devices by VID+PID pattern
            # (pnputil alone only enables one node; this catches USB parent + all HID children)
            import re as _re
            vid_pid_match = _re.search(r'(VID_[0-9A-F]+&PID_[0-9A-F]+)', device_id.upper())
            if vid_pid_match:
                vid_pid = vid_pid_match.group(1)
                ps_enable = (
                    'powershell -Command "'
                    f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like '*{vid_pid}*' }} "
                    '| Enable-PnpDevice -Confirm:$false"'
                )
                subprocess.run(ps_enable, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.run(f'pnputil /enable-device "{device_id}"', shell=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)

            subprocess.run('pnputil /scan-devices', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            log_event("usb_events", event_type="Authorized", device_name=device_name, device_id=device_id)
            messagebox.showinfo("Basarili", f"Cihaz beyaz listeye eklendi:\n{device_name}")
        except Exception as e:
            messagebox.showerror("Hata", f"Hata olustu: {str(e)}")
    else:
        messagebox.showerror("Hata", "Yanlış Şifre! Cihaz engellendi.")
        subprocess.run(f'pnputil /disable-device "{device_id}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_event("usb_events", event_type="Blocked", device_name=device_name, device_id=device_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SysMonitor Unlocker")
    parser.add_argument("--file", help="Kilitli dosyanın yolu")
    parser.add_argument("--usb", help="Engellenen USB'nin DeviceID'si")
    args = parser.parse_args()
    
    if args.file:
        unlock_file(args.file)
    elif args.usb:
        unlock_usb(args.usb)
    else:
        # Just run as a standalone app to show error
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Hata", "Argüman eksik. Bu uygulama tek başına çalıştırılamaz.")
