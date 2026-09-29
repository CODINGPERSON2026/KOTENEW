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


# Lightweight compatibility stubs for legacy startup calls
def create_users_table(): pass
def update_user_roles(): pass
def create_core_weapons_table(): pass
def create_qm_stock_table(): pass
def create_troops_table(): pass
def create_issuance_logs_table(): pass
def create_weapon_history_sheets_table(): pass
def create_weapon_incharge_history_table(): pass
def drop_coy_issuance_table(): pass