import win32gui
import time
import wmi
import threading
import os
import sys
import winreg
import pythoncom
import psutil
from database import get_connection, init_db

def get_serial_from_id(instance_id):
    """Extracts the unique serial part from various PnP ID formats."""
    id_upper = instance_id.upper()
    
    # Standard USB Storage
    if "USBSTOR" in id_upper:
        parts = id_upper.split('#')
        if len(parts) >= 3:
            return parts[2].split('&')[0]
        parts = id_upper.split('\\')
        return parts[-1].split('&')[0]
    
    # HID or USB Generic (Mouse/Keyboard)
    # These often don't have a simple serial, so we use the instance part
    parts = id_upper.split('\\')
    if len(parts) >= 2:
        # Return the last part which is the unique instance on this machine
        return parts[-1]
    
    return id_upper


def log_window_event(title, duration):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO window_events (window_title, duration_seconds) VALUES (?, ?)", (title, duration))
        conn.commit()
    except Exception as e:
        print("DB Error:", e)
    finally:
        conn.close()

def log_process_event(name, pid, path):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO process_events (process_name, pid, exe_path) VALUES (?, ?, ?)", (name, pid, path))
        conn.commit()
    except Exception as e:
        print("DB Error:", e)
    finally:
        conn.close()

def log_usb_event(event_type, device_name, device_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO usb_events (event_type, device_name, device_id) VALUES (?, ?, ?)", (event_type, device_name, device_id))
        conn.commit()
    except Exception as e:
        print("DB Error:", e)
    finally:
        conn.close()

def monitor_windows():
    print("Starting window monitor...")
    last_title = ""
    start_time = time.time()
    
    while True:
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            
            if title and title != last_title:
                duration = int(time.time() - start_time)
                if last_title and duration > 0:
                    log_window_event(last_title, duration)
                last_title = title
                start_time = time.time()
        except Exception as e:
            pass
            
        time.sleep(2)  # Poll every 2s — responsive enough, lighter CPU load

def monitor_processes():
    print("Starting process monitor...")
    blacklist = ['bittorrent.exe', 'utorrent.exe'] # Example blacklist
    try:
        pythoncom.CoInitialize()
        c = wmi.WMI()
        process_watcher = c.Win32_Process.watch_for("creation")
        while True:
            new_process = process_watcher()
            log_process_event(new_process.Name, new_process.ProcessId, new_process.ExecutablePath)
            
            if new_process.Name and new_process.Name.lower() in blacklist:
                try:
                    p = psutil.Process(new_process.ProcessId)
                    p.terminate()
                    print(f"Terminated blacklisted process: {new_process.Name}")
                except Exception as e:
                    pass
    except Exception as e:
        print(f"Process monitor error: {e}")

last_usb_event_time = 0


def _handle_new_device(instance_id, device_name):
    """Called when a brand-new device is plugged in.
    Authorization is based on the FULL USB parent InstanceId (unique per physical device).
    """
    import subprocess as sp
    import re
    instance_id = instance_id.upper()

    # Load all authorized device_ids from DB (stored as full USB InstanceId)
    try:
        conn = get_connection()
        c_db = conn.cursor()
        c_db.execute("SELECT device_id FROM authorized_devices")
        authorized_ids = set(row[0].upper() for row in c_db.fetchall())
        conn.close()
    except:
        authorized_ids = set()

    def is_match(check_id):
        """Full InstanceId match OR backward-compat: old serial/VID+PID substring check."""
        if check_id in authorized_ids:
            return True
        # Backward compat: stored value contained in the InstanceId (e.g., USB serial number)
        return any(auth in check_id for auth in authorized_ids)

    # ── Fast path: is this instance_id already authorized? (no delay) ────────
    if is_match(instance_id):
        print(f"\n[OK] Authorized device connected: {device_name} | {instance_id[:70]}")
        return

    # ── Unknown device — disable immediately ────────────────────────────────
    print(f"\n[!!] UNKNOWN DEVICE DETECTED: {device_name}")
    print(f"     InstanceId: {instance_id[:80]}")

    sp.run(f'pnputil /disable-device "{instance_id}"', shell=True,
           creationflags=sp.CREATE_NO_WINDOW)
    print(f"     [BLOCKED] Disabled: {instance_id[:70]}")

    # ── Find USB parent (full, unique InstanceId for this physical device) ───
    vid_pid_match = re.search(r'(VID_[0-9A-F]+&PID_[0-9A-F]+)', instance_id)
    target_id = instance_id  # fallback

    if vid_pid_match:
        vid_pid = vid_pid_match.group(1)
        ps_cmd = (
            'powershell -Command "'
            f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like 'USB\\{vid_pid}*' }} "
            '| Select-Object -First 1 -ExpandProperty InstanceId"'
        )
        try:
            res = sp.run(ps_cmd, capture_output=True, text=True, shell=True,
                         encoding='utf-8', errors='ignore',
                         creationflags=sp.CREATE_NO_WINDOW)
            if res.stdout.strip():
                parent_id = res.stdout.strip().upper()
                if parent_id != instance_id:
                    sp.run(f'pnputil /disable-device "{parent_id}"', shell=True,
                           creationflags=sp.CREATE_NO_WINDOW)
                    print(f"     [BLOCKED] USB parent also disabled: {parent_id[:70]}")
                target_id = parent_id
        except Exception as e:
            print(f"     [WARN] Could not find USB parent: {e}")

    # ── Re-check: maybe the USB parent IS authorized ─────────────────────────
    if target_id != instance_id and is_match(target_id):
        print(f"     [RE-ENABLE] USB parent is authorized — re-enabling.")
        ps_enable = (
            'powershell -Command "'
            f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like '*{vid_pid_match.group(1)}*' }} "
            '| Enable-PnpDevice -Confirm:$false"'
        )
        sp.run(ps_enable, shell=True, creationflags=sp.CREATE_NO_WINDOW)
        return

    # ── Truly unknown — keep disabled, show popup ────────────────────────────
    log_usb_event("Blocked", device_name, target_id)
    pythonw_path = sys.executable.replace("python.exe", "pythonw.exe")
    current_dir = os.path.dirname(os.path.abspath(__file__))
    unlocker_path = os.path.join(current_dir, "unlocker.pyw")
    print(f"     [POPUP] Launching whitelist prompt...")
    proc = sp.Popen([pythonw_path, unlocker_path, "--usb", target_id])
    proc.wait()  # Block until user responds — next event queues naturally





