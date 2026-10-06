
@qm_bp.route("/qm/issue")
def issue_page_route():
    if 'username' not in session:
        return redirect(url_for('login_route'))

    role = str(session.get('role', '')).strip().lower()
    if role != 'qm':
        return redirect(url_for('coy.coy_dashboard_route'))

    conn = get_db_connection()
    available_weapons = []

    if conn and conn.is_connected():
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT qs.id, qs.s_no, qs.type, qs.butt_number, qs.register_number,
                       qs.weapon_status, qs.added_on,
                       cw.image_path
                FROM QM_stock qs
                LEFT JOIN core_weapons cw ON LOWER(cw.weapon_type) = LOWER(qs.type)
                WHERE LOWER(qs.weapon_status) = 'available'
                ORDER BY qs.type ASC, qs.s_no ASC;
            """)
            available_weapons = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print("Error fetching available weapons for issue page:", e)

    return render_template(
        'QM/issue.html',
        username=session.get('username'),
        role=session.get('role'),
        available_weapons=available_weapons
    )
