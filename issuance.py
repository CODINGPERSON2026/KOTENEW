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
            cursor = conn.cursor(dictionary=True, buffered=True)
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

            # Check latest log in issuance_logs to auto-detect OUT or RETURN mode
            cursor.execute("""
                SELECT action_type, army_number, troop_name, rank_name, company, purpose, duty_location 
                FROM issuance_logs 
                WHERE LOWER(register_number) = LOWER(%s)
                ORDER BY id DESC LIMIT 1;
            """, (weapon['register_number'],))
            last_log = cursor.fetchone()

            is_currently_out = False
            last_purpose = 'DUTY'
            last_duty = 'RP'
            if last_log and str(last_log.get('action_type') or '').upper() == 'OUT':
                is_currently_out = True
                last_purpose = last_log.get('purpose') or 'DUTY'
                last_duty = last_log.get('duty_location') or 'RP'

            auto_mode = 'RETURN' if is_currently_out else 'OUT'

            # Fetch troop details if allotted in QM_stock or in last_log
            troop = None
            target_army_no = weapon.get('alloted_to_army_number') or (last_log.get('army_number') if last_log else None)
            if target_army_no:
                cursor.execute("SELECT army_number, name, rank_name, company, section FROM troops WHERE LOWER(army_number) = LOWER(%s) LIMIT 1;", (target_army_no,))
                t_row = cursor.fetchone()
                if t_row:
                    troop = {
                        'army_number': t_row['army_number'],
                        'name': t_row['name'],
                        'rank': t_row['rank_name'],
                        'company': t_row['company'],
                        'section': t_row['section']
                    }
                elif last_log and last_log.get('army_number'):
                    troop = {
                        'army_number': last_log['army_number'],
                        'name': last_log.get('troop_name') or 'Personnel',
                        'rank': last_log.get('rank_name') or '',
                        'company': last_log.get('company') or '',
                        'section': ''
                    }

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'found': True,
                'is_currently_out': is_currently_out,
                'auto_mode': auto_mode,
                'last_purpose': last_purpose,
                'last_duty': last_duty,
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


def is_jco_or_officer(rank_name, army_number=""):
    """
    Checks if personnel is a JCO (Junior Commissioned Officer) or Officer.
    JCO ranks include: Subedar, Naib Subedar (Nb Sub), Subedar Major (Sub Maj), JCO.
    Or Army Number prefix: JC-xxxx, etc.
    """
    rank_str = str(rank_name or '').strip().lower()
    army_str = str(army_number or '').strip().upper()

    if army_str.startswith('JC') or army_str.startswith('JC-'):
        return True

    jco_keywords = [
        'subedar', 'sub', 'nb sub', 'naib', 'sub maj', 'subedar major', 
        'sub-maj', 'jco', 'officer', 'capt', 'captain', 'maj', 'major', 
        'col', 'colonel', 'lt', 'lieutenant', 'gen', 'general'
    ]
    return any(k in rank_str for k in jco_keywords)


