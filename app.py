import streamlit as st
import mysql.connector

# --- Superuser (admin) credentials for MySQL ---
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025"
}

def get_connection(db_name=None):
    cfg = DB_CONFIG.copy()
    if db_name:
        cfg['database'] = db_name
    return mysql.connector.connect(**cfg)

st.title("Provision New MySQL Database (+Tables)")

with st.form("create_db_form"):
    db_name = st.text_input("Database name (no spaces, only letters, numbers, underscores)")
    new_user = st.text_input("New username for this DB (optional)")
    new_password = st.text_input("Password for new user (optional)", type="password")
    tables_sql = st.text_area(
        "Table SQL (enter one or more CREATE TABLE statements for your new database)",
        "CREATE TABLE users (\n  id INT PRIMARY KEY AUTO_INCREMENT,\n  name VARCHAR(50),\n  email VARCHAR(100)\n);"
    )
    submitted = st.form_submit_button("Create Database and Tables")

if submitted:
    if not db_name.replace("_", "").isalnum() or " " in db_name:
        st.error("Invalid database name! Use only letters, numbers, underscores.")
    elif new_user and (not new_user.replace("_", "").isalnum() or " " in new_user):
        st.error("Invalid username! Use only letters, numbers, underscores.")
    else:
        try:
            # Create database and (optionally) user
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE `{db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            st.success(f"Database `{db_name}` created!")

            if new_user and new_password:
                cursor.execute(
                    f"CREATE USER IF NOT EXISTS '{new_user}'@'%' IDENTIFIED BY '{new_password}';"
                )
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{new_user}'@'%';"
                )
                cursor.execute("FLUSH PRIVILEGES;")
                st.success(f"User `{new_user}` created and given access to `{db_name}`.")

            # Switch to the new database and execute table SQL
            conn.database = db_name
            cursor = conn.cursor()
            # Support for multiple CREATE TABLE statements
            import re
            stmts = [s.strip() for s in re.split(r';\s*', tables_sql) if s.strip()]
            for stmt in stmts:
                cursor.execute(stmt + ";")
            conn.commit()
            st.success("Table(s) created successfully!")
            cursor.close()
            conn.close()

            # Show connection info for new DB/user
            if new_user and new_password:
                conn_info = {
                    "host": DB_CONFIG["host"],
                    "port": DB_CONFIG["port"],
                    "database": db_name,
                    "user": new_user,
                    "password": new_password,
                }
            else:
                conn_info = {
                    "host": DB_CONFIG["host"],
                    "port": DB_CONFIG["port"],
                    "database": db_name,
                    "user": DB_CONFIG["user"],
                    "password": DB_CONFIG["password"],
                }
            st.subheader("Connection Info:")
            st.code(
                f"mysql -h {conn_info['host']} -P {conn_info['port']} -u {conn_info['user']} -p {conn_info['database']}"
            )
            st.write("Or as a Python/MySQL connection string:")
            st.code(
                f"mysql.connector.connect(host='{conn_info['host']}', port={conn_info['port']}, user='{conn_info['user']}', password='***', database='{conn_info['database']}')"
            )
        except Exception as e:
            st.error(f"Failed to create database, user, or tables: {e}")

# Optionally show all user-created databases for reference
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES")
    dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
    cursor.close()
    conn.close()
    if dbs:
        st.write("**Existing databases:**")
        st.write(", ".join(f"`{db}`" for db in dbs))
except Exception as e:
    st.warning("Could not list databases.")
