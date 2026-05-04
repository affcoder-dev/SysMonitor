import os
import sqlite3
import time
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psutil
from flask_socketio import SocketIO
from database import get_connection
import hashlib

app = Flask(__name__)
app.secret_key = "super_secret_sysmonitor_key_change_me_in_prod"

socketio = SocketIO(app, cors_allowed_origins="*")
thread = None

def background_system_stats():
    net_io_start = psutil.net_io_counters()
    time_start = time.time()
    while True:
        socketio.sleep(1)
        cpu_percent = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        
        time_end = time.time()
        net_io_end = psutil.net_io_counters()
        time_elapsed = time_end - time_start
        
        if time_elapsed > 0:
            up_speed = (net_io_end.bytes_sent - net_io_start.bytes_sent) / time_elapsed
            down_speed = (net_io_end.bytes_recv - net_io_start.bytes_recv) / time_elapsed
        else:
            up_speed = 0
            down_speed = 0
            
        net_io_start = net_io_end
        time_start = time_end
        
        socketio.emit('system_stats', {
            'cpu': cpu_percent,
            'ram': ram.percent,
            'upload': up_speed,
            'download': down_speed
        })
        
        # Check alerts in the last 2 seconds
        try:
            conn = get_connection()
            c = conn.cursor()
            
            c.execute("SELECT device_name FROM usb_events WHERE timestamp >= datetime('now', '-2 seconds') AND event_type='Connected'")
            for row in c.fetchall():
                socketio.emit('alert', {'type': 'usb', 'message': f'Yeni USB Bağlandı: {row[0]}'})
                
            blacklist = ['bittorrent.exe', 'utorrent.exe', 'cmd.exe']
            placeholders = ', '.join(['?'] * len(blacklist))
            c.execute(f"SELECT process_name FROM process_events WHERE timestamp >= datetime('now', '-2 seconds') AND LOWER(process_name) IN ({placeholders})", blacklist)
            for row in c.fetchall():
                socketio.emit('alert', {'type': 'warning', 'message': f'Yasaklı İşlem Tespit Edildi: {row[0]}'})
                
        except Exception as e:
            pass
        finally:
            if 'conn' in locals():
                conn.close()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    # Accept any stored admin username
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='admin_username'")
    row = c.fetchone()
    conn.close()
    if row and user_id == row[0]:
        return User(user_id)
    return None

