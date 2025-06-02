import streamlit as st
import mysql.connector

# --- Superuser (admin) credentials for MySQL ---
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",         # Needs privilege to create DBs and users
    "password": "Noway2025"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

st.title("Create a New MySQL Database for Your App")

with st.form("create_db_form"):
    db_name = st.text_input("Database name (no spaces, only letters, numbers, underscores)")
    new_user = st.text_input("New username for this DB (optional)")
    new_password = st.text_input("Password for new user (optional)", type="password")
    submitted = st.form_submit_button("Create Database")

if submitted:
    # Basic input validation
    if not db_name.replace("_", "").isalnum() or " " in db_name:
        st.error("Invalid database name! Use only letters, numbers, underscores.")
    elif (new_user and not new_user.replace("_", "").isalnum()) or " " in new_user:
        st.error("Invalid username! Use only letters, numbers, underscores.")
    else:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            # 1. Create the new database
            cursor.execute(f"CREATE DATABASE `{db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            st.success(f"Database `{db_name}` created!")

            if new_user and new_password:
                # 2. Create user and grant all privileges on the new DB
                cursor.execute(
                    f"CREATE USER IF NOT EXISTS '{new_user}'@'%' IDENTIFIED BY '{new_password}';"
                )
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{new_user}'@'%';"
                )
                cursor.execute("FLUSH PRIVILEGES;")
                st.success(f"User `{new_user}` created and given access to `{db_name}`.")

                conn_info = {
                    "host": DB_CONFIG["host"],
                    "port": DB_CONFIG["port"],
                    "database": db_name,
                    "user": new_user,
                    "password": new_password,
                }
            else:
                # If not creating a user, show admin connection info for this DB
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

            cursor.close()
            conn.close()
        except Exception as e:
            st.error(f"Failed to create database or user: {e}")

# Optionally, show a list of all databases for reference
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
