# edit_db_page.py  ── Spreadsheet • SQL • New-Table
from __future__ import annotations
import re
import streamlit as st
import pandas as pd
import numpy as np

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

# ───────────────────────── utils ─────────────────────────
def _py(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return None
    if isinstance(val, np.generic):  return val.item()
    if isinstance(val, pd.Timestamp):return val.to_pydatetime()
    return val

# ───────────────────────── main entry ─────────────────────
def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # ---------- choose DB ----------
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases.")
        return

    db = st.selectbox("Database", dbs)
    tab_sheet, tab_sql, tab_new = st.tabs(
        ["Spreadsheet Editor", "SQL Editor", "New Table"]
    )

    # ==================================================================
    # TAB 1  ─ Spreadsheet Editor  (unchanged)
    # ==================================================================
    with tab_sheet:
        # … (existing spreadsheet editor logic) …
        # (Cut for brevity – keep exactly as in your working version)

        # ---------------------------------------------------------------------
        #  all original Spreadsheet Editor code remains here
        # ---------------------------------------------------------------------
        pass  # placeholder; keep previous code block

    # ==================================================================
    # TAB 2  ─ Free SQL Editor  (unchanged)
    # ==================================================================
    with tab_sql:
        # … (existing SQL editor logic) …
        pass  # placeholder; keep previous SQL-editor code

    # ==================================================================
    # TAB 3  ─ Create New Table via SQL
    # ==================================================================
    with tab_new:
        st.subheader(f"Create a new table in `{db}`")

        create_tpl = (
            "-- Write a full CREATE TABLE statement.\n"
            "-- Example:\n"
            "CREATE TABLE example_table (\n"
            "  id INT AUTO_INCREMENT PRIMARY KEY,\n"
            "  name VARCHAR(100),\n"
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n"
        )

        create_sql = st.text_area(
            "CREATE TABLE statement",
            value=st.session_state.get("create_sql", create_tpl),
            height=300,
            key="create_sql_area",
        )

        if st.button("Execute CREATE TABLE", key="exec_create"):
            try:
                conn = get_connection(db); cur = conn.cursor()
                cur.execute(create_sql)
                conn.commit()
                st.success("Table created successfully!")
                simple_rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"Creation failed: {e}")
            finally:
                cur.close(); conn.close()
