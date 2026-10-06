from imports import *
import re

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

            cursor.execute("""
                SELECT COUNT(*) as cnt 
                FROM QM_stock qs
                WHERE (
                    SELECT il.action_type 
                    FROM issuance_logs il 
                    WHERE LOWER(il.register_number) = LOWER(qs.register_number)
                       OR (qs.alloted_to_army_number IS NOT NULL AND TRIM(qs.alloted_to_army_number) != '' AND LOWER(il.army_number) = LOWER(qs.alloted_to_army_number))
                    ORDER BY il.id DESC LIMIT 1
                ) = 'OUT';
            """)
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
            # Query stock count for weapon categories for the Pie Chart
            cursor.execute("""
                SELECT cw.weapon_type, 
                       COUNT(qs.id) as total_cnt
                FROM core_weapons cw
                LEFT JOIN QM_stock qs ON LOWER(cw.weapon_type) = LOWER(qs.type) AND LOWER(qs.weapon_status) NOT IN ('deposited', 'deposit')
                GROUP BY cw.id, cw.weapon_type
                ORDER BY cw.id ASC;
            """)
            cat_rows = cursor.fetchall()
            pie_labels = []
            pie_counts = []
            for cr in cat_rows:
                if cr['total_cnt'] > 0:
                    full_n = cr['weapon_type']
                    short_n = short_labels_map.get(full_n, full_n)
                    pie_labels.append(short_n)
                    pie_counts.append(cr['total_cnt'])

            chart_data = {
                'bar_labels': bar_chart_labels,
                'bar_full_names': bar_chart_full_names,
                'bar_counts': bar_chart_data,
                'donut_counts': [stats['available_weapons'], stats['assigned_to_company']],
                'donut_labels': ['In Armory', 'Assigned to Company'],
                'pie_labels': pie_labels,
                'pie_counts': pie_counts
            }

            # Fetch recent stock additions
            recent_additions = []
            cursor.execute("""
                SELECT id, s_no, type, butt_number, register_number, company, weapon_status
                FROM QM_stock
                ORDER BY id DESC
                LIMIT 5;
            """)
            recent_additions = cursor.fetchall()

            cursor.close()
            conn.close()
        except Exception as e:
            print("Error querying QM dashboard stats:", e)
            recent_additions = []

    return render_template(
        'QM/QM.html',
        username=session.get('username'),
        role=session.get('role'),
        weapons=weapons_list,
        stats=stats,
        chart_data=chart_data,
        recent_additions=recent_additions
    )


