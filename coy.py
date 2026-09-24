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
    
    # Format clean display name for company based on role or username
    comb = (role + ' ' + username).lower()
    
    if '3' in comb:
        coy_name = "3 COY KOTE"
    elif 'hq' in comb:
        coy_name = "HQ COY KOTE"
    elif 'comn' in comb or 'comm' in comb or 'cc' in comb:
        coy_name = "COMN COY KOTE"
    elif role:
        coy_name = role.upper()
    else:
        coy_name = "COY KOTE"

    conn = get_db_connection()
    weapons_list = []
    stats = {
        'total_weapons': 0,
        'available_weapons': 0,
        'issued_weapons': 0,
        'total_types': 0
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

            # Query live stock counts from QM_stock table for COY overview
            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock;")
            stats['total_weapons'] = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) = 'available';")
            stats['available_weapons'] = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) != 'available';")
            stats['issued_weapons'] = cursor.fetchone()['cnt']

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
    conn = get_db_connection()
    troops = []
    
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            sql = """
                SELECT army_number, name, `rank`, company, section 
                FROM troops 
                WHERE army_number LIKE %s OR name LIKE %s OR `rank` LIKE %s OR company LIKE %s
                ORDER BY army_number ASC LIMIT 15;
            """
            search_param = f"%{query}%"
            cursor.execute(sql, (search_param, search_param, search_param, search_param))
            rows = cursor.fetchall()
            for r in rows:
                troops.append({
                    'army_number': r['army_number'],
                    'name': r['name'],
                    'rank': r['rank'],
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
    
    conn = get_db_connection()
    stock = []
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
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
            cursor = conn.cursor(dictionary=True)

            # 1. Verify weapon exists in QM_stock
            cursor.execute("SELECT id, weapon_status FROM QM_stock WHERE register_number = %s;", (register_number,))
            weapon = cursor.fetchone()
            if not weapon:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': f'Weapon with Register Number {register_number} not found.'}), 404

            # 2. Update weapon_status to 'Alloted' and set alloted_to_army_number to army_number
            update_sql = """
                UPDATE QM_stock 
                SET weapon_status = 'Alloted', alloted_to_army_number = %s 
                WHERE register_number = %s;
            """
            cursor.execute(update_sql, (army_number, register_number))
            conn.commit()

            cursor.close()
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Weapon {register_number} successfully allotted to Army No: {army_number}!'
            })
        except Exception as e:
            print("Error allotting weapon:", e)
            if conn and conn.is_connected():
                conn.rollback()
                cursor.close()
                conn.close()
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500

    return jsonify({'success': False, 'message': 'Failed to connect to database.'}), 500




