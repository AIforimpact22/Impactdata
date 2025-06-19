"""
Main Streamlit entry point.

Pages inside this file:
    • Provision Database
    • Database Browser
    • Edit Database
    • Delete          (delegated to delete.py, unchanged)
    • Connection Info (delegated to connection.py – NEW)

External modules:
    delete.py      → render_delete_page()
    connection.py  → render_connection_page()
"""

from __future__ import annotations
import re
import streamlit as st
import mysql.connector
import pandas as pd

# ---------- ACCESS CODE ----------
ACCESS_CODE = "meer"      # 🔐  change to your own!

if "access_granted" not in st.session_state:
    st.session_state.access_granted = False

if not st.session_state.access_granted:
    st.title("🔒 Access Protected")
    code = st.text_input("Enter Access Code", type="password")
    if st.button("Unlock"):
        st.session_state.access_granted = code == ACCESS_CODE
        st.rerun()
    st.stop()

# ---------- DATABASE CONFIG ----------
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025",
}

def get_connection(db_name: str | None = None):
    """Return a fresh mysql-connector connection (optionally to a specific DB)."""
    cfg = DB_CONFIG.copy()
    if db_name:
        cfg["database"] = db_name
    return mysql.connector.connect(**cfg)

# ---------- SMALL HELPER ----------
def _simple_rerun():
    st.session_state["_force_reload"] = True
    st.rerun()

# ---------- SIDEBAR NAV ----------
PAGES = [
    "Provision Database",
    "Database Browser",
    "Edit Database",
    "Connection Info",
    "Delete",
]
st.sidebar.title("Navigation")

if "page" not in st.session_state:
    st.session_state.page = PAGES[0]

for name in PAGES:
    if st.sidebar.button(name):
        st.session_state.page = name

# ---------- PAGE: PROVISION ----------
def page_provision():
    st.title("Provision New MySQL Database (+ Tables)")
    with st.form("create_db_form"):
        db_name = st.text_input("Database name (letters, numbers, underscores)")
        tables_sql = st.text_area(
            "Table SQL",
            "CREATE TABLE users (\n"
            "  id INT PRIMARY KEY AUTO_INCREMENT,\n"
            "  name VARCHAR(50),\n"
            "  email VARCHAR(100)\n);",
            height=180,
        )
        submit = st.form_submit_button("Create")

    if not submit:
        return

    if not db_name.replace("_", "").isalnum() or " " in db_name:
        st.error("Invalid database name – only letters, numbers, underscores.")
        return

    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE `{db_name}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        )
        conn.database = db_name
        for stmt in [s.strip() for s in re.split(r";\s*", tables_sql) if s.strip()]:
            cur.execute(stmt + ";")
        conn.commit()
        st.success(f"🎉 Database `{db_name}` and table(s) created!")

        # quick-start snippets
        st.markdown("---")
        st.markdown("### Remote connection examples")
        st.code(
            f"mysql -h {DB_CONFIG['host']} -P {DB_CONFIG['port']} "
            f"-u {DB_CONFIG['user']} -p {db_name}",
            language="bash",
        )
        st.code(
            f"""import mysql.connector
conn = mysql.connector.connect(
    host="{DB_CONFIG['host']}",
    port={DB_CONFIG['port']},
    user="{DB_CONFIG['user']}",
    password="YOUR_PASSWORD",
    database="{db_name}"
)""",
            language="python",
        )

    except Exception as e:
        st.error(e)
    finally:
        cur.close(); conn.close()

# ---------- PAGE: BROWSER ----------
def page_browser():
    st.title("Database Browser")
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall()
               if d[0] not in ("information_schema", "mysql",
                               "performance_schema", "sys")]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return

    db = st.selectbox("Database", dbs)
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables."); return

    st.subheader(f"Tables in `{db}`")
    for t in tables:
        col1, col2 = st.columns([2, 1])
        col1.write(f"**{t}**")
        if col2.button("Preview 20 rows", key=f"prev_{db}_{t}"):
            try:
                conn = get_connection(db); cur = conn.cursor()
                cur.execute(f"SELECT * FROM `{t}` LIMIT 20")
                cols = [d[0] for d in cur.description]
                data = cur.fetchall()
                st.dataframe(
                    pd.DataFrame(data, columns=cols), use_container_width=True
                )
            except Exception as e:
                st.error(e)
            finally:
                cur.close(); conn.close()

# ---------- PAGE: EDIT ----------
def page_edit():
    st.title("Edit Table Data")
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall()
               if d[0] not in ("information_schema", "mysql",
                               "performance_schema", "sys")]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No databases."); return
    db = st.selectbox("Database", dbs)

    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES"); tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables."); return
    tbl = st.selectbox("Table", tables)

    limit = st.number_input("Rows to load", 1, 200, 20)
    conn = get_connection(db); cur = conn.cursor()
    cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
    cols = [d[0] for d in cur.description]; rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        st.warning("Table is empty."); return

    pk_guess = cols[0] if "id" in cols[0].lower() else cols[0]
    pk_col = st.selectbox("Primary-key column", cols, index=cols.index(pk_guess))
    edited = st.data_editor(
        pd.DataFrame(rows, columns=cols),
        num_rows="dynamic",
        use_container_width=True,
    )

    if st.button("Save Changes"):
        changes = []
        for i, r in edited.iterrows():
            orig = rows[i]
            for c, nv in zip(cols, r):
                if nv != orig[cols.index(c)]:
                    changes.append((c, nv, pk_col, r[pk_col]))

        if not changes:
            st.info("Nothing changed."); return

        try:
            conn = get_connection(db); cur = conn.cursor()
            for col, new_val, pk, pk_val in changes:
                cur.execute(
                    f"UPDATE `{tbl}` SET `{col}`=%s WHERE `{pk}`=%s",
                    (new_val, pk_val),
                )
            conn.commit()
            st.success(f"{len(changes)} change(s) saved."); _simple_rerun()
        except Exception as e:
            st.error(e)
        finally:
            cur.close(); conn.close()

# ---------- EXTERNAL PAGES ----------
from delete import render_delete_page                     # unchanged
from connection import render_connection_page             # << NEW >>

# ---------- ROUTER ----------
match st.session_state.page:
    case "Provision Database": page_provision()
    case "Database Browser":   page_browser()
    case "Edit Database":      page_edit()
    case "Delete":             render_delete_page(get_connection, _simple_rerun)
    case "Connection Info":    render_connection_page(get_connection)
