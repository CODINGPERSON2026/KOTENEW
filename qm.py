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
        'assigned_to_company': 0,
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

            # Query live stock counts from QM_stock table (Excludes Deposited weapons)
            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit');")
            stats['total_weapons'] = cursor.fetchone()['cnt']

            # Available = weapon_status = 'Available' AND company is not assigned to a company
            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) = 'available' AND (company IS NULL OR TRIM(company) = '' OR company = 'In Armory (Unassigned)');")
            stats['available_weapons'] = cursor.fetchone()['cnt']

            # Assigned to Company = weapon_status = 'Available' AND company IS NOT NULL and not empty/unassigned
            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) = 'available' AND company IS NOT NULL AND TRIM(company) != '' AND company != 'In Armory (Unassigned)';")
            stats['assigned_to_company'] = cursor.fetchone()['cnt']

            cursor.execute("SELECT COUNT(*) as cnt FROM QM_stock WHERE LOWER(weapon_status) IN ('issued', 'alloted');")
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
                SELECT cw.weapon_type, 
                       COUNT(CASE WHEN LOWER(qs.weapon_status) = 'available' AND (qs.company IS NULL OR TRIM(qs.company) = '' OR qs.company = 'In Armory (Unassigned)') THEN qs.id END) as cnt
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
    company = request.form.get('company') or None

    if not weapon_type or not butt_number or not register_number:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()

            # Calculate next s_no (sequential, starting from 1)
            cursor.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM QM_stock;")
            next_s_no = cursor.fetchone()[0]

            query = """
            INSERT INTO QM_stock (s_no, type, butt_number, register_number, company, weapon_status)
            VALUES (%s, %s, %s, %s, %s, 'Available');
            """
            cursor.execute(query, (next_s_no, weapon_type, butt_number, register_number, company))
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


# ─── STAT BREAKDOWN APIS (for clickable stat card modals) ────────────────────

@qm_bp.route("/api/qm/stats/total")
def api_stats_total():
    """Grouped weapon count for Total Weapons in Stock (excludes deposited)."""
    if 'username' not in session:
        return jsonify({'success': False}), 401
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT type AS label, COUNT(*) AS count
                FROM QM_stock
                WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit')
                GROUP BY type
                ORDER BY type ASC;
            """)
            rows = [{'label': r['label'], 'count': r['count']} for r in cursor.fetchall()]
            cursor.close(); conn.close()
            return jsonify({'success': True, 'rows': rows})
        except Exception as e:
            return jsonify({'success': False, 'rows': [], 'error': str(e)})
    return jsonify({'success': False, 'rows': []})


@qm_bp.route("/api/qm/stats/available")
def api_stats_available():
    """Grouped weapon count for Available in Armory (status=Available AND company IS NULL)."""
    if 'username' not in session:
        return jsonify({'success': False}), 401
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT type AS label, COUNT(*) AS count
                FROM QM_stock
                WHERE LOWER(weapon_status) = 'available'
                  AND company IS NULL
                GROUP BY type
                ORDER BY type ASC;
            """)
            rows = [{'label': r['label'], 'count': r['count']} for r in cursor.fetchall()]
            cursor.close(); conn.close()
            return jsonify({'success': True, 'rows': rows})
        except Exception as e:
            return jsonify({'success': False, 'rows': [], 'error': str(e)})
    return jsonify({'success': False, 'rows': []})


