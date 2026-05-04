import subprocess, json, sqlite3, os, sys
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'sysmonitor.db')

def get_serial(instance_id):
    id_upper = instance_id.upper()
    if 'USBSTOR' in id_upper:
        parts = id_upper.split('#')
        if len(parts) >= 3:
            return parts[2].split('&')[0]
        return id_upper.split('\\')[-1].split('&')[0]
    parts = id_upper.split('\\')
    if len(parts) >= 2:
        return parts[-1]
    return id_upper

# Get authorized serials from DB
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('SELECT device_id, device_name FROM authorized_devices')
authorized = c.fetchall()
authorized_serials = [row[0] for row in authorized]
conn.close()

print('=== AUTHORIZED DEVICES IN DB ===')
for dev_id, dev_name in authorized:
    print(f'  {dev_id}  |  {dev_name}')
print()

# Run same PowerShell command as logger.py
cmd = (
    'powershell -Command "'
    "Get-PnpDevice -Class 'USBSTOR', 'Mouse', 'Keyboard', 'HIDClass' "
    '| Select-Object InstanceId, Status, ConfigManagerErrorCode, Class, FriendlyName '
    '| ConvertTo-Json"'
)
result = subprocess.run(cmd, capture_output=True, text=True, shell=True,
                        encoding='utf-8', errors='ignore',
                        creationflags=subprocess.CREATE_NO_WINDOW)

if not result.stdout.strip():
    print("PowerShell output bos geldi! Hata:", result.stderr[:500])
    exit()

try:
    data = json.loads(result.stdout)
    if isinstance(data, dict):
        data = [data]
except Exception as e:
    print("JSON parse hatasi:", e)
    print("Raw output:", result.stdout[:500])
    exit()

print(f'=== USB SCAN RESULT ({len(data)} cihaz bulundu) ===')
popup_needed = []
for dev in data:
    instance_id = dev.get('InstanceId', '').upper()
    if not instance_id:
        continue

    status = dev.get('Status', 'Unknown')
    error_code = dev.get('ConfigManagerErrorCode', 0)
    friendly = dev.get('FriendlyName') or dev.get('Class') or 'Unknown'

    # Same skip logic as logger.py
    is_hid_or_mouse = any(x in instance_id for x in ['HID\\', 'USB\\VID_'])
    if status == 'Unknown' and error_code == 45 and not is_hid_or_mouse:
        continue
    if status == 'Unknown' and error_code == 45 and not any(x in instance_id for x in ['VID_', 'USB\\ROOT', 'USBSTOR']):
        continue

    # Authorization check
    serial = get_serial(instance_id)
    is_authorized = any(s == serial or s in instance_id for s in authorized_serials)

    if is_authorized:
        verdict = '[OK] AUTHORIZED'
    else:
        verdict = '[!!] UNKNOWN -> POPUP CIKMALI'
        popup_needed.append(friendly)

    print(f'  [{verdict}] {friendly}')
    print(f'    InstanceId : {instance_id[:90]}')
    print(f'    Status={status}, ErrCode={error_code}')
    print(f'    Serial extracted: {serial[:50]}')
    print()

print('=== ÖZET ===')
if popup_needed:
    print(f'  Popup çıkması gereken {len(popup_needed)} cihaz var:')
    for n in popup_needed:
        print(f'    - {n}')
    print()
    print('  EĞER POPUP ÇIKMADIYSA: logger.py yeniden başlatılmadı veya mutex sorunu var.')
else:
    print('  Tüm cihazlar ya yetkili ya da skip ediliyor — popup beklenmez.')
