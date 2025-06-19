"""
Streamlit entry-point.

Pages in this file:
    • Provision Database
    • Database Browser
Delegated pages (separate modules):
    • Edit Database     → edit.py
    • Connection Info   → connection.py
    • Delete            → delete.py
"""

from __future__ import annotations
import re
import streamlit as st
import mysql.connector
import pandas as pd

# ── ACCESS GATE ──────────────────────────────────────────────────────────────
ACCESS_CODE = "meer"  # 🔐 change this!

if "access_granted" not in st.session_state:
    st.session_state.access_granted = False

if not st.session_state.access_granted:
    st.title("🔒 Access Protected")
    pwd = st.text_input("Enter Access Code", type="password")
    if st.button("Unlock"):
        st.session_state.access_granted = pwd == ACCESS_CODE
        st.rerun()
    st.stop()

# ── DB CONFIG ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "188.36.44.146",
    "port": 8081,
    "user": "Hawkar",
    "password": "Noway2025",
}

def get_connection(db: str | None = None):
    cfg = DB_CONFIG.copy()
    if db:
        cfg["database"] = db
    return mysql.connector.connect(**cfg)

# ── MISC HELPER ──────────────────────────────────────────────────────────────
def _simple_rerun():
    st.session_state["_reload"] = True
    st.rerun()

# ── SIDEBAR NAV ──────────────────────────────────────────────────────────────
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

# ── PAGE: PROVISION ──────────────────────────────────────────────────────────
def page_provision():
    st.title("Provision New MySQL Database (+Tables)")
    with st.form("create_db_form"):
        db_name = st.text_input("Database name (letters, numbers, underscores)")
        tables_sql = st.text_area(
            "Table-definition SQL",
            "CREATE TABLE users (\n"
            "  id INT PRIMARY KEY AUTO_INCREMENT,\n"
            "  name VARCHAR(50),\n"
            "  email VARCHAR(100)\n);",
            height=180,
        )
        create = st.form_submit_button("Create")
    if not create:
        return

    if not db_name.replace("_", "").isalnum() or " " in db_name:
        st.error("Invalid database name."); return

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
        st.success(f"🎉 `{db_name}` and table(s) created!")

        st.markdown("### Quick connect")
        st.code(
            f"mysql -h {DB_CONFIG['host']} -P {DB_CONFIG['port']} "
            f"-u {DB_CONFIG['user']} -p {db_name}",
            language="bash",
        )
    except Exception as e:
        st.error(e)
    finally:
        cur.close(); conn.close()

# ── PAGE: BROWSER ────────────────────────────────────────────────────────────
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
        st.info("No databases yet."); return

    db = st.selectbox("Database", dbs)
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES"); tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables."); return

    for t in tables:
        col1, col2 = st.columns([2, 1])
        col1.write(f"**{t}**")
        if col2.button("Preview 20 rows", key=f"prev_{db}_{t}"):
            try:
                conn = get_connection(db); cur = conn.cursor()
                cur.execute(f"SELECT * FROM `{t}` LIMIT 20")
                cols = [d[0] for d in cur.description]
                st.dataframe(pd.DataFrame(cur.fetchall(), columns=cols),
                             use_container_width=True)
            except Exception as e:
                st.error(e)
            finally:
                cur.close(); conn.close()

# ── IMPORT DELEGATED PAGES ──────────────────────────────────────────────────
from delete import render_delete_page
from connection import render_connection_page
from edit import render_edit_page            #  << NEW >>

# ── ROUTER ───────────────────────────────────────────────────────────────────
match st.session_state.page:
    case "Provision Database": page_provision()
    case "Database Browser":   page_browser()
    case "Edit Database":      render_edit_page(get_connection, _simple_rerun)
    case "Connection Info":    render_connection_page(get_connection)
    case "Delete":             render_delete_page(get_connection, _simple_rerun)
