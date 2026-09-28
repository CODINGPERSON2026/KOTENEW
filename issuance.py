from imports import *

issuance_bp = Blueprint('issuance', __name__)


@issuance_bp.route('/api/scan_barcode', methods=['GET'])
def scan_barcode_route():
    """Scans or searches weapon by barcode / register_number / butt_number.
    Returns weapon type, butt number, register number, status, and troop details if assigned."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    raw_query = request.args.get('barcode', '').strip() or request.args.get('q', '').strip() or request.args.get('num', '').strip()

    if not raw_query:
        return jsonify({'success': False, 'message': 'Barcode / Register Number is required', 'found': False})

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            # Query weapon matching register_number, butt_number, or barcode
            sql = """
                SELECT id, type, butt_number, register_number, barcode, weapon_status, alloted_to_army_number
                FROM QM_stock
                WHERE LOWER(register_number) = LOWER(%s)
                   OR LOWER(butt_number) = LOWER(%s)
                   OR LOWER(barcode) = LOWER(%s)
                   OR LOWER(register_number) LIKE LOWER(%s)
                LIMIT 1;
            """
            like_param = f"%{raw_query}%"
            cursor.execute(sql, (raw_query, raw_query, raw_query, like_param))
            weapon = cursor.fetchone()

            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({
                    'success': True,
                    'found': False,
                    'message': f'No weapon found matching Barcode / Register No: "{raw_query}"'
                })

            # Fetch troop details if allotted
            troop = None
            if weapon.get('alloted_to_army_number'):
                army_no = weapon['alloted_to_army_number']
                cursor.execute("SELECT army_number, name, rank_name, company, section FROM troops WHERE army_number = %s LIMIT 1;", (army_no,))
                t_row = cursor.fetchone()
                if t_row:
                    troop = {
                        'army_number': t_row['army_number'],
                        'name': t_row['name'],
                        'rank': t_row['rank_name'],
                        'company': t_row['company'],
                        'section': t_row['section']
                    }

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'found': True,
                'weapon': {
                    'id': weapon['id'],
                    'type': weapon['type'],
                    'butt_number': weapon['butt_number'],
                    'register_number': weapon['register_number'],
                    'barcode': weapon['barcode'] or weapon['register_number'],
                    'weapon_status': weapon['weapon_status'],
                    'alloted_to_army_number': weapon['alloted_to_army_number']
                },
                'troop': troop
            })
        except Exception as e:
            print("Error scanning barcode:", e)
            return jsonify({'success': False, 'message': str(e), 'found': False})

    return jsonify({'success': False, 'message': 'Database connection error', 'found': False})


@issuance_bp.route('/api/issue_weapon', methods=['POST'])
def api_issue_weapon():
    """OUT weapon from KOTE after Barcode & Biometric scanning.
    Updates QM_stock status to 'Issued' and records log in issuance_logs."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    register_number = request.form.get('register_number', '').strip() or request.json.get('register_number', '').strip() if request.is_json else request.form.get('register_number', '').strip()
    army_number = request.form.get('army_number', '').strip() or request.json.get('army_number', '').strip() if request.is_json else request.form.get('army_number', '').strip()
    barcode = request.form.get('barcode', '').strip() or register_number
    scan_timestamp = request.form.get('scan_timestamp', '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    biometric_status = request.form.get('biometric_status', 'Verified (Match 100%)').strip()

    if not register_number or not army_number:
        return jsonify({'success': False, 'message': 'Register Number and Army Number are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Fetch weapon details
            cursor.execute("SELECT id, type, butt_number, register_number, weapon_status FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon {register_number} not found.'}), 404

            # 2. Fetch troop details
            cursor.execute("SELECT army_number, name, rank_name, company, section FROM troops WHERE LOWER(army_number) = LOWER(%s);", (army_number,))
            troop = cursor.fetchone()
            troop_name = troop['name'] if troop else 'Personnel'
            rank_name = troop['rank_name'] if troop else ''
            company_name = troop['company'] if troop else ''

            # 3. Update QM_stock weapon_status to 'Issued'
            cursor.execute("""
                UPDATE QM_stock 
                SET weapon_status = 'Issued', alloted_to_army_number = %s 
                WHERE id = %s;
            """, (army_number, weapon['id']))

            # 4. Insert into issuance_logs
            try:
                dt_obj = datetime.strptime(scan_timestamp, '%Y-%m-%d %H:%M:%S')
            except Exception:
                dt_obj = datetime.now()

            log_sql = """
                INSERT INTO issuance_logs 
                (register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, biometric_status, action_time, operator_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'OUT', %s, %s, %s, %s);
            """
            cursor.execute(log_sql, (
                weapon['register_number'],
                weapon['butt_number'],
                weapon['type'],
                army_number,
                troop_name,
                rank_name,
                company_name,
                barcode,
                biometric_status,
                dt_obj,
                session.get('username', 'KOTE Operator')
            ))
            conn.commit()

            # 5. Fetch updated stock counts
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock;")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) != 'available';")
            issued_cnt = cursor.fetchone()['issued']

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': f'Weapon {weapon["register_number"]} (Butt #{weapon["butt_number"]}) successfully ISSUED OUT to Army No: {army_number} ({troop_name})!',
                'counts': {
                    'total': total_cnt,
                    'available': avail_cnt,
                    'issued': issued_cnt
                },
                'transaction': {
                    'register_number': weapon['register_number'],
                    'butt_number': weapon['butt_number'],
                    'weapon_type': weapon['type'],
                    'army_number': army_number,
                    'troop_name': troop_name,
                    'timestamp': dt_obj.strftime('%d %b %Y, %I:%M:%S %p'),
                    'action': 'OUT'
                }
            })
        except Exception as e:
            print("Error issuing weapon:", e)
            if conn and conn.is_connected():
                conn.rollback()
                cursor.close()
                conn.close()
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

    return jsonify({'success': False, 'message': 'Database connection failed'}), 500


@issuance_bp.route('/api/return_weapon', methods=['POST'])
def api_return_weapon():
    """RETURN weapon back to KOTE after Barcode & Biometric scanning.
    Updates QM_stock status back to 'Available' and records log in issuance_logs."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    register_number = request.form.get('register_number', '').strip() or (request.json.get('register_number', '').strip() if request.is_json else '')
    barcode = request.form.get('barcode', '').strip() or register_number
    scan_timestamp = request.form.get('scan_timestamp', '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    biometric_status = request.form.get('biometric_status', 'Verified (Match 100%)').strip()

    if not register_number:
        return jsonify({'success': False, 'message': 'Register Number is required for return.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)

            # 1. Fetch weapon details
            cursor.execute("SELECT id, type, butt_number, register_number, weapon_status, alloted_to_army_number FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon {register_number} not found.'}), 404

            army_number = weapon.get('alloted_to_army_number') or 'N/A'
            troop_name = 'Personnel'
            rank_name = ''
            company_name = ''

            if army_number and army_number != 'N/A':
                cursor.execute("SELECT army_number, name, rank_name, company FROM troops WHERE LOWER(army_number) = LOWER(%s);", (army_number,))
                t_row = cursor.fetchone()
                if t_row:
                    troop_name = t_row['name']
                    rank_name = t_row['rank_name']
                    company_name = t_row['company']

            # 2. Update QM_stock weapon_status to 'Available' and clear alloted_to_army_number
            cursor.execute("""
                UPDATE QM_stock 
                SET weapon_status = 'Available', alloted_to_army_number = NULL 
                WHERE id = %s;
            """, (weapon['id'],))

            # 3. Insert into issuance_logs
            try:
                dt_obj = datetime.strptime(scan_timestamp, '%Y-%m-%d %H:%M:%S')
            except Exception:
                dt_obj = datetime.now()

            log_sql = """
                INSERT INTO issuance_logs 
                (register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, biometric_status, action_time, operator_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'RETURN', %s, %s, %s, %s);
            """
            cursor.execute(log_sql, (
                weapon['register_number'],
                weapon['butt_number'],
                weapon['type'],
                army_number,
                troop_name,
                rank_name,
                company_name,
                barcode,
                biometric_status,
                dt_obj,
                session.get('username', 'KOTE Operator')
            ))
            conn.commit()

            # 4. Fetch updated stock counts
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock;")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) != 'available';")
            issued_cnt = cursor.fetchone()['issued']

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': f'Weapon {weapon["register_number"]} (Butt #{weapon["butt_number"]}) RETURNED successfully to KOTE Armory!',
                'counts': {
                    'total': total_cnt,
                    'available': avail_cnt,
                    'issued': issued_cnt
                },
                'transaction': {
                    'register_number': weapon['register_number'],
                    'butt_number': weapon['butt_number'],
                    'weapon_type': weapon['type'],
                    'army_number': army_number,
                    'troop_name': troop_name,
                    'timestamp': dt_obj.strftime('%d %b %Y, %I:%M:%S %p'),
                    'action': 'RETURN'
                }
            })
        except Exception as e:
            print("Error returning weapon:", e)
            if conn and conn.is_connected():
                conn.rollback()
                cursor.close()
                conn.close()
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

    return jsonify({'success': False, 'message': 'Database connection failed'}), 500


@issuance_bp.route('/api/issuance_logs', methods=['GET'])
def api_issuance_logs():
    """Returns recent weapon issuance & return logs."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    conn = get_db_connection()
    logs = []
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, biometric_status, action_time, operator_username
                FROM issuance_logs
                ORDER BY id DESC LIMIT 50;
            """)
            rows = cursor.fetchall()
            for r in rows:
                action_dt = r['action_time']
                dt_str = action_dt.strftime('%d %b %Y, %I:%M:%S %p') if isinstance(action_dt, datetime) else str(action_dt)
                logs.append({
                    'id': r['id'],
                    'register_number': r['register_number'],
                    'butt_number': r['butt_number'],
                    'weapon_type': r['weapon_type'],
                    'army_number': r['army_number'] or 'N/A',
                    'troop_name': r['troop_name'] or 'N/A',
                    'rank_name': r['rank_name'] or '',
                    'company': r['company'] or '',
                    'action_type': r['action_type'],
                    'barcode': r['barcode'] or r['register_number'],
                    'biometric_status': r['biometric_status'] or 'Verified',
                    'action_time': dt_str,
                    'operator': r['operator_username'] or 'KOTE Operator'
                })
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'logs': logs})
        except Exception as e:
            print("Error loading issuance logs:", e)
            return jsonify({'success': False, 'message': str(e), 'logs': []})

    return jsonify({'success': False, 'logs': []})


@issuance_bp.route('/api/sample_barcodes', methods=['GET'])
def api_sample_barcodes():
    """Returns a list of available and issued weapon barcodes for easy test scanning."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    conn = get_db_connection()
    weapons = []
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT register_number, butt_number, type, weapon_status FROM QM_stock ORDER BY register_number ASC LIMIT 20;")
            rows = cursor.fetchall()
            for r in rows:
                weapons.append({
                    'register_number': r['register_number'],
                    'butt_number': r['butt_number'],
                    'type': r['type'],
                    'status': r['weapon_status']
                })
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'weapons': weapons})
        except Exception as e:
            print("Error fetching sample barcodes:", e)
            return jsonify({'success': False, 'weapons': []})

    return jsonify({'success': False, 'weapons': []})


