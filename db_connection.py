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

    try:
        return mysql.connector.connect(**DB_CONFIG)

    except Error as e:
        print("Error connecting to MySQL:", e)
        return None


def create_users_table():
    """Creates the users table in the database if it doesn't already exist."""
    conn = get_db_connection()
    if not conn:
        print("Could not connect to database.")
        return False
    
    try:
        cursor = conn.cursor()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()

        # Seed initial default users if table is empty
        cursor.execute("SELECT COUNT(*) FROM users;")
        count = cursor.fetchone()[0]
        if count == 0:
            initial_users = [
                ('qm', '123456', 'qm'),
                ('3coy', '123456', '3 coy kote'),
                ('hqcoy', '123456', 'hq coy kote'),
                ('comncoy', '123456', 'comn coy kote')
            ]
            cursor.executemany(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s);",
                initial_users
            )
            conn.commit()
            print("Populated default users into 'users' table.")

        print("Table 'users' verified/created successfully.")
        return True
    except Error as e:
        print(f"Error creating table: {e}")
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def update_user_roles():
    """Updates user roles in MySQL users table (HQ Company, COMN Company, 3 Company, QM)."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = 'HQ Company' WHERE UPPER(username) = 'HQKOTE';")
        cursor.execute("UPDATE users SET role = 'COMN Company' WHERE UPPER(username) = 'CCKOTE';")
        cursor.execute("UPDATE users SET role = '3 Company' WHERE UPPER(username) = '3KOTE';")
        cursor.execute("UPDATE users SET role = 'QM' WHERE UPPER(username) = 'QM';")
        conn.commit()
        cursor.close()
        conn.close()
        print("Updated user roles in MySQL database successfully.")
        return True
    except Exception as e:
        print("Error updating user roles:", e)
        return False


def create_core_weapons_table():
    """Creates the core_weapons table in DB and populates initial weapons if empty."""
    conn = get_db_connection()
    if not conn:
        print("Could not connect to database.")
        return False
    
    try:
        cursor = conn.cursor()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS core_weapons (
            id INT AUTO_INCREMENT PRIMARY KEY,
            weapon_type VARCHAR(100) NOT NULL UNIQUE,
            image_path VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()

        # Seed initial weapons if table is empty
        cursor.execute("SELECT COUNT(*) FROM core_weapons;")
        count = cursor.fetchone()[0]
        if count == 0:
            initial_weapons = [
                ('AK-47 / AK Series Rifle', 'ak47.png'),
                ('9mm CMG Carbine Machine Gun', 'cmg_9mm.jpg'),
                ('INSAS 5.56mm Assault Rifle', 'insas_5.56.png'),
                ('INSAS 5.56mm Light Machine Gun', 'insas_lmg_5.56.jpg'),
                ('7.62mm Light Machine Gun (LMG)', 'lmg_7.62.png'),
                ('9mm Service Pistol', 'pistol.png')
            ]
            cursor.executemany(
                "INSERT INTO core_weapons (weapon_type, image_path) VALUES (%s, %s);",
                initial_weapons
            )
            conn.commit()
            print("Populated initial weapons into 'core_weapons'.")

        print("Table 'core_weapons' verified/created successfully.")
        return True
    except Error as e:
        print(f"Error creating core_weapons table: {e}")
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def create_qm_stock_table():
    """Creates the QM_stock table in DB if it doesn't already exist."""
    conn = get_db_connection()
    if not conn:
        print("Could not connect to database.")
        return False
    
    try:
        cursor = conn.cursor()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS QM_stock (
            id INT AUTO_INCREMENT PRIMARY KEY,
            type VARCHAR(100) NOT NULL,
            butt_number VARCHAR(50) NOT NULL,
            register_number VARCHAR(50) NOT NULL UNIQUE,
            weapon_status VARCHAR(50) NOT NULL DEFAULT 'Available',
            alloted_to_army_number VARCHAR(100) DEFAULT NULL,
            added_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()

        # Migration: ensure alloted_to_army_number column exists if table was created previously
        try:
            cursor.execute("SHOW COLUMNS FROM QM_stock LIKE 'alloted_to_army_number';")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE QM_stock ADD COLUMN alloted_to_army_number VARCHAR(100) DEFAULT NULL;")
                conn.commit()
                print("Added column 'alloted_to_army_number' to QM_stock table.")
        except Exception as ex:
            print("Notice verifying alloted_to_army_number column in QM_stock:", ex)

        # Seed / Ensure 30+ available weapons exist in QM_stock
        stock_weapons = [
            # AK-47 Rifles
            ('AK-47 / AK Series Rifle', 'BT-101', 'REG-AK47-001', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-102', 'REG-AK47-002', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-103', 'REG-AK47-003', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-104', 'REG-AK47-004', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-105', 'REG-AK47-005', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-106', 'REG-AK47-006', 'Available'),
            ('AK-47 / AK Series Rifle', 'BT-107', 'REG-AK47-007', 'Available'),
            
            # INSAS Assault Rifles
            ('INSAS 5.56mm Assault Rifle', 'BT-201', 'REG-INS-001', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-202', 'REG-INS-002', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-203', 'REG-INS-003', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-204', 'REG-INS-004', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-205', 'REG-INS-005', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-206', 'REG-INS-006', 'Available'),
            ('INSAS 5.56mm Assault Rifle', 'BT-207', 'REG-INS-007', 'Available'),

            # 9mm Service Pistols
            ('9mm Service Pistol', 'BT-301', 'REG-PST-001', 'Available'),
            ('9mm Service Pistol', 'BT-302', 'REG-PST-002', 'Available'),
            ('9mm Service Pistol', 'BT-303', 'REG-PST-003', 'Available'),
            ('9mm Service Pistol', 'BT-304', 'REG-PST-004', 'Available'),
            ('9mm Service Pistol', 'BT-305', 'REG-PST-005', 'Available'),
            ('9mm Service Pistol', 'BT-306', 'REG-PST-006', 'Available'),

            # 9mm CMG Carbines
            ('9mm CMG Carbine Machine Gun', 'BT-401', 'REG-CMG-001', 'Available'),
            ('9mm CMG Carbine Machine Gun', 'BT-402', 'REG-CMG-002', 'Available'),
            ('9mm CMG Carbine Machine Gun', 'BT-403', 'REG-CMG-003', 'Available'),
            ('9mm CMG Carbine Machine Gun', 'BT-404', 'REG-CMG-004', 'Available'),
            ('9mm CMG Carbine Machine Gun', 'BT-405', 'REG-CMG-005', 'Available'),
            ('9mm CMG Carbine Machine Gun', 'BT-406', 'REG-CMG-006', 'Available'),

            # 7.62mm Light Machine Guns
            ('7.62mm Light Machine Gun (LMG)', 'BT-501', 'REG-LMG-001', 'Available'),
            ('7.62mm Light Machine Gun (LMG)', 'BT-502', 'REG-LMG-002', 'Available'),
            ('7.62mm Light Machine Gun (LMG)', 'BT-503', 'REG-LMG-003', 'Available'),
            ('7.62mm Light Machine Gun (LMG)', 'BT-504', 'REG-LMG-004', 'Available'),
            ('7.62mm Light Machine Gun (LMG)', 'BT-505', 'REG-LMG-005', 'Available'),

            # INSAS LMG
            ('INSAS 5.56mm Light Machine Gun', 'BT-601', 'REG-INSLMG-001', 'Available'),
            ('INSAS 5.56mm Light Machine Gun', 'BT-602', 'REG-INSLMG-002', 'Available'),
            ('INSAS 5.56mm Light Machine Gun', 'BT-603', 'REG-INSLMG-003', 'Available'),
            ('INSAS 5.56mm Light Machine Gun', 'BT-604', 'REG-INSLMG-004', 'Available'),
            ('INSAS 5.56mm Light Machine Gun', 'BT-605', 'REG-INSLMG-005', 'Available')
        ]

        for w in stock_weapons:
            cursor.execute("""
                INSERT INTO QM_stock (type, butt_number, register_number, weapon_status)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE weapon_status = weapon_status;
            """, w)
        conn.commit()
        print("Populated/verified 30+ available weapons in 'QM_stock'.")

        print("Table 'QM_stock' verified/created successfully.")
        return True
    except Error as e:
        print(f"Error creating QM_stock table: {e}")
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def drop_coy_issuance_table():
    """Drops coy_issuance table from MySQL database if it exists."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS coy_issuance;")
        conn.commit()
        cursor.close()
        conn.close()
        print("Table 'coy_issuance' dropped successfully.")
        return True
    except Exception as e:
        print("Error dropping coy_issuance table:", e)
        return False


def create_troops_table():
    """Creates troops table in DB if it doesn't exist and seeds sample personnel data."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS troops (
            id INT AUTO_INCREMENT PRIMARY KEY,
            army_number VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(150) NOT NULL,
            rank_name VARCHAR(100) NOT NULL,
            company VARCHAR(100) NOT NULL,
            section VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_sql)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM troops;")
        count = cursor.fetchone()[0]
        if count == 0:
            initial_troops = [
                ('15489201A', 'Rajesh Kumar', 'Havildar', 'HQ Company', 'Sec 1'),
                ('15489202B', 'Amit Sharma', 'Naik', 'COMN Company', 'Sec 2'),
                ('16001234X', 'Suresh Verma', 'Sapper', '3 Company', 'HQ Sec'),
                ('JC-782190P', 'Ramesh Chand', 'Subedar', 'HQ Company', 'Admin Sec'),
                ('15123456M', 'Vikas Singh', 'Lance Naik', '3 Company', 'Sec 3')
            ]
            cursor.executemany(
                "INSERT INTO troops (army_number, name, rank_name, company, section) VALUES (%s, %s, %s, %s, %s);",
                initial_troops
            )
            conn.commit()
            print("Populated initial troops records into 'troops' table.")

        print("Table 'troops' verified/created successfully.")
        return True
    except Exception as e:
        print("Error creating troops table:", e)
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()



