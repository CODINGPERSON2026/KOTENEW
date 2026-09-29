from imports import *

coy_bp = Blueprint('coy', __name__)


@coy_bp.route("/coy")
def coy_dashboard_route():
    if 'username' not in session:
        return redirect(url_for('login_route'))
    
    role = str(session.get('role', '')).strip().lower()
    if role == 'qm':
        return redirect(url_for('qm.qm_dashboard_route'))
    
    role = str(session.get('role', '')).strip()
    username = str(session.get('username', '')).strip()
    user_company = str(session.get('company', '')).strip()
    
    # Format clean display name and target_company based on company column or role/username fallback
    target_company = user_company
    if not target_company:
        comb = (role + ' ' + username).lower()
        if '3' in comb:
            target_company = "3 Company"
        elif 'hq' in comb:
            target_company = "HQ Company"
        elif 'comn' in comb or 'comm' in comb or 'cc' in comb:
            target_company = "COMN Company"
        elif role:
            target_company = role

    t_lower = target_company.lower()
    if '3' in t_lower:
        coy_name = "3 COY KOTE"
        target_company = "3 Company"
        coy_pattern = "%3%"
    elif 'hq' in t_lower:
        coy_name = "HQ COY KOTE"
        target_company = "HQ Company"
        coy_pattern = "%hq%"
    elif 'comn' in t_lower or 'comm' in t_lower or 'cc' in t_lower:
        coy_name = "COMN COY KOTE"
        target_company = "COMN Company"
        coy_pattern = "%comn%"
    elif target_company:
        coy_name = target_company.upper()
        coy_pattern = f"%{target_company.lower()}%"
    else:
        coy_name = "COY KOTE"
        coy_pattern = "%"

    conn = get_db_connection()
    weapons_list = []
    stats = {
        'weapons_held': 0,
        'available_weapons': 0,
        'issued_weapons': 0,
        'total_types': 0,
        'in_kote': 0
    }
    chart_data = {
        'bar_labels': [],
        'bar_full_names': [],
        'bar_counts': [],
        'donut_counts': [0, 0]
    }

    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Fetch core weapons list
            cursor.execute("SELECT id, weapon_type, image_path FROM core_weapons ORDER BY id ASC;")
            rows = cursor.fetchall()
            for r in rows:
                weapons_list.append({
                    'id': r['id'],
                    'name': r['weapon_type'],
                    'filename': r['image_path']
                })
            stats['total_types'] = len(weapons_list)

            # Query live company-specific stock counts from QM_stock table for COY overview
            if target_company:
                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM QM_stock qs
                    WHERE LOWER(qs.company) LIKE LOWER(%s)
                      AND LOWER(qs.weapon_status) IN ('available', 'issued', 'alloted');
                """, (coy_pattern,))
                stats['weapons_held'] = cursor.fetchone()['cnt']

                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM QM_stock qs
                    WHERE LOWER(qs.company) LIKE LOWER(%s)
                      AND LOWER(qs.weapon_status) = 'available';
                """, (coy_pattern,))
                stats['available_weapons'] = cursor.fetchone()['cnt']

                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM QM_stock qs
                    WHERE LOWER(qs.company) LIKE LOWER(%s)
                      AND LOWER(qs.weapon_status) IN ('issued', 'alloted');
                """, (coy_pattern,))
                stats['issued_weapons'] = cursor.fetchone()['cnt']

                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM issuance_logs 
                    WHERE UPPER(action_type) = 'RETURN'
                      AND (LOWER(company) LIKE LOWER(%s) OR LOWER(operator_username) LIKE LOWER(%s));
                """, (coy_pattern, coy_pattern))
                stats['in_kote'] = cursor.fetchone()['cnt']
            else:
                cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) IN ('available', 'issued', 'alloted');")
                stats['weapons_held'] = cursor.fetchone()['cnt']

                cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
                stats['available_weapons'] = cursor.fetchone()['cnt']

                cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
                stats['issued_weapons'] = cursor.fetchone()['cnt']

                cursor.execute("SELECT COUNT(*) as cnt FROM issuance_logs WHERE UPPER(action_type) = 'RETURN';")
                stats['in_kote'] = cursor.fetchone()['cnt']

            # Query stock count for each weapon type for the Bar Chart
            bar_chart_labels = []
            bar_chart_full_names = []
            bar_chart_data = []
            
            short_labels_map = {
                'AK-47 / AK Series Rifle': 'AK47',
                '9mm CMG Carbine Machine Gun': 'CMG',
                'INSAS 5.56mm Assault Rifle': 'INSAS',
                'INSAS 5.56mm Light Machine Gun': 'INSAS LMG',
                '7.62mm Light Machine Gun (LMG)': 'LMG 7.62',
                '9mm Service Pistol': 'PISTOL'
            }

            if target_company:
                cursor.execute("""
                    SELECT cw.weapon_type, COUNT(qs.id) as cnt
                    FROM core_weapons cw
                    LEFT JOIN QM_stock qs ON LOWER(cw.weapon_type) = LOWER(qs.type) 
                                         AND LOWER(qs.weapon_status) = 'available'
                                         AND (LOWER(qs.company) LIKE LOWER(%s) OR qs.company IS NULL OR qs.company = '')
                    GROUP BY cw.id, cw.weapon_type
                    ORDER BY cw.id ASC;
                """, (coy_pattern,))
            else:
                cursor.execute("""
                    SELECT cw.weapon_type, COUNT(qs.id) as cnt
                    FROM core_weapons cw
                    LEFT JOIN QM_stock qs ON LOWER(cw.weapon_type) = LOWER(qs.type) AND LOWER(qs.weapon_status) = 'available'
                    GROUP BY cw.id, cw.weapon_type
                    ORDER BY cw.id ASC;
                """)
            type_rows = cursor.fetchall()
            for tr in type_rows:
                full_name = tr['weapon_type']
                short_name = short_labels_map.get(full_name, full_name)
                bar_chart_labels.append(short_name)
                bar_chart_full_names.append(full_name)
                bar_chart_data.append(tr['cnt'])

            chart_data = {
                'bar_labels': bar_chart_labels,
                'bar_full_names': bar_chart_full_names,
                'bar_counts': bar_chart_data,
                'donut_counts': [stats['available_weapons'], stats['issued_weapons']]
            }

            cursor.close()
            conn.close()
        except Exception as e:
            print("Error querying COY dashboard stats:", e)

    return render_template(
        'COY/COY.html',
        username=session.get('username'),
        role=session.get('role'),
        coy_name=coy_name,
        weapons=weapons_list,
        stats=stats,
        chart_data=chart_data
    )


