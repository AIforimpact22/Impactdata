import streamlit as st
import mysql.connector

# --- Database Configuration ---
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025",
    "database": "my_streamlit_db"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

st.title("Create New Table and Generate Link")

# Table creation form
with st.form("create_table_form"):
    table_name = st.text_input("Table name (no spaces, only letters, numbers, and underscores)")
    columns = st.text_area(
        "Columns (e.g. `id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(50), email VARCHAR(100)`)",
        "id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(50), email VARCHAR(100)"
    )
    submit = st.form_submit_button("Create Table")

if submit:
    # Basic input validation
    if not table_name.replace("_", "").isalnum() or " " in table_name:
        st.error("Invalid table name! Use only letters, numbers, and underscores, no spaces.")
    else:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            sql = f"CREATE TABLE {table_name} ({columns})"
            cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
            st.success(f"Table `{table_name}` created successfully!")

            # Generate a "link" to view or interact with this table (e.g. yourapp.com/?table=tablename)
            base_url = "https://yourstreamlitappurl.com"  # Change this to your real Streamlit app URL
            table_link = f"{base_url}/?table={table_name}"
            st.write("Shareable link to access this table:")
            st.code(table_link)
            st.button("Copy Link", on_click=lambda: st.session_state.update({"_copied": True}))
            if st.session_state.get("_copied", False):
                st.success("Link copied! (or just highlight and copy manually)")

        except Exception as e:
            st.error(f"Failed to create table: {e}")

# Optionally, show all existing tables and links
try:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    if tables:
        st.write("**Existing tables and links:**")
        base_url = "https://yourstreamlitappurl.com"  # Change to your deployed Streamlit app URL
        for t in tables:
            st.write(f"• `{t}` — [Open Table Link]({base_url}/?table={t})")
except Exception as e:
    st.warning("Could not list tables. Check your connection or database.")