def monitor_usb_events():
    """Watch for newly plugged-in USB/HID devices using a single WMI event watcher."""
    import queue as q_mod
    import re
    import time as time_mod
    print("USB monitor started (WMI event mode)...")

    device_queue = q_mod.Queue()

    def extract_vid_pid(instance_id):
        """Extract VID+PID as a stable key to identify a physical device."""
        m = re.search(r'(VID_[0-9A-F]+&PID_[0-9A-F]+)', instance_id.upper())
        if m:
            return m.group(1)
        return instance_id  # Fallback to full ID if no VID/PID

    def watcher_thread():
        """Single WMI watcher for all PnP device creations."""
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            watcher = c.Win32_PnPEntity.watch_for("creation")
            while True:
                try:
                    device = watcher(timeout_ms=5000)
                    if device is None:
                        continue
                    instance_id = (device.DeviceID or "").upper()
                    if not instance_id:
                        continue
                    # Only care about real USB/HID hardware (has VID_)
                    if "VID_" not in instance_id:
                        continue
                    name = device.Name or device.Description or "USB Device"
                    device_queue.put((instance_id, name))
                except wmi.x_wmi_timed_out:
                    continue
                except Exception as e:
                    print(f"USB watcher error: {e}")
                    time_mod.sleep(2)
        except Exception as e:
            print(f"USB watcher fatal: {e}")

    threading.Thread(target=watcher_thread, daemon=True).start()

    # Cooldown: VID&PID -> last popup time. Prevents multiple popups per physical device.
    last_popup_time = {}
    COOLDOWN_SECONDS = 20

    while True:
        try:
            instance_id, name = device_queue.get(timeout=5)

            vid_pid = extract_vid_pid(instance_id)
            now = time_mod.time()

            # Skip if we already showed a popup for this VID+PID recently
            if now - last_popup_time.get(vid_pid, 0) < COOLDOWN_SECONDS:
                print(f"[SKIP duplicate] {name} ({vid_pid})")
                continue

            last_popup_time[vid_pid] = now
            _handle_new_device(instance_id, name)

        except Exception:
            pass  # queue timeout, loop again




def monitor_temporary_locks():
    import subprocess
    from datetime import datetime
    print("Starting temporary locks monitor...")
    while True:
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT id, original_path, locked_path FROM file_locks WHERE unlock_expiry IS NOT NULL AND unlock_expiry <= datetime('now', 'localtime')")
            expired_locks = c.fetchall()
            
            for lock_id, original_path, locked_path in expired_locks:
                if os.path.exists(original_path):
                    if os.path.isdir(original_path):
                        subprocess.run(['attrib', '+h', '+s', original_path], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                        if not os.path.exists(locked_path):
                            open(locked_path, 'a').close()
                    else:
                        os.rename(original_path, locked_path)
                
                c.execute("UPDATE file_locks SET unlock_expiry = NULL WHERE id = ?", (lock_id,))
                
                # Log event
                c.execute("INSERT INTO file_access_events (file_name, event_type, details) VALUES (?, ?, ?)", 
                          (os.path.basename(original_path), "Locked", "Geçici süre doldu, otomatik kilitlendi."))
                print(f"Auto-relocked: {original_path}")
                
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Temp locks monitor error: {e}")
            
        time.sleep(30)

def add_to_startup():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        script_path = os.path.abspath(__file__)
        winreg.SetValueEx(key, "SysMonitor", 0, winreg.REG_SZ, f'"{python_exe}" "{script_path}"')
        winreg.CloseKey(key)
        print("Added to startup.")
    except Exception as e:
        print(f"Failed to add to startup: {e}")

if __name__ == "__main__":
    init_db()
    add_to_startup()
    
    t1 = threading.Thread(target=monitor_windows, daemon=True)
    t2 = threading.Thread(target=monitor_processes, daemon=True)
    t3 = threading.Thread(target=monitor_usb_events, daemon=True)
    t4 = threading.Thread(target=monitor_temporary_locks, daemon=True)
    
    t1.start()
    t2.start()
    t3.start()
    t4.start()
    
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Exiting...")
