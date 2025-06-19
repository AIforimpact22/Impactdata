"""
Delete page for the Streamlit app.

`render_delete_page(get_connection, rerun_callback)` is imported
and called by app.py, so there is **no circular import**.
"""

import streamlit as st
import pandas as pd  # only needed for pretty display of tables

def render_delete_page(get_connection, simple_rerun):
    st.title("Delete Database or Table")
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

    db = st.selectbox("Select database", dbs)

    # --- Delete entire database ---
    if st.button(f"❌  Drop database `{db}`"):
        st.warning(f"This will permanently delete `{db}` and all its data.")
        if st.button("Confirm delete", key="confirm_db"):
            try:
                conn = get_connection(); cur = conn.cursor()
                cur.execute(f"DROP DATABASE `{db}`")
                conn.commit()
                st.success(f"Database `{db}` deleted.")
                simple_rerun()
            except Exception as e:
                st.error(e)
            finally:
                cur.close(); conn.close()
        st.stop()   # wait for confirmation

    # --- Delete individual tables ---
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables inside this database."); return

    tbl = st.selectbox("Table", tables)
    if st.button(f"Drop table `{tbl}`"):
        st.warning(f"This will permanently delete `{tbl}` from `{db}`.")
        if st.button("Confirm delete", key="confirm_tbl"):
            try:
                conn = get_connection(db); cur = conn.cursor()
                cur.execute(f"DROP TABLE `{tbl}`")
                conn.commit()
                st.success(f"Table `{tbl}` dropped.")
                simple_rerun()
            except Exception as e:
                st.error(e)
            finally:
                cur.close(); conn.close()