@coy_bp.route("/coy/search_troops", methods=['GET'])
def search_troops_route():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    query = request.args.get('q', '').strip()
    role = str(session.get('role', '')).strip().lower()
    user_company = str(session.get('company', '')).strip()

    conn = get_db_connection()
    troops = []
    
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            search_param = f"%{query}%"
            
            # Filter troops by company if non-QM user has company assigned
            if role != 'qm' and user_company:
                sql = """
                    SELECT army_number, name, rank_name, rank_name AS `rank`, company, section 
                    FROM troops 
                    WHERE (LOWER(army_number) LIKE LOWER(%s) OR LOWER(name) LIKE LOWER(%s) OR LOWER(rank_name) LIKE LOWER(%s) OR LOWER(company) LIKE LOWER(%s))
                      AND LOWER(company) = LOWER(%s)
                    ORDER BY army_number ASC LIMIT 15;
                """
                cursor.execute(sql, (search_param, search_param, search_param, search_param, user_company))
            else:
                sql = """
                    SELECT army_number, name, rank_name, rank_name AS `rank`, company, section 
                    FROM troops 
                    WHERE LOWER(army_number) LIKE LOWER(%s) OR LOWER(name) LIKE LOWER(%s) OR LOWER(rank_name) LIKE LOWER(%s) OR LOWER(company) LIKE LOWER(%s)
                    ORDER BY army_number ASC LIMIT 15;
                """
                cursor.execute(sql, (search_param, search_param, search_param, search_param))

            rows = cursor.fetchall()
            for r in rows:
                troops.append({
                    'army_number': r['army_number'],
                    'name': r['name'],
                    'rank': r['rank_name'],
                    'rank_name': r['rank_name'],
                    'company': r['company'],
                    'section': r['section']
                })
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'troops': troops})
        except Exception as e:
            print("Error searching troops:", e)
            return jsonify({'success': False, 'message': str(e), 'troops': []})
            
    return jsonify({'success': False, 'troops': []})


