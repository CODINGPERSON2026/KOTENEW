import mysql.connector
from mysql.connector import Error

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'qaz123QAZ!@#',
    'database': 'wms',
    'port': 3306
}


def get_db_connection():
    """Establishes and returns a connection to the MySQL database."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print("Error connecting to MySQL:", e)
        return None


def create_issuance_logs_table():
    """Ensures issuance_logs table exists in database."""
    conn = get_db_connection()
    if conn and conn.is_connected():
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS issuance_logs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    register_number VARCHAR(100),
                    butt_number VARCHAR(50),
                    weapon_type VARCHAR(100),
                    army_number VARCHAR(100),
                    troop_name VARCHAR(150),
                    rank_name VARCHAR(100),
                    company VARCHAR(100),
                    action_type VARCHAR(50),
                    barcode VARCHAR(100),
                    purpose VARCHAR(150),
                    duty_location VARCHAR(200),
                    biometric_status VARCHAR(100),
                    action_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    operator_username VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            cursor.close()
            conn.close()
            print("issuance_logs table checked/created successfully.")
        except Error as e:
            print("Error creating issuance_logs table:", e)


def create_users_table(): pass
def update_user_roles(): pass
def create_core_weapons_table(): pass
def create_qm_stock_table(): pass
def create_troops_table(): pass
def create_weapon_history_sheets_table(): pass
def create_weapon_incharge_history_table(): pass
def drop_coy_issuance_table(): pass

# Auto-run table creation check
create_issuance_logs_table()