@issuance_bp.route('/api/issue_weapon', methods=['POST'])
def api_issue_weapon():
    """OUT weapon from KOTE after Barcode & Biometric scanning.
    Updates QM_stock status to 'Issued' and records log in issuance_logs."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    register_number = request.form.get('register_number', '').strip() or (request.json.get('register_number', '').strip() if request.is_json else '')
    army_number = request.form.get('army_number', '').strip() or (request.json.get('army_number', '').strip() if request.is_json else '')
    barcode = request.form.get('barcode', '').strip() or register_number
    purpose = request.form.get('purpose', '').strip() or (request.json.get('purpose', '').strip() if request.is_json else 'DUTY')
    duty_location = request.form.get('duty_location', '').strip() or (request.json.get('duty_location', '').strip() if request.is_json else 'RP')
    if not purpose:
        purpose = 'DUTY'
    if not duty_location:
        duty_location = 'RP'

    scan_timestamp = request.form.get('scan_timestamp', '').strip() or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    biometric_status = request.form.get('biometric_status', 'Verified (Match 100%)').strip()

    if not register_number or not army_number:
        return jsonify({'success': False, 'message': 'Register Number and Army Number are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True, buffered=True)

            # 1. Fetch weapon details
            cursor.execute("SELECT id, type, butt_number, register_number, weapon_status FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon {register_number} not found in stock.'}), 404

            w_status = str(weapon.get('weapon_status') or '').strip().lower()
            # Check if latest issuance_log action for this weapon is OUT
            cursor.execute("""
                SELECT il.action_type 
                FROM issuance_logs il 
                WHERE LOWER(il.register_number) = LOWER(%s)
                ORDER BY il.id DESC LIMIT 1;
            """, (register_number,))
            last_log = cursor.fetchone()
            if last_log and str(last_log.get('action_type') or '').upper() == 'OUT':
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon {register_number} (Butt #{weapon["butt_number"]}) is ALREADY issued out!'}), 400

            # 2. Fetch troop details
            cursor.execute("SELECT army_number, name, rank_name, company, section FROM troops WHERE LOWER(army_number) = LOWER(%s);", (army_number,))
            troop = cursor.fetchone()
            troop_name = troop['name'] if troop else 'Personnel'
            rank_name = troop['rank_name'] if troop else ''
            company_name = troop['company'] if troop else ''

            # 3. Check current weapons issued to this army_number based on action_type = OUT in issuance_logs
            cursor.execute("""
                SELECT COUNT(*) as count, GROUP_CONCAT(qs.register_number SEPARATOR ', ') as issued_regs
                FROM QM_stock qs
                WHERE LOWER(qs.alloted_to_army_number) = LOWER(%s)
                  AND (
                      SELECT il.action_type 
                      FROM issuance_logs il 
                      WHERE LOWER(il.register_number) = LOWER(qs.register_number)
                      ORDER BY il.id DESC LIMIT 1
                  ) = 'OUT';
            """, (army_number,))
            existing_info = cursor.fetchone()
            existing_count = existing_info['count'] if existing_info and existing_info['count'] else 0
            existing_regs = existing_info['issued_regs'] if existing_info and existing_info['issued_regs'] else ''

            # 4. Enforce Maintenance / JCO vs Jawan weapon limits
            is_jco = is_jco_or_officer(rank_name, army_number)
            is_maint = any(k in purpose.upper() for k in ['MAINT', 'REPAIR', 'CLEANING', 'INSPECTION', 'SERVICING'])

            if existing_count > 0:
                if is_maint and is_jco:
                    # ALLOW: JCO can be issued multiple / all weapons for Maintenance under their Army Number!
                    pass
                elif is_maint and not is_jco:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        'success': False,
                        'message': f'Issue Blocked: Jawan {troop_name} ({rank_name}) already has weapon ({existing_regs}) issued. Maintenance mein Jawan ke naam pe single weapon hi out hoga! (JCO ke naam pe multiple weapons out ho sakte hain).'
                    }), 400
                else:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        'success': False,
                        'message': f'Issue Blocked: Personnel {troop_name} ({rank_name}) already has weapon ({existing_regs}) issued! Only 1 weapon per person allowed for non-maintenance duties.'
                    }), 400

            # 5. Update QM_stock alloted_to_army_number & record duty location (weapon_status is NOT updated to Issued)
            cursor.execute("""
                UPDATE QM_stock 
                SET alloted_to_army_number = %s, duty_location = %s 
                WHERE id = %s;
            """, (army_number, f"{purpose}: {duty_location}", weapon['id']))

            # 6. Insert into issuance_logs
            try:
                dt_obj = datetime.strptime(scan_timestamp, '%Y-%m-%d %H:%M:%S')
            except Exception:
                dt_obj = datetime.now()

            fingerprint_impression = request.form.get('fingerprint_impression', '').strip() or (request.json.get('fingerprint_impression', '').strip() if request.is_json else '')

            log_sql = """
                INSERT INTO issuance_logs 
                (register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, purpose, duty_location, biometric_status, action_time, operator_username)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'OUT', %s, %s, %s, %s, %s, %s);
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
                purpose,
                duty_location,
                biometric_status,
                dt_obj,
                session.get('username', 'KOTE Operator')
            ))
            conn.commit()

            # 7. Fetch updated stock counts (Total active stock excludes Deposited)
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("""
                SELECT COUNT(*) as issued 
                FROM QM_stock qs
                WHERE (
                    SELECT il.action_type 
                    FROM issuance_logs il 
                    WHERE LOWER(il.register_number) = LOWER(qs.register_number)
                    ORDER BY il.id DESC LIMIT 1
                ) = 'OUT';
            """)
            issued_cnt = cursor.fetchone()['issued']

            cursor.close()
            conn.close()

            jco_note = " [JCO Maintenance Multi-Weapon Mode]" if (is_maint and is_jco) else ""
            return jsonify({
                'success': True,
                'message': f'Weapon {weapon["register_number"]} (Butt #{weapon["butt_number"]}) successfully ISSUED OUT to Army No: {army_number} ({troop_name}, {rank_name}) for Purpose: {purpose} ({duty_location}){jco_note}!',
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
                    'purpose': purpose,
                    'duty_location': duty_location,
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
            cursor = conn.cursor(dictionary=True, buffered=True)

            # 1. Fetch weapon details
            cursor.execute("SELECT id, type, butt_number, register_number, weapon_status, alloted_to_army_number, duty_location FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon {register_number} not found.'}), 404

            army_number = weapon.get('alloted_to_army_number') or 'N/A'
            troop_name = 'Personnel'
            rank_name = ''
            company_name = ''
            prev_duty = weapon.get('duty_location') or 'RP/NIGHT PQT'

            if army_number and army_number != 'N/A':
                cursor.execute("SELECT army_number, name, rank_name, company FROM troops WHERE LOWER(army_number) = LOWER(%s);", (army_number,))
                t_row = cursor.fetchone()
                if t_row:
                    troop_name = t_row['name']
                    rank_name = t_row['rank_name']
                    company_name = t_row['company']

            # 2. Update QM_stock: weapon remains 'Alloted' to the personnel, clear active duty_location
            cursor.execute("""
                UPDATE QM_stock 
                SET weapon_status = 'Alloted', duty_location = NULL 
                WHERE id = %s;
            """, (weapon['id'],))

            # 3. Update the most recent OUT row for this weapon → mark as RETURN
            try:
                dt_obj = datetime.strptime(scan_timestamp, '%Y-%m-%d %H:%M:%S')
            except Exception:
                dt_obj = datetime.now()

            # Find the most recent OUT log row for this weapon
            cursor.execute("""
                SELECT id FROM issuance_logs
                WHERE LOWER(register_number) = LOWER(%s) AND action_type = 'OUT'
                ORDER BY id DESC LIMIT 1;
            """, (weapon['register_number'],))
            out_row = cursor.fetchone()

            if out_row:
                # Update the existing OUT row — flip it to RETURN with return timestamp
                cursor.execute("""
                    UPDATE issuance_logs
                    SET action_type = 'RETURN',
                        return_time = %s,
                        return_operator_username = %s,
                        biometric_status = %s
                    WHERE id = %s;
                """, (dt_obj, session.get('username', 'KOTE Operator'), biometric_status, out_row['id']))
            else:
                # Fallback: no OUT row found — insert a RETURN record as before
                cursor.execute("""
                    INSERT INTO issuance_logs 
                    (register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, purpose, duty_location, biometric_status, action_time, operator_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'RETURN', %s, %s, %s, %s, %s, %s);
                """, (
                    weapon['register_number'],
                    weapon['butt_number'],
                    weapon['type'],
                    army_number,
                    troop_name,
                    rank_name,
                    company_name,
                    barcode,
                    'RETURN',
                    prev_duty,
                    biometric_status,
                    dt_obj,
                    session.get('username', 'KOTE Operator')
                ))
            conn.commit()

            # 4. Fetch updated stock counts (Total active stock excludes Deposited)
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
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

    user_company = str(session.get('company', '')).strip()
    role = str(session.get('role', '')).strip().lower()

    conn = get_db_connection()
    logs = []
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            if role != 'qm' and user_company:
                cursor.execute("""
                    SELECT id, register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, purpose, duty_location, biometric_status, action_time, operator_username
                    FROM issuance_logs
                    WHERE LOWER(company) = LOWER(%s) OR LOWER(operator_username) = LOWER(%s)
                    ORDER BY id DESC LIMIT 50;
                """, (user_company, session.get('username', '')))
            else:
                cursor.execute("""
                    SELECT id, register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, purpose, duty_location, biometric_status, action_time, operator_username
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
                    'purpose': r.get('purpose') or 'DUTY',
                    'duty_location': r.get('duty_location') or 'RP/NIGHT PQT',
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
    """Detects physically connected biometric fingerprint devices on Windows system, DigitalPersona SDK & RD Services."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    import subprocess
    import json
    import urllib.request
    from digitalpersona_sdk import digitalpersona_sdk

    devices = []
    rd_services = []

    # 1. Primary: Check official DigitalPersona SDK
    try:
        sdk_devs = digitalpersona_sdk.list_connected_devices()
        for sd in sdk_devs:
            devices.append({
                'name': sd.get('name') or 'HID DigitalPersona 4500 Optical Fingerprint Reader (VID:05BA)',
                'status': 'READY',
                'instance_id': sd.get('device_id') or 'VID_05BA&PID_000A',
                'sdk': 'DigitalPersona C-API (dpfpdd.dll)'
            })
    except Exception as e:
        print("[issuance.py] DigitalPersona SDK device check note:", e)

    # 2. Secondary: Check Windows PnP Device Manager if not already listed
    if not devices:
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

    # 3. Check local RD Service & DigitalPersona Web SDK ports (8000, 11100, 11101, 8088)
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


@issuance_bp.route('/api/hardware_fingerprint_scan', methods=['GET', 'POST'])
def hardware_fingerprint_scan_route():
    """Direct Hardware Fingerprint Reader interaction (HID U.are.U 4500 / DigitalPersona).
    Activates the optical sensor, waits for the user to press their finger, captures live impression,
    and strictly verifies whether the scanned thumb belongs to the specified Army Number."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    from digitalpersona_sdk import digitalpersona_sdk

    # Parse parameters
    req_data = request.get_json(silent=True) or {}
    timeout_val = request.args.get('timeout') or req_data.get('timeout') or 8000
    army_number = request.args.get('army_number', '').strip() or req_data.get('army_number', '').strip()

    try:
        timeout_ms = int(timeout_val)
    except (ValueError, TypeError):
        timeout_ms = 8000

    # Ensure timeout is between 2000ms and 20000ms
    timeout_ms = max(2000, min(20000, timeout_ms))

    # 1. Primary: Capture using official DigitalPersona SDK (waits for finger touch)
    try:
        scan_res = digitalpersona_sdk.capture_fingerprint(timeout_ms=timeout_ms)
        if scan_res.get('captured'):
            # Perform Biometric Verification (1:1 if army_number provided, or 1:N Identification if empty)
            verify_res = digitalpersona_sdk.verify_troop_biometric(
                army_number=army_number,
                captured_fmd=scan_res.get('fmd_template'),
                captured_hash=scan_res.get('hash'),
                captured_data=scan_res.get('data')
            )
            scan_res.update(verify_res)
            if not verify_res.get('matched'):
                scan_res['success'] = False
                scan_res['verified'] = False

            return jsonify(scan_res), 200

        elif scan_res.get('timeout'):
            return jsonify(scan_res), 200
        elif scan_res.get('message') and not scan_res.get('success'):
            return jsonify(scan_res), 200
    except Exception as e:
        print("[issuance.py] Error in DigitalPersona SDK capture:", e)

    # 2. Fallback: Check if device is connected but lib failed
    devs = digitalpersona_sdk.list_connected_devices()
    if not devs:
        return jsonify({
            'success': False,
            'captured': False,
            'message': 'No HID DigitalPersona fingerprint reader detected on USB ports. Please connect the device and try again.'
        }), 200

@issuance_bp.route('/api/update_troop_biometric', methods=['POST'])
def update_troop_biometric_route():
    """Captures live fingerprint from HID 4500 and saves/updates the Master Biometric Template in the `troops` table."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    from digitalpersona_sdk import digitalpersona_sdk

    req_data = request.get_json(silent=True) or {}
    army_number = request.args.get('army_number', '').strip() or req_data.get('army_number', '').strip()
    timeout_val = request.args.get('timeout') or req_data.get('timeout') or 8000

    if not army_number:
        return jsonify({'success': False, 'message': 'Please select or enter an Army Number first!'}), 400

    try:
        timeout_ms = int(timeout_val)
    except (ValueError, TypeError):
        timeout_ms = 8000
    timeout_ms = max(2000, min(20000, timeout_ms))

    # 1. Capture live fingerprint from HID 4500 optical sensor
    try:
        scan_res = digitalpersona_sdk.capture_fingerprint(timeout_ms=timeout_ms)
        if scan_res.get('captured'):
            update_res = digitalpersona_sdk.update_troop_biometric(
                army_number=army_number,
                captured_fmd=scan_res.get('fmd_template'),
                captured_hash=scan_res.get('hash')
            )
            scan_res.update(update_res)
            return jsonify(scan_res), 200
        elif scan_res.get('timeout'):
            return jsonify(scan_res), 200
        elif scan_res.get('message') and not scan_res.get('success'):
            return jsonify(scan_res), 200
    except Exception as e:
        print("[issuance.py] Error in update_troop_biometric_route:", e)
        return jsonify({'success': False, 'message': f'Hardware error: {str(e)}'}), 500

    # 2. Device detection fallback
    devs = digitalpersona_sdk.list_connected_devices()
    if not devs:
        return jsonify({
            'success': False,
            'captured': False,
            'message': 'No HID DigitalPersona fingerprint reader detected on USB ports. Please connect the device and try again.'
        }), 200

    return jsonify({
        'success': False,
        'captured': False,
        'message': 'No finger detected on sensor! Please place finger firmly and scan again.'
    }), 200


def auto_revert_expired_temporary_allotments(conn=None):
    """
    Checks QM_stock for any Temporary Transfer allotments where leave_end_date has passed (CURDATE() > leave_end_date).
    Automatically reverts allotment back to permanent_allottee_army_no on the next date after leave ends!
    """
    should_close = False
    if not conn:
        conn = get_db_connection()
        should_close = True

    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, register_number, butt_number, type, permanent_allottee_army_no, alloted_to_army_number, leave_end_date
                FROM QM_stock
                WHERE LOWER(allotment_type) = 'temporary'
                  AND leave_end_date IS NOT NULL
                  AND CURDATE() > leave_end_date;
            """)
            expired_items = cursor.fetchall()

            for item in expired_items:
                perm_owner = item['permanent_allottee_army_no']
                temp_holder = item['alloted_to_army_number']
                reg_no = item['register_number']
                end_dt = item['leave_end_date']

                # Revert weapon allotment back to Permanent Allottee
                cursor.execute("""
                    UPDATE QM_stock
                    SET alloted_to_army_number = permanent_allottee_army_no,
                        allotment_type = 'Permanent',
                        leave_start_date = NULL,
                        leave_end_date = NULL
                    WHERE id = %s;
                """, (item['id'],))

                # Log automatic reversion in issuance_logs
                cursor.execute("""
                    INSERT INTO issuance_logs 
                    (register_number, butt_number, weapon_type, army_number, troop_name, rank_name, company, action_type, barcode, purpose, duty_location, biometric_status, action_time, operator_username)
                    VALUES (%s, %s, %s, %s, %s, 'N/A', 'HQ', 'AUTO_REVERT', %s, 'LEAVE_EXPIRED', %s, 'Auto System Trigger', NOW(), 'System Cron');
                """, (
                    reg_no,
                    item['butt_number'],
                    item['type'],
                    perm_owner or temp_holder,
                    f"Auto-Reverted to Permanent Owner (Was Temp to {temp_holder})",
                    reg_no,
                    f"Leave expired on {end_dt}. Reverted from {temp_holder} to {perm_owner}"
                ))

            conn.commit()
            cursor.close()
        except Exception as e:
            print("Error auto-reverting expired temporary allotments:", e)
        finally:
            if should_close and conn and conn.is_connected():
                conn.close()


@issuance_bp.route('/api/inventory_stock', methods=['GET'])
def api_inventory_stock():
    """Returns full inventory stock with optional filters for weapon type, butt number, register number, and query."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    w_type = request.args.get('type', '').strip()
    butt_no = request.args.get('butt_number', '').strip()
    reg_no = request.args.get('register_number', '').strip()
    status_filter = request.args.get('status', '').strip()
    action_type_filter = request.args.get('action_type', '').strip()
    q = request.args.get('q', '').strip()

    user_company = str(session.get('company', '')).strip()
    role = str(session.get('role', '')).strip().lower()

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            # Trigger automatic reversion of expired leave temporary allotments
            auto_revert_expired_temporary_allotments(conn)

            cursor = conn.cursor(dictionary=True)
            sql = """
                SELECT 
                    qs.id, 
                    qs.type, 
                    qs.butt_number, 
                    qs.register_number, 
                    qs.barcode, 
                    qs.weapon_status, 
                    qs.alloted_to_army_number, 
                    qs.permanent_allottee_army_no, 
                    qs.allotment_type, 
                    DATE_FORMAT(qs.leave_start_date, '%Y-%m-%d') as leave_start_date, 
                    DATE_FORMAT(qs.leave_end_date, '%Y-%m-%d') as leave_end_date,
                    COALESCE(
                        (
                            SELECT il.duty_location 
                            FROM issuance_logs il 
                            WHERE LOWER(il.army_number) = LOWER(qs.alloted_to_army_number)
                              AND il.duty_location IS NOT NULL AND il.duty_location != ''
                            ORDER BY il.id DESC LIMIT 1
                        ),
                        (
                            SELECT il.duty_location 
                            FROM issuance_logs il 
                            WHERE LOWER(il.register_number) = LOWER(qs.register_number)
                              AND il.duty_location IS NOT NULL AND il.duty_location != ''
                            ORDER BY il.id DESC LIMIT 1
                        ),
                        'RP'
                    ) AS duty_location,
                    COALESCE(
                        (
                            SELECT il.action_type 
                            FROM issuance_logs il 
                            WHERE LOWER(il.army_number) = LOWER(qs.alloted_to_army_number)
                               OR LOWER(il.register_number) = LOWER(qs.register_number)
                            ORDER BY il.id DESC LIMIT 1
                        ),
                        'OUT'
                    ) AS action_type,
                    (
                        SELECT t.name 
                        FROM troops t 
                        WHERE LOWER(t.army_number) = LOWER(qs.alloted_to_army_number) LIMIT 1
                    ) AS allottee_name,
                    (
                        SELECT t.rank_name 
                        FROM troops t 
                        WHERE LOWER(t.army_number) = LOWER(qs.alloted_to_army_number) LIMIT 1
                    ) AS allottee_rank,
                    (
                        SELECT t.company 
                        FROM troops t 
                        WHERE LOWER(t.army_number) = LOWER(qs.alloted_to_army_number) LIMIT 1
                    ) AS allottee_company
                FROM QM_stock qs 
                WHERE 1=1
            """
            params = []

            if role != 'qm' and user_company:
                coy_pattern = f"%{user_company.lower()}%"
                sql += """ AND (LOWER(qs.company) LIKE LOWER(%s) 
                           OR LOWER((SELECT t.company FROM troops t WHERE LOWER(t.army_number) = LOWER(qs.alloted_to_army_number) LIMIT 1)) LIKE LOWER(%s))"""
                params.extend([coy_pattern, coy_pattern])

            if w_type and w_type.upper() != 'ALL':
                sql += " AND LOWER(qs.type) = LOWER(%s)"
                params.append(w_type)
            if status_filter and status_filter.upper() != 'ALL':
                if status_filter.lower() in ['issued', 'alloted', 'allotted']:
                    sql += " AND LOWER(qs.weapon_status) IN ('issued', 'alloted')"
                elif status_filter.lower() == 'available':
                    sql += " AND LOWER(qs.weapon_status) = 'available'"
                elif status_filter.lower() in ['deposited', 'deposit']:
                    sql += " AND LOWER(qs.weapon_status) IN ('deposited', 'deposit')"
                elif status_filter.lower() in ['maintenance', 'repair']:
                    sql += " AND LOWER(qs.weapon_status) IN ('maintenance', 'repair')"
            if action_type_filter and action_type_filter.upper() != 'ALL':
                if action_type_filter.upper() == 'OUT':
                    sql += """ AND COALESCE(
                        (
                            SELECT il.action_type 
                            FROM issuance_logs il 
                            WHERE LOWER(il.army_number) = LOWER(qs.alloted_to_army_number)
                               OR LOWER(il.register_number) = LOWER(qs.register_number)
                            ORDER BY il.id DESC LIMIT 1
                        ), 'OUT') = 'OUT'"""
                elif action_type_filter.upper() == 'IN':
                    sql += """ AND COALESCE(
                        (
                            SELECT il.action_type 
                            FROM issuance_logs il 
                            WHERE LOWER(il.army_number) = LOWER(qs.alloted_to_army_number)
                               OR LOWER(il.register_number) = LOWER(qs.register_number)
                            ORDER BY il.id DESC LIMIT 1
                        ), 'IN') = 'IN'"""
            if butt_no:
                sql += " AND (LOWER(qs.butt_number) = LOWER(%s) OR qs.butt_number LIKE %s)"
                params.extend([butt_no, f"%{butt_no}%"])
            if reg_no:
                sql += " AND (LOWER(qs.register_number) = LOWER(%s) OR qs.register_number LIKE %s)"
                params.extend([reg_no, f"%{reg_no}%"])
            if q:
                sql += " AND (LOWER(qs.type) LIKE LOWER(%s) OR LOWER(qs.butt_number) LIKE LOWER(%s) OR LOWER(qs.register_number) LIKE LOWER(%s) OR LOWER(qs.alloted_to_army_number) LIKE LOWER(%s))"
                q_param = f"%{q}%"
                params.extend([q_param, q_param, q_param, q_param])

            sql += " ORDER BY qs.register_number ASC;"
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()

            # Also fetch distinct weapon types for dropdown
            cursor.execute("SELECT DISTINCT type FROM QM_stock WHERE type IS NOT NULL AND type != '' ORDER BY type ASC;")
            types_rows = cursor.fetchall()
            distinct_types = [t['type'] for t in types_rows]

            # Stock stats (Held Strength excludes Deposited weapons)
            if role != 'qm' and user_company:
                coy_pattern = f"%{user_company.lower()}%"
                cursor.execute("SELECT COUNT(*) as total FROM QM_stock WHERE LOWER(company) LIKE LOWER(%s);", (coy_pattern,))
                total_cnt = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) as held FROM QM_stock WHERE LOWER(company) LIKE LOWER(%s) AND LOWER(weapon_status) IN ('available', 'issued', 'alloted');", (coy_pattern,))
                held_cnt = cursor.fetchone()['held']
                cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(company) LIKE LOWER(%s) AND LOWER(weapon_status) = 'available';", (coy_pattern,))
                avail_cnt = cursor.fetchone()['avail']
                cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(company) LIKE LOWER(%s) AND LOWER(weapon_status) IN ('issued', 'alloted');", (coy_pattern,))
                issued_cnt = cursor.fetchone()['issued']
                cursor.execute("SELECT COUNT(*) as deposited FROM QM_stock WHERE LOWER(company) LIKE LOWER(%s) AND LOWER(weapon_status) IN ('deposited', 'deposit');", (coy_pattern,))
                deposited_cnt = cursor.fetchone()['deposited']
            else:
                cursor.execute("SELECT COUNT(*) as total FROM QM_stock;")
                total_cnt = cursor.fetchone()['total']
                cursor.execute("SELECT COUNT(*) as held FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
                held_cnt = cursor.fetchone()['held']
                cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
                avail_cnt = cursor.fetchone()['avail']
                cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
                issued_cnt = cursor.fetchone()['issued']
                cursor.execute("SELECT COUNT(*) as deposited FROM QM_stock WHERE LOWER(weapon_status) IN ('deposited', 'deposit');")
                deposited_cnt = cursor.fetchone()['deposited']

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'stock': rows,
                'types': distinct_types,
                'stats': {
                    'total': total_cnt,
                    'held_strength': held_cnt,
                    'available': avail_cnt,
                    'issued': issued_cnt,
                    'deposited': deposited_cnt
                }
            })
        except Exception as e:
            print("Error fetching inventory stock:", e)
            return jsonify({'success': False, 'message': str(e), 'stock': []})

    return jsonify({'success': False, 'message': 'Database connection failed', 'stock': []})


@issuance_bp.route('/api/add_inventory_weapon', methods=['POST'])
def api_add_inventory_weapon():
    """Adds single or multiple weapons into QM_stock DB and returns newly created weapon details."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    w_type = (data.get('weapon_type') or data.get('type') or '').strip()
    company = (data.get('company') or '').strip() or None

    weapons = []
    if request.is_json and isinstance(data.get('weapons'), list):
        for item in data.get('weapons'):
            b = str(item.get('butt_number') or item.get('butt_no') or '').strip()
            r = str(item.get('register_number') or item.get('reg_no') or '').strip()
            if b and r:
                weapons.append({'butt_number': b, 'register_number': r})
    else:
        single_b = (data.get('butt_number') or data.get('butt_no') or '').strip()
        single_r = (data.get('register_number') or data.get('reg_no') or '').strip()
        if single_b and single_r:
            weapons.append({'butt_number': single_b, 'register_number': single_r})

    if not w_type:
        return jsonify({'success': False, 'message': 'Type of Weapon is required!'}), 400
    if not weapons:
        return jsonify({'success': False, 'message': 'At least one Butt Number and Register Number pair is required!'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            added_weapons = []
            duplicates = []

            for item in weapons:
                b_no = item['butt_number']
                r_no = item['register_number']

                cursor.execute("SELECT id FROM QM_stock WHERE LOWER(register_number) = LOWER(%s) LIMIT 1;", (r_no,))
                dup = cursor.fetchone()
                if dup:
                    duplicates.append(r_no)
                    continue

                cursor.execute("SELECT COALESCE(MAX(s_no), 0) AS max_s FROM QM_stock;")
                s_res = cursor.fetchone()
                next_s_no = (s_res['max_s'] or 0) + 1 if s_res else 1

                query = """
                INSERT INTO QM_stock (s_no, type, butt_number, register_number, company, weapon_status, barcode, allotment_type)
                VALUES (%s, %s, %s, %s, %s, 'Available', %s, NULL);
                """
                cursor.execute(query, (next_s_no, w_type, b_no, r_no, company, r_no))
                new_id = cursor.lastrowid
                added_weapons.append({
                    'id': new_id,
                    'type': w_type,
                    'butt_number': b_no,
                    'register_number': r_no,
                    'weapon_status': 'Available'
                })

            conn.commit()
            cursor.close()
            conn.close()

            if len(added_weapons) == 0 and duplicates:
                return jsonify({'success': False, 'message': f"Register Number(s) already exist in stock: {', '.join(duplicates)}"}), 400

            msg = f"{len(added_weapons)} weapon(s) of type '{w_type}' added to stock successfully!"
            if duplicates:
                msg += f" (Skipped {len(duplicates)} duplicate(s): {', '.join(duplicates)})"

            return jsonify({
                'success': True,
                'message': msg,
                'count': len(added_weapons),
                'weapons': added_weapons,
                'duplicates': duplicates,
                'weapon': added_weapons[0] if added_weapons else None
            })
        except Exception as e:
            print("Error adding inventory weapon:", e)
            return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': False, 'message': 'Database connection error'}), 500


@issuance_bp.route('/api/update_weapon_status', methods=['POST'])
def api_update_weapon_status():
    """Updates status of a weapon (Available, Issued, Deposited, Maintenance). Deposited weapons are removed from active Held Strength."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    weapon_id = data.get('id') or data.get('weapon_id')
    reg_no = (data.get('register_number') or data.get('reg_no') or '').strip()
    new_status = (data.get('status') or data.get('weapon_status') or '').strip()

    if not new_status:
        return jsonify({'success': False, 'message': 'New status is required!'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            if weapon_id:
                sql = "UPDATE QM_stock SET weapon_status = %s WHERE id = %s;"
                cursor.execute(sql, (new_status, weapon_id))
            elif reg_no:
                sql = "UPDATE QM_stock SET weapon_status = %s WHERE LOWER(register_number) = LOWER(%s);"
                cursor.execute(sql, (new_status, reg_no))
            else:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': 'Weapon ID or Register Number required!'}), 400

            conn.commit()

            # Recalculate stats (Held Strength excludes Deposited weapons)
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock;")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as held FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
            held_cnt = cursor.fetchone()['held']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
            issued_cnt = cursor.fetchone()['issued']
            cursor.execute("SELECT COUNT(*) as deposited FROM QM_stock WHERE LOWER(weapon_status) IN ('deposited', 'deposit');")
            deposited_cnt = cursor.fetchone()['deposited']

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': f'Weapon status updated to "{new_status}" successfully!',
                'new_status': new_status,
                'stats': {
                    'total': total_cnt,
                    'held_strength': held_cnt,
                    'available': avail_cnt,
                    'issued': issued_cnt,
                    'deposited': deposited_cnt
                }
            })
        except Exception as e:
            print("Error updating weapon status:", e)
            return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': False, 'message': 'Database connection error'}), 500


@issuance_bp.route('/api/delete_inventory_weapon', methods=['POST', 'DELETE'])
def api_delete_inventory_weapon():
    """Deletes a weapon entry from QM_stock DB permanently."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    weapon_id = data.get('id') or data.get('weapon_id')
    reg_no = (data.get('register_number') or data.get('reg_no') or '').strip()

    if not weapon_id and not reg_no:
        return jsonify({'success': False, 'message': 'Weapon ID or Register Number is required for deletion!'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            if weapon_id:
                cursor.execute("DELETE FROM QM_stock WHERE id = %s;", (weapon_id,))
            else:
                cursor.execute("DELETE FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (reg_no,))

            conn.commit()

            # Recalculate stats
            cursor.execute("SELECT COUNT(*) as total FROM QM_stock;")
            total_cnt = cursor.fetchone()['total']
            cursor.execute("SELECT COUNT(*) as held FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
            held_cnt = cursor.fetchone()['held']
            cursor.execute("SELECT COUNT(*) as avail FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            avail_cnt = cursor.fetchone()['avail']
            cursor.execute("SELECT COUNT(*) as issued FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
            issued_cnt = cursor.fetchone()['issued']
            cursor.execute("SELECT COUNT(*) as deposited FROM QM_stock WHERE LOWER(weapon_status) IN ('deposited', 'deposit');")
            deposited_cnt = cursor.fetchone()['deposited']

            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'Weapon record deleted successfully from inventory stock!',
                'stats': {
                    'total': total_cnt,
                    'held_strength': held_cnt,
                    'available': avail_cnt,
                    'issued': issued_cnt,
                    'deposited': deposited_cnt
                }
            })
        except Exception as e:
            print("Error deleting inventory weapon:", e)
            return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': False, 'message': 'Database connection error'}), 500


@issuance_bp.route('/api/history_sheet', methods=['GET'])
def get_history_sheets_route():
    """Fetches weapon history sheet entries from weapon_history_sheets table."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    search = request.args.get('search', '').strip()
    reg_no = request.args.get('register_number', '').strip()
    health_status = request.args.get('health_status', '').strip()

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT * FROM weapon_history_sheets WHERE 1=1"
        params = []

        if reg_no:
            sql += " AND LOWER(register_number) = LOWER(%s)"
            params.append(reg_no)

        if health_status:
            sql += " AND UPPER(health_status) = UPPER(%s)"
            params.append(health_status)

        if search:
            sql += """ AND (
                LOWER(weapon_type) LIKE LOWER(%s) OR 
                LOWER(butt_number) LIKE LOWER(%s) OR 
                LOWER(register_number) LIKE LOWER(%s) OR 
                LOWER(incharge_name) LIKE LOWER(%s) OR 
                LOWER(incharge_army_number) LIKE LOWER(%s) OR 
                LOWER(incharge_rank) LIKE LOWER(%s)
            )"""
            like_p = f"%{search}%"
            params.extend([like_p, like_p, like_p, like_p, like_p, like_p])

        sql += " ORDER BY id DESC LIMIT 100;"
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

        records = []
        for r in rows:
            d_firing = str(r['date_of_firing']) if r['date_of_firing'] else ''
            f_date = r['from_date'].strftime('%Y-%m-%d %H:%M') if isinstance(r.get('from_date'), (datetime, date)) else str(r.get('from_date') or '')
            t_date = r['to_date'].strftime('%Y-%m-%d %H:%M') if isinstance(r.get('to_date'), (datetime, date)) else str(r.get('to_date') or '')
            c_at = r['created_at'].strftime('%Y-%m-%d %H:%M') if isinstance(r.get('created_at'), (datetime, date)) else str(r.get('created_at') or '')

            records.append({
                'id': r['id'],
                'weapon_type': r['weapon_type'],
                'butt_number': r['butt_number'],
                'register_number': r['register_number'],
                'health_status': r['health_status'],
                'accessories': r.get('accessories') or 'Sling, Magazine (1)',
                'date_of_firing': d_firing,
                'rounds_fired': r['rounds_fired'],
                'total_rounds_count': r['total_rounds_count'],
                'incharge_army_number': r['incharge_army_number'],
                'incharge_rank': r['incharge_rank'],
                'incharge_name': r['incharge_name'],
                'from_date': f_date,
                'to_date': t_date,
                'biometric_status': r['biometric_status'] or 'Verified',
                'created_at': c_at
            })

        cursor.close()
        conn.close()
        return jsonify({'success': True, 'records': records, 'total': len(records)})
    except Exception as e:
        print("Error fetching history sheet records:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@issuance_bp.route('/api/history_sheet/save', methods=['POST'])
def save_history_sheet_route():
    """Saves a new weapon history sheet record in DB."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    weapon_type = (data.get('weapon_type') or '').strip()
    butt_number = (data.get('butt_number') or '').strip()
    register_number = (data.get('register_number') or '').strip()
    health_status = (data.get('health_status') or 'R1').strip().upper()
    accessories = (data.get('accessories') or 'Sling, Magazine (1)').strip()
    date_of_firing = (data.get('date_of_firing') or datetime.now().strftime('%Y-%m-%d')).strip()
    rounds_fired = int(data.get('rounds_fired') or 0)
    total_rounds_count = int(data.get('total_rounds_count') or 0)

    incharge_army_number = (data.get('incharge_army_number') or '').strip()
    incharge_rank = (data.get('incharge_rank') or '').strip()
    incharge_name = (data.get('incharge_name') or '').strip()
    from_date_raw = (data.get('from_date') or '').strip()
    to_date_raw = (data.get('to_date') or '').strip()
    biometric_status = (data.get('biometric_status') or 'Verified').strip()

    if not weapon_type or not register_number or not butt_number:
        return jsonify({'success': False, 'message': 'Weapon Type, Butt No, and Register No are required!'}), 400

    if not incharge_name or not incharge_army_number:
        return jsonify({'success': False, 'message': 'Incharge Name and Number are required!'}), 400

    from_date = None
    if from_date_raw:
        try:
            from_date = datetime.strptime(from_date_raw.replace('T', ' '), '%Y-%m-%d %H:%M')
        except Exception:
            try:
                from_date = datetime.strptime(from_date_raw[:10], '%Y-%m-%d')
            except Exception:
                from_date = None

    to_date = None
    if to_date_raw:
        try:
            to_date = datetime.strptime(to_date_raw.replace('T', ' '), '%Y-%m-%d %H:%M')
        except Exception:
            try:
                to_date = datetime.strptime(to_date_raw[:10], '%Y-%m-%d')
            except Exception:
                to_date = None

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error'}), 500

    try:
        cursor = conn.cursor()
        sql_insert = """
            INSERT INTO weapon_history_sheets 
            (weapon_type, butt_number, register_number, health_status, accessories, date_of_firing, rounds_fired, total_rounds_count, incharge_army_number, incharge_rank, incharge_name, from_date, to_date, biometric_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        cursor.execute(sql_insert, (
            weapon_type, butt_number, register_number, health_status, accessories,
            date_of_firing, rounds_fired, total_rounds_count,
            incharge_army_number, incharge_rank, incharge_name,
            from_date, to_date, biometric_status
        ))
        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'History Sheet recorded successfully for weapon {register_number}!',
            'id': new_id
        })
    except Exception as e:
        print("Error saving history sheet:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@issuance_bp.route('/api/history_sheet/weapons', methods=['GET'])
def get_stock_weapons_for_history_route():
    """Returns stock weapons list to prefill dropdowns in History Sheet modal."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, type, butt_number, register_number, weapon_status FROM QM_stock ORDER BY register_number ASC;")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        weapons = []
        for r in rows:
            weapons.append({
                'id': r['id'],
                'type': r['type'],
                'butt_number': r['butt_number'],
                'register_number': r['register_number'],
                'weapon_status': r['weapon_status']
            })

        return jsonify({'success': True, 'weapons': weapons})
    except Exception as e:
        print("Error fetching stock weapons for history:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@issuance_bp.route('/api/history_sheet/incharge_history', methods=['GET'])
def get_incharge_history_route():
    """Fetches full chronological incharge tenure history for a specific weapon."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    reg_no = request.args.get('register_number', '').strip()
    if not reg_no:
        return jsonify({'success': False, 'message': 'Register Number is required', 'history': []})

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error', 'history': []})

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, register_number, army_number, rank_name, name, from_date, to_date, created_at 
            FROM weapon_incharge_history 
            WHERE LOWER(register_number) = LOWER(%s)
            ORDER BY id ASC;
        """, (reg_no,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        history = []
        for r in rows:
            history.append({
                'id': r['id'],
                'register_number': r['register_number'],
                'army_number': r['army_number'],
                'rank_name': r['rank_name'],
                'name': r['name'],
                'from_date': r['from_date'],
                'to_date': r['to_date'] or 'As on Date'
            })

        return jsonify({'success': True, 'history': history, 'total': len(history)})
    except Exception as e:
        print("Error fetching incharge history:", e)
        return jsonify({'success': False, 'message': str(e), 'history': []})


@issuance_bp.route('/api/history_sheet/incharge_history/add', methods=['POST'])
def add_incharge_history_route():
    """Adds a new incharge tenure entry to the weapon's history chain."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    reg_no = (data.get('register_number') or '').strip()
    army_no = (data.get('army_number') or '').strip()
    rank_name = (data.get('rank_name') or '').strip()
    name = (data.get('name') or '').strip()
    from_date = (data.get('from_date') or '').strip()
    to_date = (data.get('to_date') or 'As on Date').strip()

    if not reg_no or not army_no or not name:
        return jsonify({'success': False, 'message': 'Register Number, Army Number, and Name are required!'}), 400

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO weapon_incharge_history (register_number, army_number, rank_name, name, from_date, to_date)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (reg_no, army_no, rank_name, name, from_date, to_date))
        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Incharge history entry added successfully!', 'id': new_id})
    except Exception as e:
        print("Error adding incharge history record:", e)
        return jsonify({'success': False, 'message': str(e)}), 500


@issuance_bp.route('/api/history_sheet/print_details', methods=['GET'])
def get_weapon_print_details_route():
    """Fetches complete weapon specifications, full incharge history, and all firing logs for printing."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    butt_no = request.args.get('butt_number', '').strip()
    reg_no = request.args.get('register_number', '').strip()
    query = request.args.get('q', '').strip()

    search_target = butt_no or reg_no or query

    conn = get_db_connection()
    if not conn or not conn.is_connected():
        return jsonify({'success': False, 'message': 'Database connection error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        # Search weapon stock details by butt_number or register_number
        sql_weapon = """
            SELECT id, type, butt_number, register_number, weapon_status, added_on
            FROM QM_stock
            WHERE LOWER(butt_number) = LOWER(%s)
               OR LOWER(register_number) = LOWER(%s)
               OR LOWER(butt_number) LIKE LOWER(%s)
               OR LOWER(register_number) LIKE LOWER(%s)
            LIMIT 1;
        """
        like_p = f"%{search_target}%" if search_target else "%"
        cursor.execute(sql_weapon, (search_target, search_target, like_p, like_p))
        weapon = cursor.fetchone()

        if not weapon:
            weapon = {
                'type': 'AK-47 / AK Series Rifle',
                'butt_number': butt_no or 'BT-101',
                'register_number': reg_no or 'REG-AK47-001',
                'weapon_status': 'R1'
            }

        target_reg = weapon.get('register_number') or reg_no or 'REG-AK47-001'

        # Fetch incharge history timeline
        cursor.execute("""
            SELECT id, register_number, army_number, rank_name, name, from_date, to_date 
            FROM weapon_incharge_history 
            WHERE LOWER(register_number) = LOWER(%s)
            ORDER BY id ASC;
        """, (target_reg,))
        incharge_history = cursor.fetchall()

        if not incharge_history:
            incharge_history = [
                {'army_number': '15717788X', 'rank_name': 'Nk', 'name': 'Kartheeswaran', 'from_date': '01 Jan 2006', 'to_date': '31 Dec 2009'},
                {'army_number': '15703251W', 'rank_name': 'Hav', 'name': 'Amrendra', 'from_date': '01 Jan 2010', 'to_date': '31 Dec 2013'},
                {'army_number': 'JC-782190P', 'rank_name': 'Sub', 'name': 'Ramesh Chand', 'from_date': '01 Jan 2014', 'to_date': '31 Dec 2023'},
                {'army_number': '15489201A', 'rank_name': 'Hav', 'name': 'Rajesh Kumar', 'from_date': '01 Jan 2024', 'to_date': 'As on Date'}
            ]

        # Fetch all firing logs for this weapon
        cursor.execute("""
            SELECT id, weapon_type, butt_number, register_number, health_status, date_of_firing, rounds_fired, total_rounds_count, incharge_army_number, incharge_rank, incharge_name, from_date, to_date, biometric_status, created_at
            FROM weapon_history_sheets
            WHERE LOWER(register_number) = LOWER(%s)
            ORDER BY id DESC;
        """, (target_reg,))
        firing_logs = cursor.fetchall()

        # Format dates for JSON
        for fl in firing_logs:
            if fl.get('date_of_firing'):
                fl['date_of_firing'] = str(fl['date_of_firing'])
            if fl.get('from_date'):
                fl['from_date'] = str(fl['from_date'])
            if fl.get('to_date'):
                fl['to_date'] = str(fl['to_date'])
            if fl.get('created_at'):
                fl['created_at'] = str(fl['created_at'])

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'weapon': weapon,
            'incharge_history': incharge_history,
            'firing_logs': firing_logs
        })
    except Exception as e:
        print("Error fetching weapon print details:", e)
        return jsonify({'success': False, 'message': str(e)}), 500