@issuance_bp.route('/api/detect_biometric_device', methods=['GET'])
def api_detect_biometric_device():
    """Detects physically connected biometric fingerprint devices on Windows system & RD Services."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    import subprocess
    import json
    import urllib.request

    devices = []
    rd_services = []

    # 1. Check Windows PnP Device Manager for physical USB Biometric / HID 4500 hardware
    try:
        ps_cmd = (
            'Get-PnpDevice -PresentOnly | '
            'Where-Object { $_.Class -eq "Biometric" -or $_.FriendlyName -like "*DigitalPersona*" -or $_.FriendlyName -like "*U.are.U*" -or $_.FriendlyName -like "*4500*" -or $_.FriendlyName -like "*Fingerprint*" -or $_.FriendlyName -like "*Mantra*" -or $_.FriendlyName -like "*Morpho*" -or $_.FriendlyName -like "*SecuGen*" -or $_.InstanceId -like "*VID_05BA*" } | '
            'Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Json'
        )
        res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                d_name = item.get('FriendlyName') or 'HID DigitalPersona 4500 Fingerprint Reader'
                if '05BA' in str(item.get('InstanceId')) or 'DigitalPersona' in d_name or '4500' in d_name:
                    d_name = 'HID DigitalPersona 4500 Optical Fingerprint Reader (VID:05BA)'
                devices.append({
                    'name': d_name,
                    'status': item.get('Status') or 'OK',
                    'instance_id': item.get('InstanceId')
                })
    except Exception as e:
        print("Notice scanning PnpDevice:", e)

    # 2. Check local RD Service & DigitalPersona Web SDK ports (8000, 11100, 11101, 8088)
    rd_ports = [
        ('8000', 'DigitalPersona Web SDK / One Touch Agent'),
        ('11100', 'Mantra MFS100 RD Service'),
        ('11101', 'Morpho / Mantra SSL RD Service'),
        ('8088', 'SecuGen / DigitalPersona RD Service'),
        ('8085', 'Startek RD Service')
    ]
    for port, label in rd_ports:
        try:
            url = f"http://127.0.0.1:{port}/"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=0.6) as resp:
                if resp.status in [200, 404, 403, 400]:
                    rd_services.append({
                        'port': port,
                        'name': label,
                        'status': 'READY'
                    })
        except Exception:
            pass

    found = len(devices) > 0 or len(rd_services) > 0

    return jsonify({
        'success': True,
        'detected': found,
        'devices': devices,
        'rd_services': rd_services,
        'message': f"Detected {len(devices)} physical biometric device(s) and {len(rd_services)} RD Service(s)." if found else "No physical biometric device detected on USB ports or RD Services."
    })

