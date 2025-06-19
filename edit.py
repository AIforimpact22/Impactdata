"""
Edit-Database page isolated from app.py.

Usage (from app.py):
    from edit import render_edit_page
    render_edit_page(get_connection, simple_rerun)

— get_connection(db_name?) must return a mysql-connector connection
— simple_rerun() should call st.rerun() after setting any flag
"""

import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

def render_edit_page(get_connection, simple_rerun):
    """Interactive table editor with immediate UPDATEs."""
    st.title("Edit Table Data")

    # ---- choose database ---------------------------------------------------
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return
    db = st.selectbox("Database", dbs)

    # ---- choose table ------------------------------------------------------
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables in this DB."); return
    tbl = st.selectbox("Table", tables)

    # ---- fetch rows --------------------------------------------------------
    limit = st.number_input("Rows to load", 1, 200, 20)
    conn = get_connection(db); cur = conn.cursor()
    cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        st.warning("Table is empty."); return

    pk_guess = cols[0] if "id" in cols[0].lower() else cols[0]
    pk_col = st.selectbox("Primary-key column", cols, index=cols.index(pk_guess))

    edited_df = st.data_editor(
        pd.DataFrame(rows, columns=cols),
        num_rows="dynamic",
        use_container_width=True,
    )

    # ---- save changes ------------------------------------------------------
    if st.button("Save Changes"):
        changes = []
        for i, row in edited_df.iterrows():
            orig = rows[i]
            for c in cols:
                if row[c] != orig[cols.index(c)]:
                    changes.append((c, row[c], pk_col, row[pk_col]))

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
            st.success(f"{len(changes)} change(s) saved.")
            simple_rerun()
        except Exception as e:
            st.error(e)
        finally:
            cur.close(); conn.close()