@coy_bp.route("/coy/available_weapons", methods=['GET'])
def available_weapons_route():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    role = str(session.get('role', '')).strip().lower()
    user_company = str(session.get('company', '')).strip()

    conn = get_db_connection()
    stock = []
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            if role != 'qm' and user_company:
                cursor.execute("""
                    SELECT register_number, butt_number, type 
                    FROM QM_stock 
                    WHERE LOWER(weapon_status) = 'available'
                      AND (LOWER(company) = LOWER(%s) OR company IS NULL OR company = '')
                    ORDER BY register_number ASC;
                """, (user_company,))
            else:
                cursor.execute("SELECT register_number, butt_number, type FROM QM_stock WHERE LOWER(weapon_status) = 'available' ORDER BY register_number ASC;")

            rows = cursor.fetchall()
            for r in rows:
                stock.append({
                    'register_number': r['register_number'],
                    'butt_number': r['butt_number'],
                    'type': r['type']
                })
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'stock': stock})
        except Exception as e:
            print("Error loading available weapons:", e)
            return jsonify({'success': False, 'message': str(e), 'stock': []})
            
    return jsonify({'success': False, 'stock': []})


def is_jco_or_officer(rank_name, army_number=""):
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


@coy_bp.route("/coy/allot_weapon", methods=['POST'])
def allot_weapon_route():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    register_number = request.form.get('register_number', '').strip()
    army_number = request.form.get('army_number', '').strip()

    if not register_number or not army_number:
        return jsonify({'success': False, 'message': 'Register Number and Army Number are required fields.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True , buffered = True)

            # 1. Verify weapon exists in QM_stock
            cursor.execute("SELECT id, weapon_status FROM QM_stock WHERE register_number = %s;", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon with Register Number {register_number} not found.'}), 404

            # 2. Check existing weapons allotted to this army_number
            cursor.execute("""
                SELECT COUNT(*) as count, GROUP_CONCAT(register_number SEPARATOR ', ') as issued_regs
                FROM QM_stock 
                WHERE LOWER(alloted_to_army_number) = LOWER(%s)
                  AND LOWER(weapon_status) IN ('issued', 'alloted');
            """, (army_number,))
            existing_info = cursor.fetchone()
            existing_count = existing_info['count'] if existing_info and existing_info['count'] else 0
            existing_regs = existing_info['issued_regs'] if existing_info and existing_info['issued_regs'] else ''

            # Check rank of personnel
            cursor.execute("SELECT rank_name, name FROM troops WHERE LOWER(army_number) = LOWER(%s);", (army_number,))
            tr = cursor.fetchone()
            tr_rank = tr['rank_name'] if tr else ''
            tr_name = tr['name'] if tr else 'Personnel'

            if existing_count > 0 and not is_jco_or_officer(tr_rank, army_number):
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'Allotment Blocked: Jawan {tr_name} ({tr_rank}) already has weapon ({existing_regs}) allotted! Jawan ke naam pe single weapon hi allot ho sakta hai.'
                }), 400

            # 3. Handle Permanent vs Temporary (Leave) Allotment
            allotment_type = request.form.get('allotment_type', 'Permanent').strip()
            perm_army_number = request.form.get('permanent_army_number', '').strip() or army_number
            leave_start = request.form.get('leave_start_date', '').strip() or None
            leave_end = request.form.get('leave_end_date', '').strip() or None

            if allotment_type.lower() == 'temporary':
                if not leave_start or not leave_end:
                    cursor.close()
                    conn.close()
                    return jsonify({'success': False, 'message': 'Leave Start Date and Leave End Date are required for Temporary Transfer!'}), 400

                update_sql = """
                    UPDATE QM_stock 
                    SET weapon_status = 'Alloted', 
                        alloted_to_army_number = %s,
                        permanent_allottee_army_no = %s,
                        allotment_type = 'Temporary',
                        leave_start_date = %s,
                        leave_end_date = %s
                    WHERE register_number = %s;
                """
                cursor.execute(update_sql, (army_number, perm_army_number, leave_start, leave_end, register_number))
                msg_suffix = f" (Temporary Transfer due to Leave from {leave_start} to {leave_end}. Will auto-revert to {perm_army_number} after leave ends)."
            else:
                update_sql = """
                    UPDATE QM_stock 
                    SET weapon_status = 'Alloted', 
                        alloted_to_army_number = %s,
                        permanent_allottee_army_no = %s,
                        allotment_type = 'Permanent',
                        leave_start_date = NULL,
                        leave_end_date = NULL
                    WHERE register_number = %s;
                """
                cursor.execute(update_sql, (army_number, perm_army_number, register_number))
                msg_suffix = " (Permanent Allotment)."

            conn.commit()

            cursor.close()
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Weapon {register_number} successfully allotted to Army No: {army_number} ({tr_name}){msg_suffix}'
            })
        except Exception as e:
            print("Error allotting weapon:", e)
            if conn and conn.is_connected():
                conn.rollback()
                cursor.close()
                conn.close()
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

    return jsonify({'success': False, 'message': 'Failed to connect to database.'}), 500