def is_setup_complete():
    """Returns True only if setup flag is set AND real credentials exist."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='setup_complete'")
        row_flag = c.fetchone()
        c.execute("SELECT value FROM settings WHERE key='admin_username'")
        row_user = c.fetchone()
        c.execute("SELECT value FROM settings WHERE key='master_password_hash'")
        row_pwd = c.fetchone()
        conn.close()
        # ALL three must exist for setup to be considered complete
        return (row_flag and row_flag[0] == '1'
                and row_user and row_user[0]
                and row_pwd and row_pwd[0])
    except:
        return False

@app.before_request
def check_setup():
    """Redirect to setup wizard if first-run setup is not done."""
    allowed_routes = ('setup', 'static')
    if request.endpoint in allowed_routes:
        return
    if not is_setup_complete():
        return redirect(url_for('setup'))

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        return False
    global thread
    if thread is None:
        thread = socketio.start_background_task(background_system_stats)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """First-run setup wizard — creates admin username and password."""
    if is_setup_complete():
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not username:
            flash('Kullanıcı adı boş olamaz.')
        elif len(username) < 3:
            flash('Kullanıcı adı en az 3 karakter olmalıdır.')
        elif len(password) < 6:
            flash('Şifre en az 6 karakter olmalıdır.')
        elif password != password2:
            flash('Şifreler eşleşmiyor.')
        else:
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_username', ?)", (username,))
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('master_password_hash', ?)", (pwd_hash,))
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('setup_complete', '1')")
                conn.commit()
                conn.close()
                flash('Kurulum tamamlandı! Giriş yapabilirsiniz.')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'Hata: {e}')

    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        # Get stored admin username and password hash from DB
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='admin_username'")
            row_user = c.fetchone()
            c.execute("SELECT value FROM settings WHERE key='master_password_hash'")
            row_pwd = c.fetchone()
            conn.close()
        except:
            row_user = row_pwd = None

        stored_username = row_user[0] if row_user else None
        stored_hash = row_pwd[0] if row_pwd else None
        input_hash = hashlib.sha256(password.encode()).hexdigest()

        if stored_username and username == stored_username and stored_hash and input_hash == stored_hash:
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Geçersiz kullanıcı adı veya şifre.')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    filter_date = request.args.get('date') # YYYY-MM-DD
    filter_hour = request.args.get('hour') # HH
    
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query_cond = "1=1"
    params = []
    
    if filter_date:
        query_cond += " AND date(timestamp) = ?"
        params.append(filter_date)
        
    if filter_hour:
        query_cond += " AND strftime('%H', timestamp) = ?"
        params.append(filter_hour.zfill(2))
        
    try:
        c.execute(f"SELECT * FROM window_events WHERE {query_cond} ORDER BY timestamp DESC LIMIT 200", params)
        windows = [dict(row) for row in c.fetchall()]
        
        c.execute(f"SELECT * FROM process_events WHERE {query_cond} ORDER BY timestamp DESC LIMIT 200", params)
        processes = [dict(row) for row in c.fetchall()]
        
        c.execute(f"SELECT * FROM usb_events WHERE {query_cond} ORDER BY timestamp DESC LIMIT 200", params)
        usbs = [dict(row) for row in c.fetchall()]
        
        c.execute(f"SELECT * FROM file_access_events WHERE {query_cond} ORDER BY timestamp DESC LIMIT 200", params)
        file_events = [dict(row) for row in c.fetchall()]
    except Exception as e:
        print("Error fetching logs:", e)
        windows, processes, usbs, file_events = [], [], [], []
    finally:
        conn.close()
    
    return jsonify({
        'windows': windows,
        'processes': processes,
        'usb': usbs,
        'files': file_events
    })

@app.route('/api/kill/<int:pid>', methods=['POST'])
@login_required
def kill_process(pid):
    try:
        p = psutil.Process(pid)
        p.terminate()
        return jsonify({"status": "success", "message": f"PID {pid} sonlandırıldı."})
    except psutil.NoSuchProcess:
        return jsonify({"status": "error", "message": "İşlem bulunamadı."}), 404
    except psutil.AccessDenied:
        return jsonify({"status": "error", "message": "Erişim reddedildi (Yönetici izni gerekebilir)."}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/chart_data', methods=['GET'])
@login_required
def get_chart_data():
    conn = get_connection()
    c = conn.cursor()
    try:
        # Get top 5 window titles by duration today
        c.execute("""
            SELECT window_title, SUM(duration_seconds) as total_duration 
            FROM window_events 
            WHERE date(timestamp) = date('now', 'localtime')
            GROUP BY window_title 
            ORDER BY total_duration DESC 
            LIMIT 5
        """)
        top_apps = [{"title": row[0], "duration": row[1]} for row in c.fetchall()]
        return jsonify(top_apps)
    except Exception as e:
        print("Chart DB Error:", e)
        return jsonify([])
    finally:
        conn.close()

@app.route('/security')
@login_required
def security_page():
    return render_template('security.html')

@app.route('/api/browse')
@login_required
def browse_files():
    req_path = request.args.get('path', 'C:\\')
    if not os.path.exists(req_path):
        return jsonify({"error": "Dizin bulunamadı."}), 404
        
    items = []
    try:
        for entry in os.scandir(req_path):
            is_dir = entry.is_dir()
            # Don't show already locked files
            if entry.name.endswith('.sysmon_locked'):
                continue
            items.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": is_dir
            })
    except PermissionError:
        return jsonify({"error": "Erişim reddedildi."}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 400
        
    # Sort: folders first, then alphabetically
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
    
    return jsonify({
        "current_path": req_path,
        "parent_path": os.path.dirname(req_path) if req_path != os.path.dirname(req_path) else req_path,
        "items": items
    })

@app.route('/api/lock_file', methods=['POST'])
@login_required
def api_lock_file():
    data = request.json
    file_path = data.get('path')
    if not file_path or not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Geçersiz dosya/klasör yolu."}), 400
        
    locked_path = file_path + ".sysmon_locked"
    
    try:
        import subprocess
        if os.path.isdir(file_path):
            # Folder lock: hide folder, create dummy file
            subprocess.run(['attrib', '+h', '+s', file_path], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            open(locked_path, 'a').close()
            msg = f"{os.path.basename(file_path)} klasörü kilitlendi."
            detail = "Web üzerinden klasör kilitlendi."
        else:
            # File lock: rename file
            os.rename(file_path, locked_path)
            msg = f"{os.path.basename(file_path)} kilitlendi."
            detail = "Web üzerinden dosya kilitlendi."
        
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO file_locks (original_path, locked_path, password_hash) VALUES (?, ?, ?)",
                  (file_path, locked_path, 'use_master'))
        
        c.execute("INSERT INTO file_access_events (file_name, event_type, details) VALUES (?, ?, ?)", 
                  (os.path.basename(file_path), "Locked", detail))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": msg})
    except PermissionError:
        return jsonify({"status": "error", "message": "Erişim Reddedildi. C:\\ veya sistem klasörlerinde işlem yapmak için SysMonitor'ü Yönetici olarak çalıştırmalısınız."}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/locked_files')
@login_required
def get_locked_files():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, original_path, locked_path, unlock_expiry FROM file_locks")
        locks = []
        for row in c.fetchall():
            locks.append({
                "id": row[0],
                "original_path": row[1],
                "locked_path": row[2],
                "is_temp_unlocked": row[3] is not None,
                "unlock_expiry": row[3]
            })
        conn.close()
        return jsonify(locks)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/unlock_file', methods=['POST'])
@login_required
def api_unlock_file():
    data = request.json
    lock_id = data.get('id')
    password = data.get('password')
    action = data.get('action') # 'permanent' or 'temporary'
    
    if not lock_id or not password or action not in ['permanent', 'temporary']:
        return jsonify({"status": "error", "message": "Eksik veya geçersiz veri."}), 400
        
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='master_password_hash'")
        res = c.fetchone()
        master_hash = res[0] if res else hashlib.sha256("admin").hexdigest()
        
        if hashlib.sha256(password.encode()).hexdigest() != master_hash:
            return jsonify({"status": "error", "message": "Yanlış şifre."}), 403
            
        c.execute("SELECT original_path, locked_path FROM file_locks WHERE id = ?", (lock_id,))
        lock_data = c.fetchone()
        if not lock_data:
            return jsonify({"status": "error", "message": "Kilit kaydı bulunamadı."}), 404
            
        original_path, locked_path = lock_data
        import subprocess
        
        if action == 'permanent':
            if os.path.isdir(original_path) or (os.path.exists(locked_path) and os.path.getsize(locked_path) == 0):
                # Unhide folder and delete dummy file
                subprocess.run(['attrib', '-h', '-s', original_path], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                if os.path.exists(locked_path):
                    os.remove(locked_path)
            else:
                os.rename(locked_path, original_path)
                
            c.execute("DELETE FROM file_locks WHERE id = ?", (lock_id,))
            c.execute("INSERT INTO file_access_events (file_name, event_type, details) VALUES (?, ?, ?)", 
                      (os.path.basename(original_path), "Unlock_Success", "Web: Kalıcı olarak açıldı."))
            msg = "Kilit kalıcı olarak kaldırıldı."
            
        elif action == 'temporary':
            if os.path.isdir(original_path) or (os.path.exists(locked_path) and os.path.getsize(locked_path) == 0):
                # Unhide folder, keep dummy file
                subprocess.run(['attrib', '-h', '-s', original_path], check=False, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                # File: rename back, dummy file not needed here, but since it's a file, we actually rename it back.
                # However, when temp timer expires, we need to rename it again.
                os.rename(locked_path, original_path)
                
            c.execute("UPDATE file_locks SET unlock_expiry = datetime('now', '+5 minutes', 'localtime') WHERE id = ?", (lock_id,))
            c.execute("INSERT INTO file_access_events (file_name, event_type, details) VALUES (?, ?, ?)", 
                      (os.path.basename(original_path), "Unlock_Success", "Web: 5 dakikalığına açıldı."))
            msg = "5 dakikalığına geçici olarak açıldı."
            
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": msg})
    except PermissionError:
        return jsonify({"status": "error", "message": "Erişim Reddedildi. SysMonitor'ü Yönetici olarak çalıştırın."}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/settings/password', methods=['POST'])
@login_required
def update_master_password():
    data = request.json
    new_password = data.get('password')
    if not new_password:
        return jsonify({"status": "error", "message": "Şifre boş olamaz."}), 400
        
    pwd_hash = hashlib.sha256(new_password.encode()).hexdigest()
    
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('master_password_hash', pwd_hash))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Ana şifre güncellendi."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/authorized_devices', methods=['GET'])
@login_required
def get_authorized_devices():
    try:
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM authorized_devices ORDER BY timestamp DESC")
        devices = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify(devices)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/authorized_devices/<device_id>', methods=['DELETE'])
@login_required
def remove_authorized_device(device_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM authorized_devices WHERE device_id = ?", (device_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Cihaz izni kaldırıldı."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/current_devices', methods=['GET'])
@login_required
def get_current_devices():
    import subprocess
    import json
    try:
        cmd = 'powershell -Command "Get-PnpDevice -Class \'USBSTOR\', \'Mouse\', \'Keyboard\', \'HIDClass\' | Select-Object InstanceId, FriendlyName, Status, Class | ConvertTo-Json"'
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        devices = []
        if result.stdout.strip():
            data = json.loads(result.stdout)
            devices = [data] if isinstance(data, dict) else data
            
        # Add authorization status
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT device_id FROM authorized_devices")
        auth_serials = [row[0] for row in c.fetchall()]
        conn.close()
        
        for dev in devices:
            instance_id = dev.get("InstanceId", "").upper()
            serial = instance_id
            if "USBSTOR" in instance_id:
                parts = instance_id.split('#')
                serial = parts[2].split('&')[0] if len(parts) >= 3 else instance_id.split('\\')[-1].split('&')[0]
            else:
                parts = instance_id.split('\\')
                serial = parts[-1] if len(parts) >= 2 else instance_id
                
            dev['serial'] = serial
            dev['is_authorized'] = serial in auth_serials
            
        return jsonify(devices)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/authorize_device', methods=['POST'])
@login_required
def authorize_device():
    import re, subprocess
    data = request.json
    instance_id = data.get('instance_id')
    name = data.get('name', 'Bilinmeyen Cihaz')

    if not instance_id:
        return jsonify({"status": "error", "message": "Cihaz ID eksik."}), 400

    instance_id = instance_id.upper()

    # Find the USB parent device (full unique InstanceId = device fingerprint)
    vid_pid_match = re.search(r'(VID_[0-9A-F]+&PID_[0-9A-F]+)', instance_id)
    device_key = instance_id  # fallback: store what we have

    if vid_pid_match:
        vid_pid = vid_pid_match.group(1)
        ps_cmd = (
            'powershell -Command "'
            f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like 'USB\\{vid_pid}*' }} "
            '| Select-Object -First 1 -ExpandProperty InstanceId"'
        )
        try:
            res = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True,
                                 encoding='utf-8', errors='ignore',
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            if res.stdout.strip():
                device_key = res.stdout.strip().upper()  # Full USB parent InstanceId
        except:
            pass

    try:
        conn = get_connection()
        c = conn.cursor()
        # Store FULL USB parent InstanceId as device_id (unique per physical device)
        c.execute("INSERT OR REPLACE INTO authorized_devices (device_id, device_name) VALUES (?, ?)",
                  (device_key, name))
        conn.commit()
        conn.close()

        # Enable all related sub-devices by VID+PID pattern
        if vid_pid_match:
            ps_enable = (
                'powershell -Command "'
                f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like '*{vid_pid_match.group(1)}*' }} "
                '| Enable-PnpDevice -Confirm:$false"'
            )
            subprocess.run(ps_enable, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.run(f'pnputil /enable-device "{device_key}"', shell=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)

        return jsonify({"status": "success", "message": f"{name} yetkilendirildi.",
                        "stored_id": device_key})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/authorize_all_current', methods=['POST'])
@login_required
def authorize_all_current():
    import subprocess, json, re
    try:
        # Get all HID input devices with VID_ (mouse, keyboard — Status filter removed, HID shows 'Unknown')
        cmd = (
            'powershell -Command "'
            "Get-PnpDevice -Class 'Mouse', 'Keyboard', 'HIDClass' "
            "| Where-Object { $_.InstanceId -like '*VID_*' } "
            '| Select-Object InstanceId, FriendlyName | ConvertTo-Json"'
        )
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True,
                                encoding='utf-8', errors='ignore',
                                creationflags=subprocess.CREATE_NO_WINDOW)

        if not result.stdout.strip():
            return jsonify({"status": "success", "message": "Bagli aktif giris cihazi bulunamadi."})

        data = json.loads(result.stdout)
        devices = [data] if isinstance(data, dict) else data

        conn = get_connection()
        c = conn.cursor()
        added = set()

        for dev in devices:
            hid_id = (dev.get("InstanceId") or "").upper()
            name = dev.get("FriendlyName") or "Bilinmeyen Cihaz"
            if not hid_id:
                continue

            # Find the USB parent InstanceId (unique fingerprint per physical device)
            vid_pid_match = re.search(r'(VID_[0-9A-F]+&PID_[0-9A-F]+)', hid_id)
            device_key = hid_id  # fallback

            if vid_pid_match:
                vid_pid = vid_pid_match.group(1)
                ps_cmd = (
                    'powershell -Command "'
                    f"Get-PnpDevice | Where-Object {{ $_.InstanceId -like 'USB\\{vid_pid}*' }} "
                    '| Select-Object -First 1 -ExpandProperty InstanceId"'
                )
                try:
                    res = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True,
                                         encoding='utf-8', errors='ignore',
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.stdout.strip():
                        device_key = res.stdout.strip().upper()
                except:
                    pass

            if device_key not in added:
                c.execute("INSERT OR REPLACE INTO authorized_devices (device_id, device_name) VALUES (?, ?)",
                          (device_key, name))
                added.add(device_key)

        conn.commit()
        conn.close()

        return jsonify({"status": "success",
                        "message": f"{len(added)} cihaz guvenli olarak isaretlendi."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print("Starting Web UI at http://127.0.0.1:5000")
    socketio.run(app, debug=False, port=5000, allow_unsafe_werkzeug=True)
