import streamlit as st
import mysql.connector
import re
import pandas as pd

# --- Database configuration for admin access ---
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025"
}

def get_connection(db_name=None):
    cfg = DB_CONFIG.copy()
    if db_name:
        cfg["database"] = db_name
    return mysql.connector.connect(**cfg)

def show_connection_instructions(db, user, password, host, port):
    st.markdown("#### Connection instructions for database `{}`:".format(db))
    st.markdown("**MySQL Command Line:**")
    st.code(f"mysql -h {host} -P {port} -u {user} -p {db}", language="bash")
    st.write("Enter your password when prompted.")

    st.markdown("**Python (mysql-connector-python):**")
    st.code(
        f"""import mysql.connector

conn = mysql.connector.connect(
    host="{host}",
    port={port},
    user="{user}",
    password="{password}",
    database="{db}"
)
# ... your code ...
""", language="python"
    )

    st.markdown("**PHP (PDO):**")
    st.code(
        f"""$pdo = new PDO('mysql:host={host};port={port};dbname={db}', '{user}', '{password}');""",
        language="php"
    )
    st.info("Replace `password` with your actual password as needed.")

# --- Sidebar navigation ---
st.sidebar.title("Navigation")
if "page" not in st.session_state:
    st.session_state.page = "Provision Database"

if st.sidebar.button("Provision Database"):
    st.session_state.page = "Provision Database"
if st.sidebar.button("Database Browser"):
    st.session_state.page = "Database Browser"

# --- Page 1: Provision Database, User, and Tables ---
if st.session_state.page == "Provision Database":
    st.title("Provision New MySQL Database (+Tables)")

    with st.form("create_db_form"):
        db_name = st.text_input("Database name (letters, numbers, underscores)")
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

                connection_user = DB_CONFIG["user"]
                connection_pass = DB_CONFIG["password"]
                if new_user and new_password:
                    cursor.execute(
                        f"CREATE USER IF NOT EXISTS '{new_user}'@'%' IDENTIFIED BY '{new_password}';"
                    )
                    cursor.execute(
                        f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{new_user}'@'%';"
                    )
                    cursor.execute("FLUSH PRIVILEGES;")
                    st.success(f"User `{new_user}` created and given access to `{db_name}`.")
                    connection_user = new_user
                    connection_pass = new_password

                # Switch to the new database and execute table SQL
                conn.database = db_name
                cursor = conn.cursor()
                stmts = [s.strip() for s in re.split(r';\s*', tables_sql) if s.strip()]
                for stmt in stmts:
                    cursor.execute(stmt + ";")
                conn.commit()
                st.success("Table(s) created successfully!")
                cursor.close()
                conn.close()

                # --- Show clear connection instructions for the created DB/user ---
                st.markdown("---")
                show_connection_instructions(
                    db=db_name,
                    user=connection_user,
                    password=connection_pass,
                    host=DB_CONFIG["host"],
                    port=DB_CONFIG["port"]
                )

            except Exception as e:
                st.error(f"Failed to create database, user, or tables: {e}")

# --- Page 2: Database Browser with Table Data Preview and Connection Info ---
elif st.session_state.page == "Database Browser":
    st.title("Database Browser")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
        cursor.close()

        if dbs:
            for db in dbs:
                with st.expander(f"Database: `{db}`"):
                    # Show connection info for admin user for each DB
                    show_connection_instructions(
                        db=db,
                        user=DB_CONFIG["user"],
                        password=DB_CONFIG["password"],
                        host=DB_CONFIG["host"],
                        port=DB_CONFIG["port"]
                    )

                    try:
                        db_conn = get_connection(db)
                        db_cursor = db_conn.cursor()
                        db_cursor.execute("SHOW TABLES")
                        tables = [r[0] for r in db_cursor.fetchall()]
                        db_cursor.close()
                        if tables:
                            st.write("**Tables:**")
                            for table in tables:
                                with st.expander(f"Table: **{table}**", expanded=False):
                                    preview = st.button(f"Show first 20 rows", key=f"preview_{db}_{table}")
                                    if preview:
                                        try:
                                            t_conn = get_connection(db)
                                            t_cursor = t_conn.cursor()
                                            t_cursor.execute(f"SELECT * FROM `{table}` LIMIT 20")
                                            columns = [desc[0] for desc in t_cursor.description]
                                            data = t_cursor.fetchall()
                                            t_cursor.close()
                                            t_conn.close()
                                            df = pd.DataFrame(data, columns=columns)
                                            st.dataframe(df)
                                        except Exception as err:
                                            st.error(f"Could not fetch data from `{table}`: {err}")
                        else:
                            st.info("No tables in this database.")
                        db_conn.close()
                    except Exception as err:
                        st.error(f"Could not show tables for `{db}`: {err}")
        else:
            st.info("No user-created databases found.")
        conn.close()
    except Exception as e:
        st.error(f"Error connecting to MySQL: {e}")
