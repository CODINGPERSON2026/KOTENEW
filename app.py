from imports import *
from qm import qm_bp
from coy import coy_bp
from issuance import issuance_bp

app = Flask(__name__)
app.secret_key = 'wms_secret_session_key_2026'  # Secret key for Flask sessions

# Register Blueprints
app.register_blueprint(qm_bp)
app.register_blueprint(coy_bp)
app.register_blueprint(issuance_bp)

# Automatically ensure CDN assets (FontAwesome CSS & webfonts) are saved locally for offline use
try:
    from download_cdn import ensure_cdn_downloaded
    ensure_cdn_downloaded()
except Exception as e:
    print("CDN Download check skipped:", e)



# Ensure database tables are created on startup
try:
    create_core_weapons_table()
    create_qm_stock_table()
    create_troops_table()
    create_issuance_logs_table()
    create_weapon_history_sheets_table()
    create_weapon_incharge_history_table()
    try:
        from db_connection import drop_coy_issuance_table, update_user_roles
        drop_coy_issuance_table()
        update_user_roles()
    except Exception as e:
        print("Database cleanup & role update notice:", e)
except Exception as e:
    print("Database table initialization notice:", e)


@app.route("/")
def home_route():
    # Check if user is logged in via session
    if 'username' not in session:
        return redirect(url_for('login_route'))
    
    # Role-based redirection: Only 'qm' role renders QM dashboard; all other users render COY dashboard
    role = str(session.get('role', '')).strip().lower()
    if role == 'qm':
        return redirect(url_for('qm.qm_dashboard_route'))
    else:
        return redirect(url_for('coy.coy_dashboard_route'))
    
    return render_template('index.html')


@app.route("/login", methods=['GET', 'POST'])
def login_route():
    # If user is already logged in, redirect to home
    if 'username' in session:
        return redirect(url_for('home_route'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check credentials in database
        conn = get_db_connection()
        if conn and conn.is_connected():
            try:
                cursor = conn.cursor(dictionary=True)
                query = "SELECT * FROM users WHERE username = %s AND password = %s"
                cursor.execute(query, (username, password))
                user = cursor.fetchone()
                cursor.close()
                conn.close()

                if user:
                    session['username'] = user['username']
                    session['role'] = user.get('role', 'user')
                    session['company'] = user.get('company') or user.get('role', '')
                    return redirect(url_for('home_route'))
                else:
                    flash('Invalid username or password')
            except Exception as e:
                print("Database error:", e)
                flash('An error occurred during authentication')
        else:
            flash('Database connection error')

    return render_template('login.html')


@app.route("/logout")
def logout_route():
    session.clear()
    return redirect(url_for('login_route'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4000)

