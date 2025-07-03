import streamlit as st

"""
Delete page for the Streamlit app.

`render_delete_page(get_connection, simple_rerun)` is imported
and called by app.py.
"""


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
        st.info("No user-created databases.")
        return

    # ── Drop a database ──────────────────────────────────────────────────────
    st.subheader("Drop an entire database")
    db_to_drop = st.selectbox("Select database", dbs, key="db_drop")
    confirm_drop_db = st.checkbox(
        f"Are you sure you want to drop database `{db_to_drop}`?", key="confirm_drop_db"
    )
    if st.button(f"❌ Drop database `{db_to_drop}`"):
        if confirm_drop_db:
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
        else:
            st.warning("Please confirm deletion by checking the box above.")
        return  # stop here so the rerun will refresh the list

    st.markdown("---")

    # ── Drop a table ─────────────────────────────────────────────────────────
    st.subheader("Drop a table from a database")
    db_for_tables = st.selectbox("Choose database", dbs, key="tbl_db_drop")
    try:
        conn = get_connection(db_for_tables); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info(f"No tables in `{db_for_tables}`.")
        return

    tbl_to_drop = st.selectbox("Select table", tables, key="tbl_drop")
    confirm_drop_tbl = st.checkbox(
        f"Are you sure you want to drop table `{tbl_to_drop}` from `{db_for_tables}`?", key="confirm_drop_tbl"
    )
    if st.button(f"❌ Drop table `{tbl_to_drop}` from `{db_for_tables}`"):
        if confirm_drop_tbl:
            try:
                conn = get_connection(db_for_tables); cur = conn.cursor()
                cur.execute(f"DROP TABLE `{tbl_to_drop}`")
                conn.commit()
                st.success(f"Table `{tbl_to_drop}` dropped.")
                simple_rerun()
            except Exception as e:
                st.error(f"Failed to drop table `{tbl_to_drop}`: {e}")
            finally:
                cur.close(); conn.close()
        else:
            st.warning("Please confirm deletion by checking the box above.")
        return  # stop here so the rerun will refresh the table list
