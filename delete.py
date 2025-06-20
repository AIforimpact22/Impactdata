# delete.py
"""
Delete page for the Streamlit app.

`render_delete_page(get_connection, simple_rerun)` is imported
and called by app.py.
"""

import streamlit as st
import pandas as pd

def render_delete_page(get_connection, simple_rerun):
    st.title("Delete Database or Table")

    # ── Fetch user databases ─────────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [
            d[0] for d in cur.fetchall()
            if d[0] not in ("information_schema", "mysql", "performance_schema", "sys")
        ]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); 
        return

    # ── Section: Drop entire database ────────────────────────────────────────
    with st.expander("Drop a whole database", expanded=True):
        with st.form("drop_db_form"):
            db_to_drop = st.selectbox("Select database to drop", dbs, key="drop_db_select")
            confirm_db = st.form_submit_button(f"⚠️ Drop database `{db_to_drop}`")
        if confirm_db:
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute(f"DROP DATABASE `{db_to_drop}`")
                conn.commit()
                st.success(f"Database `{db_to_drop}` deleted.")
                simple_rerun()
            except Exception as e:
                st.error(f"Failed to drop `{db_to_drop}`: {e}")
            finally:
                cur.close(); conn.close()
            return  # stop further rendering to let rerun refresh the list

    # ── Section: Drop individual table ────────────────────────────────────────
    db_for_tables = st.selectbox("Database for table operations", dbs, key="table_db_select")
    try:
        conn = get_connection(db_for_tables); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info(f"No tables inside database `{db_for_tables}`.")
        return

    with st.expander(f"Drop a table from `{db_for_tables}`", expanded=True):
        with st.form("drop_table_form"):
            tbl = st.selectbox("Select table to drop", tables, key="drop_tbl_select")
            confirm_tbl = st.form_submit_button(f"⚠️ Drop table `{tbl}`")
        if confirm_tbl:
            try:
                conn = get_connection(db_for_tables); cur = conn.cursor()
                cur.execute(f"DROP TABLE `{tbl}`")
                conn.commit()
                st.success(f"Table `{tbl}` dropped from `{db_for_tables}`.")
                simple_rerun()
            except Exception as e:
                st.error(f"Failed to drop table `{tbl}`: {e}")
            finally:
                cur.close(); conn.close()
            return  # stop to let rerun refresh the list

