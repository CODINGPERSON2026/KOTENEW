from imports import *

qm_bp = Blueprint('qm', __name__)


@qm_bp.route("/qm")
def qm_dashboard_route():
    if 'username' not in session:
        return redirect(url_for('login_route'))
    
    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return redirect(url_for('coy.coy_dashboard_route'))
    
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
        'bar_counts': [],
        'donut_counts': [0, 0]
    }

    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            
            # Fetch core weapons list for dropdown
            cursor.execute("SELECT id, weapon_type, image_path FROM core_weapons ORDER BY id ASC;")
            rows = cursor.fetchall()
            for r in rows:
                weapons_list.append({
                    'id': r['id'],
                    'name': r['weapon_type'],
                    'filename': r['image_path']
                })
            stats['total_types'] = len(weapons_list)

            # Query live stock counts from QM_stock table
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
                LEFT JOIN QM_stock qs ON LOWER(cw.weapon_type) = LOWER(qs.type)
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
            print("Error querying QM dashboard stats:", e)

    return render_template(
        'QM/QM.html',
        username=session.get('username'),
        role=session.get('role'),
        weapons=weapons_list,
        stats=stats,
        chart_data=chart_data
    )


@qm_bp.route("/qm/add_weapon", methods=['POST'])
def add_weapon_route():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    weapon_type = request.form.get('weapon_type')
    butt_number = request.form.get('butt_number')
    register_number = request.form.get('register_number')

    if not weapon_type or not butt_number or not register_number:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            query = """
            INSERT INTO QM_stock (type, butt_number, register_number, weapon_status)
            VALUES (%s, %s, %s, 'Available');
            """
            cursor.execute(query, (weapon_type, butt_number, register_number))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'message': 'Weapon added to QM stock successfully!'})
        except Error as e:
            print("Database Error when adding weapon:", e)
            if e.errno == 1062:  # Duplicate entry
                return jsonify({'success': False, 'message': 'Register Number already exists in stock!'}), 400
            return jsonify({'success': False, 'message': str(e)}), 500
    else:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500


@qm_bp.route("/qm/check_register_number")
def check_register_number_route():
    if 'username' not in session:
        return jsonify({'exists': False, 'message': 'Unauthorized'}), 401
    
    register_num = request.args.get('num', '').strip()
    if not register_num:
        return jsonify({'exists': False})

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (register_num,))
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return jsonify({'exists': count > 0})
        except Exception as e:
            print("Error checking register_number:", e)
            return jsonify({'exists': False})
    return jsonify({'exists': False})