@qm_bp.route("/qm/add_weapon", methods=['POST'])
def add_weapon_route():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    data = request.get_json(silent=True) or request.form
    weapon_type = (data.get('weapon_type') or request.form.get('weapon_type') or '').strip()
    company = (data.get('company') or request.form.get('company') or '').strip() or None

    weapons = []
    if request.is_json and isinstance(data.get('weapons'), list):
        for item in data.get('weapons'):
            b = str(item.get('butt_number') or item.get('butt_no') or '').strip()
            r = str(item.get('register_number') or item.get('reg_no') or '').strip()
            if b and r:
                weapons.append({'butt_number': b, 'register_number': r})
    else:
        butt_nums = request.form.getlist('butt_number')
        reg_nums = request.form.getlist('register_number')
        if butt_nums and reg_nums:
            for b, r in zip(butt_nums, reg_nums):
                b_str = (b or '').strip()
                r_str = (r or '').strip()
                if b_str and r_str:
                    weapons.append({'butt_number': b_str, 'register_number': r_str})
        else:
            b_single = (request.form.get('butt_number') or data.get('butt_number') or '').strip()
            r_single = (request.form.get('register_number') or data.get('register_number') or '').strip()
            if b_single and r_single:
                weapons.append({'butt_number': b_single, 'register_number': r_single})

    if not weapon_type:
        return jsonify({'success': False, 'message': 'Weapon type is required.'}), 400
    if not weapons:
        return jsonify({'success': False, 'message': 'At least one valid Butt Number and Register Number pair is required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            added_count = 0
            duplicates = []
            
            for item in weapons:
                b_raw = str(item['butt_number']).strip()
                b_no = re.sub(r'\D', '', b_raw) or b_raw
                r_no = item['register_number']

                cursor.execute("SELECT COUNT(*) FROM QM_stock WHERE LOWER(register_number) = LOWER(%s);", (r_no,))
                if cursor.fetchone()[0] > 0:
                    duplicates.append(r_no)
                    continue

                cursor.execute("SELECT COALESCE(MAX(s_no), 0) + 1 FROM QM_stock;")
                next_s_no = cursor.fetchone()[0]

                query = """
                INSERT INTO QM_stock (s_no, type, butt_number, register_number, company, weapon_status, barcode, allotment_type)
                VALUES (%s, %s, %s, %s, %s, 'Available', %s, NULL);
                """
                cursor.execute(query, (next_s_no, weapon_type, b_no, r_no, company, r_no))
                added_count += 1

            conn.commit()
            cursor.close()
            conn.close()

            if added_count == 0 and duplicates:
                return jsonify({'success': False, 'message': f"Register Number(s) already exist in stock: {', '.join(duplicates)}"}), 400

            msg = f"{added_count} weapon(s) of type '{weapon_type}' added to QM stock successfully!"
            if duplicates:
                msg += f" (Skipped {len(duplicates)} duplicate(s): {', '.join(duplicates)})"

            return jsonify({'success': True, 'message': msg, 'added_count': added_count, 'duplicates': duplicates})
        except Error as e:
            print("Database Error when adding weapon:", e)
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


def sanitize_qm_stock_butt_numbers():
    """Sanitizes butt_number column in QM_stock to ensure pure integer strings (removing BT- or other prefixes)."""
    try:
        conn = get_db_connection()
        if conn and conn.is_connected():
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, butt_number FROM QM_stock WHERE butt_number IS NOT NULL AND butt_number != '';")
            rows = cursor.fetchall()
            for row in rows:
                raw_b = str(row['butt_number']).strip()
                digits = re.sub(r'\D', '', raw_b)
                if digits and digits != raw_b:
                    cursor.execute("UPDATE QM_stock SET butt_number = %s WHERE id = %s;", (digits, row['id']))
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        print("Error sanitizing butt numbers:", e)


@qm_bp.route("/qm/get_last_butt_number")
def get_last_butt_number_route():
    """Finds highest integer butt number for a given weapon type in QM_stock and returns last & next expected butt number (1 if none exists)."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    weapon_type = request.args.get('weapon_type', '').strip()
    if not weapon_type:
        return jsonify({'success': False, 'message': 'Weapon type is required'}), 400

    # Auto sanitize DB entries if needed
    sanitize_qm_stock_butt_numbers()

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT butt_number FROM QM_stock WHERE LOWER(type) = LOWER(%s);", (weapon_type,))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()

            max_num = None

            for (b_no,) in rows:
                if not b_no:
                    continue
                digits = re.sub(r'\D', '', str(b_no))
                if digits:
                    val = int(digits)
                    if max_num is None or val > max_num:
                        max_num = val

            if max_num is not None:
                next_num = max_num + 1
                return jsonify({
                    'success': True,
                    'last_butt_number': str(max_num),
                    'next_butt_number': str(next_num),
                    'max_num': max_num
                })
            else:
                return jsonify({
                    'success': True,
                    'last_butt_number': None,
                    'next_butt_number': "1",
                    'max_num': 0
                })

        except Exception as e:
            print("Error fetching last butt number:", e)
            return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({'success': False, 'message': 'Database connection error'}), 500


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
    """Lookup a troop by army_number or name for the issue modal."""
    if 'username' not in session:
        return jsonify({'found': False, 'message': 'Unauthorized'}), 401

    query = request.args.get('army_number', '').strip() or request.args.get('q', '').strip() or request.args.get('name', '').strip()
    if not query:
        return jsonify({'found': False})

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT army_number, name, rank_name, company, section 
                FROM troops 
                WHERE LOWER(army_number) = LOWER(%s) OR LOWER(name) = LOWER(%s)
                   OR LOWER(army_number) LIKE LOWER(%s) OR LOWER(name) LIKE LOWER(%s)
                ORDER BY 
                    CASE 
                        WHEN LOWER(army_number) = LOWER(%s) THEN 1
                        WHEN LOWER(name) = LOWER(%s) THEN 2
                        ELSE 3
                    END
                LIMIT 1;
                """,
                (query, query, f"{query}%", f"{query}%", query, query)
            )
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            if row:
                return jsonify({
                    'found': True,
                    'army_number': row['army_number'],
                    'name': row['name'] or '',
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
    """Update company column in QM_stock for single or multiple weapon IDs."""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    data = request.get_json(silent=True) or request.form
    company = (data.get('company') or request.form.get('company') or '').strip()

    weapon_ids = []
    if request.is_json and isinstance(data.get('weapon_ids'), list):
        weapon_ids = [str(x).strip() for x in data.get('weapon_ids') if str(x).strip()]
    else:
        raw_list = request.form.getlist('weapon_id') or request.form.getlist('weapon_ids')
        if not raw_list and data.get('weapon_id'):
            raw_list = [str(data.get('weapon_id'))]
        if not raw_list and data.get('weapon_ids'):
            raw_list = str(data.get('weapon_ids')).split(',')

        for item in raw_list:
            for sub in str(item).split(','):
                if sub.strip():
                    weapon_ids.append(sub.strip())

    if not weapon_ids or not company:
        return jsonify({'success': False, 'message': 'At least one Weapon ID and a Company are required.'}), 400

    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            format_strings = ','.join(['%s'] * len(weapon_ids))
            sql = f"UPDATE QM_stock SET company = %s WHERE id IN ({format_strings});"
            params = [company] + weapon_ids
            cursor.execute(sql, tuple(params))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': f'{affected} weapon(s) assigned to {company} successfully!'
            })
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
