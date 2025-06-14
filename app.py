import streamlit as st
import mysql.connector
import pandas as pd
import re

# --- ACCESS CODE GATE ---
ACCESS_CODE = "meer"   # <-- Set your real code!

if "access_granted" not in st.session_state:
    st.session_state.access_granted = False

if not st.session_state.access_granted:
    st.title("🔒 Access Protected")
    code = st.text_input("Enter Access Code:", type="password")
    if st.button("Unlock"):
        if code == ACCESS_CODE:
            st.session_state.access_granted = True
            st.experimental_rerun()
        else:
            st.error("Invalid code. Please try again.")
    st.stop()

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

# --- Sidebar navigation ---
st.sidebar.title("Navigation")
if "page" not in st.session_state:
    st.session_state.page = "Provision Database"

if st.sidebar.button("Provision Database"):
    st.session_state.page = "Provision Database"
if st.sidebar.button("Database Browser"):
    st.session_state.page = "Database Browser"
if st.sidebar.button("Edit Database"):
    st.session_state.page = "Edit Database"
if st.sidebar.button("Connection Info"):
    st.session_state.page = "Connection Info"
if st.sidebar.button("Delete"):
    st.session_state.page = "Delete"

def simple_rerun():
    st.session_state.deleted = True
    st.rerun()

if "deleted" in st.session_state:
    del st.session_state["deleted"]

