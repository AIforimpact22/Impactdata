# edit.py
"""
edit.py  –  Table spreadsheet editor + free-form SQL editor.

Public API (used by app.py):
    render_edit_page(get_connection, simple_rerun)

- get_connection(db_name:str|None) → mysql.connector connection
- simple_rerun() → sets any flag then st.rerun()
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # Choose database
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases.")
        return
    db = st.selectbox("Select Database", dbs)

    tab_spreadsheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # TAB 1: Spreadsheet Editor
    with tab_spreadsheet:
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
            return
        tbl = st.selectbox("Select Table", tables)

        # Fetch all rows (no limit) for editing
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}`")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        df_orig = pd.DataFrame(rows, columns=cols)
        edited_df = st.data_editor(df_orig, num_rows="dynamic", use_container_width=True)

        # Primary key selection
        pk_default = cols[0]
        for c in cols:
            if 'id' in c.lower():
                pk_default = c
                break
        pk_col = st.selectbox("Primary-key column", cols, index=cols.index(pk_default))

        if st.button("Save Changes"):
            # Map original and new rows by PK
            orig_map = {row[cols.index(pk_col)]: row for row in rows}
            new_map = {r[pk_col]: r for _, r in edited_df.iterrows() if not pd.isna(r[pk_col])}

            orig_keys = set(orig_map.keys())
            new_keys = set(new_map.keys())

            deletions = orig_keys - new_keys
            additions_keys = new_keys - orig_keys
            updates_keys = orig_keys & new_keys

            additions = [new_map[k] for k in additions_keys]
            updates = []
            for k in updates_keys:
                old_row = orig_map[k]
                new_row = new_map[k]
                for col in cols:
                    old_val = old_row[cols.index(col)]
                    new_val = new_row[col]
                    if pd.isna(old_val) and pd.isna(new_val):
                        continue
                    if old_val != new_val:
                        updates.append((col, new_val, k))

            if not (deletions or additions or updates):
                st.info("Nothing changed.")
                return

            try:
                conn = get_connection(db); cur = conn.cursor()
                # Deletions
                for k in deletions:
                    cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s", (k,))
                # Updates
                for col, val, k in updates:
                    cur.execute(
                        f"UPDATE `{tbl}` SET `{col}` = %s WHERE `{pk_col}` = %s",
                        (val, k)
                    )
                # Additions
                for new_row in additions:
                    cols_ins, vals_ins = [], []
                    for col in cols:
                        v = new_row[col]
                        if pd.isna(v) or (col == pk_col and v in (None, '', 0)):
                            continue
                        cols_ins.append(f"`{col}`")
                        vals_ins.append(v)
                    if vals_ins:
                        placeholders = ','.join(['%s'] * len(vals_ins))
                        cols_str = ','.join(cols_ins)
                        cur.execute(
                            f"INSERT INTO `{tbl}` ({cols_str}) VALUES ({placeholders})", tuple(vals_ins)
                        )
                conn.commit()
                msgs = []
                if additions:
                    msgs.append(f"{len(additions)} addition(s)")
                if updates:
                    msgs.append(f"{len(updates)} update(s)")
                if deletions:
                    msgs.append(f"{len(deletions)} deletion(s)")
                st.success("; ".join(msgs) + " applied.")
                simple_rerun()
            except Exception as e:
                st.error(f"Error saving changes: {e}")
            finally:
                cur.close(); conn.close()

    # TAB 2: SQL Editor
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")
        default_sql = (
            "-- Example:\n"
            "SELECT * FROM your_table LIMIT 10;\n\n"
            "-- UPDATE your_table SET col = 'value' WHERE id = 1;"
        )
        sql_code = st.text_area("SQL statements (separate with semicolons)", value=default_sql, height=200)
        if st.button("Execute SQL"):
            stmts = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not stmts:
                st.warning("Nothing to run.")
                return
            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False
                for idx, stmt in enumerate(stmts, start=1):
                    st.markdown(f"##### Statement {idx}")
                    cur.execute(stmt)
                    if cur.with_rows:
                        df = pd.DataFrame(cur.fetchmany(200), columns=[d[0] for d in cur.description])
                        st.dataframe(df, use_container_width=True)
                    else:
                        any_write = True
                        st.success(f"{cur.rowcount} row(s) affected.")
                if any_write:
                    conn.commit()
                    st.success("Changes committed.")
            except Exception as e:
                st.error(f"SQL error: {e}")
            finally:
                cur.close(); conn.close()