@qm_bp.route("/api/qm/stats/assigned")
def api_stats_assigned():
    """Grouped weapon count for Assigned to Company (status=Available AND company IS NOT NULL)."""
    if 'username' not in session:
        return jsonify({'success': False}), 401
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT company AS label, COUNT(*) AS count
                FROM QM_stock
                WHERE LOWER(weapon_status) = 'available'
                  AND company IS NOT NULL
                GROUP BY company
                ORDER BY company ASC;
            """)
            rows = [{'label': r['label'], 'count': r['count']} for r in cursor.fetchall()]
            cursor.close(); conn.close()
            return jsonify({'success': True, 'rows': rows})
        except Exception as e:
            return jsonify({'success': False, 'rows': [], 'error': str(e)})
    return jsonify({'success': False, 'rows': []})


@qm_bp.route("/api/qm/company_distribution")
def api_company_distribution():
    """Company-wise weapon distribution, optionally filtered by weapon_type."""
    if 'username' not in session:
        return jsonify({'success': False}), 401

    weapon_type = request.args.get('weapon_type', '').strip()
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)

            base_where = "LOWER(weapon_status) NOT IN ('deposited', 'deposit')"
            params = []
            if weapon_type:
                base_where += " AND LOWER(type) = LOWER(%s)"
                params.append(weapon_type)

            cursor.execute(f"""
                SELECT company AS label,
                       COUNT(*) AS count
                FROM QM_stock
                WHERE {base_where} AND company IS NOT NULL AND TRIM(company) != '' AND company != 'In Armory (Unassigned)'
                GROUP BY company
                ORDER BY label ASC;
            """, params)
            rows = [{'label': r['label'], 'count': r['count']} for r in cursor.fetchall()]

            # Also fetch weapon types for the dropdown
            cursor.execute("""
                SELECT DISTINCT type FROM QM_stock
                WHERE LOWER(weapon_status) NOT IN ('deposited', 'deposit')
                ORDER BY type ASC;
            """)
            types = [r['type'] for r in cursor.fetchall()]

            cursor.close(); conn.close()
            return jsonify({'success': True, 'rows': rows, 'weapon_types': types})
        except Exception as e:
            return jsonify({'success': False, 'rows': [], 'weapon_types': [], 'error': str(e)})
    return jsonify({'success': False, 'rows': [], 'weapon_types': []})


@qm_bp.route("/qm/issue")
def issue_page_route():
    if 'username' not in session:
        return redirect(url_for('login_route'))

    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return redirect(url_for('coy.coy_dashboard_route'))

    conn = get_db_connection()
    available_weapons = []
    weapon_types = []  # list of {name, available_count, image_path}

    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)

            # Fetch all available weapons for the table (Available = status='available' AND company IS NULL)
            cursor.execute("""
                SELECT qs.id, qs.s_no, qs.type, qs.butt_number, qs.register_number,
                       qs.weapon_status, qs.added_on,
                       cw.image_path
                FROM QM_stock qs
                LEFT JOIN core_weapons cw ON LOWER(cw.weapon_type) = LOWER(qs.type)
                WHERE LOWER(qs.weapon_status) = 'available'
                  AND qs.company IS NULL
                ORDER BY qs.type ASC, qs.s_no ASC;
            """)
            available_weapons = cursor.fetchall()

            # Fetch weapon types with available counts for the bulk modal (same definition)
            cursor.execute("""
                SELECT cw.weapon_type AS name, cw.image_path,
                       COUNT(qs.id) AS available_count
                FROM core_weapons cw
                LEFT JOIN QM_stock qs
                    ON LOWER(cw.weapon_type) = LOWER(qs.type)
                    AND LOWER(qs.weapon_status) = 'available'
                    AND qs.company IS NULL
                GROUP BY cw.id, cw.weapon_type, cw.image_path
                HAVING COUNT(qs.id) > 0
                ORDER BY cw.weapon_type ASC;
            """)
            weapon_types = cursor.fetchall()

            cursor.close()
            conn.close()
        except Exception as e:
            print("Error fetching available weapons for issue page:", e)

    return render_template(
        'QM/issue.html',
        username=session.get('username'),
        role=session.get('role'),
        available_weapons=available_weapons,
        weapon_types=weapon_types
    )


@qm_bp.route("/api/troops/lookup")
def api_troops_lookup():
    """Lookup a troop by army_number for the issue modal."""
    if 'username' not in session:
        return jsonify({'found': False, 'message': 'Unauthorized'}), 401

    army_number = request.args.get('army_number', '').strip()
    if not army_number:
        return jsonify({'found': False})

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT army_number, name, rank_name, company, section FROM troops WHERE LOWER(army_number) = LOWER(%s) LIMIT 1;",
                (army_number,)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                return jsonify({
                    'found': True,
                    'army_number': row['army_number'],
                    'name': row['name'],
                    'rank': row['rank_name'] or '',
                    'company': row['company'] or '',
                    'section': row['section'] or ''
                })
            return jsonify({'found': False})
        except Exception as e:
            print("Troop lookup error:", e)
            return jsonify({'found': False})
    return jsonify({'found': False})


@qm_bp.route("/api/qm/companies")
def api_qm_companies():
    """Return distinct non-QM company names from the users table."""
    if 'username' not in session:
        return jsonify({'success': False, 'companies': []}), 401

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT DISTINCT company
                FROM users
                WHERE company IS NOT NULL
                  AND company != ''
                  AND LOWER(company) != 'qm'
                ORDER BY company ASC;
            """)
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            companies = [r['company'] for r in rows if r['company']]
            return jsonify({'success': True, 'companies': companies})
        except Exception as e:
            print("Error fetching companies:", e)
            return jsonify({'success': False, 'companies': []})
    return jsonify({'success': False, 'companies': []})


@qm_bp.route("/qm/assign_company", methods=['POST'])
def assign_company_route():
    """Update only the company column in QM_stock for the given weapon id."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    weapon_id = request.form.get('weapon_id', '').strip()
    company   = request.form.get('company', '').strip()

    if not weapon_id or not company:
        return jsonify({'success': False, 'message': 'Weapon ID and Company are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE QM_stock SET company = %s WHERE id = %s;",
                (company, weapon_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'message': f'Weapon assigned to {company} successfully!'})
        except Exception as e:
            print("Error assigning company:", e)
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Database connection error'}), 500


@qm_bp.route("/qm/bulk_assign_company", methods=['POST'])
def bulk_assign_company_route():
    """Bulk-update company for the N oldest available weapons of a given type."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    weapon_type = request.form.get('weapon_type', '').strip()
    company     = request.form.get('company', '').strip()
    try:
        count = int(request.form.get('count', 0))
    except ValueError:
        count = 0

    if not weapon_type or not company or count <= 0:
        return jsonify({'success': False, 'message': 'Weapon type, company, and a valid count are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)

            # Check how many are actually available for this type (Available = status='available' AND company IS NULL)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM QM_stock WHERE LOWER(type) = LOWER(%s) AND LOWER(weapon_status) = 'available' AND company IS NULL;",
                (weapon_type,)
            )
            available = cursor.fetchone()['cnt']

            if count > available:
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': f'Only {available} weapon(s) of this type are available. Cannot assign {count}.'
                }), 400

            # Fetch IDs of the N oldest available weapons of this type
            cursor.execute(
                "SELECT id FROM QM_stock WHERE LOWER(type) = LOWER(%s) AND LOWER(weapon_status) = 'available' AND company IS NULL ORDER BY s_no ASC, id ASC LIMIT %s;",
                (weapon_type, count)
            )
            ids = [r['id'] for r in cursor.fetchall()]

            if not ids:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'message': 'No available weapons found for this type.'}), 404

            # Bulk update company
            placeholders = ', '.join(['%s'] * len(ids))
            cursor.execute(
                f"UPDATE QM_stock SET company = %s WHERE id IN ({placeholders});",
                [company] + ids
            )
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'message': f'{len(ids)} weapon(s) assigned to {company} successfully!'})
        except Exception as e:
            print("Error in bulk assign company:", e)
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'Database connection error'}), 500