# --- Page 1: Provision Database and Tables ---
if st.session_state.page == "Provision Database":
    st.title("Provision New MySQL Database (+Tables)")
    with st.form("create_db_form"):
        db_name = st.text_input("Database name (letters, numbers, underscores)")
        tables_sql = st.text_area(
            "Table SQL (enter one or more CREATE TABLE statements for your new database)",
            "CREATE TABLE users (\n  id INT PRIMARY KEY AUTO_INCREMENT,\n  name VARCHAR(50),\n  email VARCHAR(100)\n);"
        )
        submitted = st.form_submit_button("Create Database and Tables")
    if submitted:
        if not db_name.replace("_", "").isalnum() or " " in db_name:
            st.error("Invalid database name! Use only letters, numbers, underscores.")
        else:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE `{db_name}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                st.success(f"Database `{db_name}` created!")
                conn.database = db_name
                cursor = conn.cursor()
                stmts = [s.strip() for s in re.split(r';\s*', tables_sql) if s.strip()]
                for stmt in stmts:
                    cursor.execute(stmt + ";")
                conn.commit()
                st.success("Table(s) created successfully!")
                cursor.close()
                conn.close()
                st.markdown("---")
                st.success("🎉 Database successfully created!\n")
                st.markdown("### How to Connect Remotely")
                st.markdown("**From another device, use these connection settings:**")
                st.markdown("#### MySQL Command Line:")
                st.code(
                    f"mysql -h {DB_CONFIG['host']} -P {DB_CONFIG['port']} -u {DB_CONFIG['user']} -p {db_name}",
                    language="bash"
                )
                st.write("Enter your password when prompted.")
                st.markdown("#### Python (mysql-connector-python):")
                st.code(
                    f"""import mysql.connector

conn = mysql.connector.connect(
    host="{DB_CONFIG['host']}",
    port={DB_CONFIG['port']},
    user="{DB_CONFIG['user']}",
    password="YOUR_PASSWORD",
    database="{db_name}"
)
# ... your code ...
""", language="python"
                )
                st.markdown("#### PHP (PDO):")
                st.code(
                    f"""$pdo = new PDO('mysql:host={DB_CONFIG['host']};port={DB_CONFIG['port']};dbname={db_name}', '{DB_CONFIG['user']}', 'Noway2025');""",
                    language="php"
                )
                st.markdown("""
---
- **Replace** `YOUR_PASSWORD` with your actual password.
- Use the username and database as shown above.
- Make sure your app/server is allowed to reach `188.36.44.146:8081` (open on your firewall/router).
---
""")
            except Exception as e:
                st.error(f"Failed to create database or tables: {e}")

# --- Page 2: Database Browser with Table Data Preview ---
elif st.session_state.page == "Database Browser":
    st.title("Database Browser")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
        cursor.close()
        conn.close()
        if dbs:
            selected_db = st.selectbox("Select a database to browse:", dbs, key="browser_db_select")
            try:
                db_conn = get_connection(selected_db)
                db_cursor = db_conn.cursor()
                db_cursor.execute("SHOW TABLES")
                tables = [r[0] for r in db_cursor.fetchall()]
                db_cursor.close()
                db_conn.close()
                if tables:
                    st.write(f"**Tables in `{selected_db}`:**")
                    for table in tables:
                        col1, col2 = st.columns([2, 1])
                        with col1:
                            st.write(f"**{table}**")
                        with col2:
                            if st.button(f"Show first 20 rows", key=f"preview_{selected_db}_{table}"):
                                try:
                                    t_conn = get_connection(selected_db)
                                    t_cursor = t_conn.cursor()
                                    t_cursor.execute(f"SELECT * FROM `{table}` LIMIT 20")
                                    columns = [desc[0] for desc in t_cursor.description]
                                    data = t_cursor.fetchall()
                                    t_cursor.close()
                                    t_conn.close()
                                    df = pd.DataFrame(data, columns=columns)
                                    st.dataframe(df, use_container_width=True)
                                except Exception as err:
                                    st.error(f"Could not fetch data from `{table}`: {err}")
                else:
                    st.info("No tables in this database.")
            except Exception as err:
                st.error(f"Could not show tables for `{selected_db}`: {err}")
        else:
            st.info("No user-created databases found.")
    except Exception as e:
        st.error(f"Error connecting to MySQL: {e}")

# --- Page 3: Edit Database (NEW!) ---
elif st.session_state.page == "Edit Database":
    st.title("Edit Database/Table Data")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
        cursor.close()
        conn.close()
        if dbs:
            selected_db = st.selectbox("Database", dbs, key="edit_db_select")
            try:
                db_conn = get_connection(selected_db)
                db_cursor = db_conn.cursor()
                db_cursor.execute("SHOW TABLES")
                tables = [r[0] for r in db_cursor.fetchall()]
                db_cursor.close()
                db_conn.close()
                if tables:
                    selected_table = st.selectbox("Table", tables, key="edit_table_select")
                    edit_limit = st.number_input("Rows to load (max):", min_value=1, max_value=200, value=20, step=1)
                    t_conn = get_connection(selected_db)
                    t_cursor = t_conn.cursor()
                    t_cursor.execute(f"SELECT * FROM `{selected_table}` LIMIT {edit_limit}")
                    columns = [desc[0] for desc in t_cursor.description]
                    data = t_cursor.fetchall()
                    t_cursor.close()
                    t_conn.close()
                    df = pd.DataFrame(data, columns=columns)
                    if not df.empty:
                        st.info("Edit any cell below and click **Save Changes**. (Primary Key required!)")
                        pk_guess = columns[0] if 'id' in columns[0].lower() else columns[0]  # Just a best guess
                        pk_col = st.selectbox("Primary key column", columns, index=columns.index(pk_guess) if pk_guess in columns else 0)
                        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="edit_df")
                        if st.button("Save Changes"):
                            changes = []
                            for i, row in edited_df.iterrows():
                                orig_row = df.iloc[i]
                                for col in columns:
                                    if row[col] != orig_row[col]:
                                        # Prepare the UPDATE statement
                                        changes.append((col, row[col], pk_col, row[pk_col]))
                            if not changes:
                                st.info("No changes detected.")
                            else:
                                try:
                                    t_conn = get_connection(selected_db)
                                    t_cursor = t_conn.cursor()
                                    for col, new_val, pk, pk_val in changes:
                                        # Use %s to prevent SQL injection; handle None/null as well
                                        t_cursor.execute(
                                            f"UPDATE `{selected_table}` SET `{col}`=%s WHERE `{pk}`=%s",
                                            (new_val, pk_val)
                                        )
                                    t_conn.commit()
                                    t_cursor.close()
                                    t_conn.close()
                                    st.success(f"{len(changes)} change(s) saved successfully!")
                                    st.experimental_rerun()
                                except Exception as e:
                                    st.error(f"Error saving changes: {e}")
                    else:
                        st.warning("Table is empty. Nothing to edit.")
                else:
                    st.info("No tables in this database.")
            except Exception as e:
                st.error(f"Could not fetch tables: {e}")
        else:
            st.info("No user-created databases found.")
    except Exception as e:
        st.error(f"Error connecting to MySQL: {e}")

# --- Page 4: Connection Info for Any Database (admin only) ---
elif st.session_state.page == "Connection Info":
    st.title("Database Connection Info")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
        cursor.close()
        conn.close()
        if dbs:
            selected_db = st.selectbox("Select a database to show connection info:", dbs, key="conn_db_select")
            st.markdown("### Connection Information (using admin user)")
            st.code(
                f"mysql -h {DB_CONFIG['host']} -P {DB_CONFIG['port']} -u {DB_CONFIG['user']} -p {selected_db}",
                language="bash"
            )
            st.markdown("#### Python (mysql-connector-python):")
            st.code(
                f"""import mysql.connector

conn = mysql.connector.connect(
    host="{DB_CONFIG['host']}",
    port={DB_CONFIG['port']},
    user="{DB_CONFIG['user']}",
    password="YOUR_PASSWORD",
    database="{selected_db}"
)
""", language="python"
            )
            st.markdown("#### PHP (PDO):")
            st.code(
                f"""$pdo = new PDO('mysql:host={DB_CONFIG['host']};port={DB_CONFIG['port']};dbname={selected_db}', '{DB_CONFIG['user']}', 'YOUR_PASSWORD');""",
                language="php"
            )
            st.markdown("""
---
- **Replace** `YOUR_PASSWORD` with your actual password.
- Use the username and database as shown above.
- Make sure your app/server can reach `188.36.44.146:8081`.
---
""")
        else:
            st.info("No user-created databases found.")
    except Exception as e:
        st.error(f"Error connecting to MySQL: {e}")

# --- Page 5: Delete Database or Table (instant update!) ---
elif st.session_state.page == "Delete":
    st.title("Delete Database or Table")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall() if row[0] not in ['information_schema', 'mysql', 'performance_schema', 'sys']]
        cursor.close()
        conn.close()
        if dbs:
            selected_db = st.selectbox("Select database:", dbs, key="delete_db_select")
            col_db, col_table = st.columns(2)
            with col_db:
                if st.button(f"❌ Delete ENTIRE database `{selected_db}`", key="delete_db_btn"):
                    st.warning(f"This will permanently delete database `{selected_db}` and ALL its data.")
                    if st.button("Confirm database delete", key="confirm_delete_db_btn"):
                        try:
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute(f"DROP DATABASE `{selected_db}`")
                            conn.commit()
                            cursor.close()
                            conn.close()
                            st.success(f"Database `{selected_db}` deleted!")
                            simple_rerun()
                        except Exception as e:
                            st.error(f"Could not delete database: {e}")
            # List tables for deletion
            with col_table:
                try:
                    conn = get_connection(selected_db)
                    cursor = conn.cursor()
                    cursor.execute("SHOW TABLES")
                    tables = [r[0] for r in cursor.fetchall()]
                    cursor.close()
                    conn.close()
                    if tables:
                        selected_table = st.selectbox("Select table to delete:", tables, key="delete_table_select")
                        if st.button(f"Delete table `{selected_table}` from `{selected_db}`", key="delete_table_btn"):
                            st.warning(f"This will permanently delete table `{selected_table}` from `{selected_db}`.")
                            if st.button("Confirm table delete", key="confirm_delete_table_btn"):
                                try:
                                    conn = get_connection(selected_db)
                                    cursor = conn.cursor()
                                    cursor.execute(f"DROP TABLE `{selected_table}`")
                                    conn.commit()
                                    cursor.close()
                                    conn.close()
                                    st.success(f"Table `{selected_table}` deleted from `{selected_db}`!")
                                    simple_rerun()
                                except Exception as e:
                                    st.error(f"Could not delete table: {e}")
                    else:
                        st.info("No tables in this database to delete.")
                except Exception as e:
                    st.error(f"Could not fetch tables: {e}")
        else:
            st.info("No user-created databases found.")
    except Exception as e:
        st.error(f"Error connecting to MySQL: {e}")
