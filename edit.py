# edit.py
"""
edit.py  –  Table spreadsheet editor  +  free-form SQL editor.

Public API (used by app.py):
    render_edit_page(get_connection, simple_rerun)

- get_connection(db_name:str|None)  → mysql.connector connection
- simple_rerun()                    → sets any flag then st.rerun()
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # ── choose DATABASE first ───────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return
    db = st.selectbox("Database", dbs)

    tab_spreadsheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # ── TAB 1: Spreadsheet Editor ────────────────────────────────────────────
    with tab_spreadsheet:
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this DB."); return
        tbl = st.selectbox("Table", tables)

        limit = st.number_input("Rows to load", min_value=1, max_value=200, value=20)
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty."); return

        # Guess primary key
        pk_guess = cols[0] if "id" in cols[0].lower() else cols[0]
        pk_col = st.selectbox("Primary-key column", cols, index=cols.index(pk_guess))

        # Show editable DataFrame
        df_orig = pd.DataFrame(rows, columns=cols)
        edited_df = st.data_editor(
            df_orig,
            num_rows="dynamic",
            use_container_width=True,
        )

        if st.button("Save Changes", key="save_changes_btn"):
            # Prepare sets and lists
            orig_pks = {row[cols.index(pk_col)] for row in rows}
            new_pks = set(edited_df[pk_col].dropna().tolist())

            updates: list[tuple[str, object, str, object]] = []
            deletions: set[object] = orig_pks - new_pks
            insertions: list[pd.Series] = []

            # Detect updates and insertions
            for idx, new_row in edited_df.iterrows():
                pk_val = new_row[pk_col]
                if pd.isna(pk_val) or pk_val not in orig_pks:
                    # New row (no original PK match)
                    insertions.append(new_row)
                else:
                    # Potential update
                    old_row = rows[idx]
                    for c in cols:
                        if new_row[c] != old_row[cols.index(c)]:
                            updates.append((c, new_row[c], pk_col, pk_val))

            if not updates and not deletions and not insertions:
                st.info("Nothing changed."); return

            try:
                conn = get_connection(db); cur = conn.cursor()

                # Apply updates
                for col, val, pk, pk_val in updates:
                    cur.execute(
                        f"UPDATE `{tbl}` SET `{col}` = %s WHERE `{pk}` = %s",
                        (val, pk_val)
                    )

                # Apply deletions
                for pk_val in deletions:
                    cur.execute(
                        f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s",
                        (pk_val,)
                    )

                # Apply insertions
                for new_row in insertions:
                    # Build INSERT ignoring auto-increment PK
                    cols_to_insert = []
                    vals = []
                    for field in cols:
                        if field == pk_col:
                            # If PK is auto-inc, skip it
                            continue
                        cols_to_insert.append(f"`{field}`")
                        vals.append(new_row[field])
                    cols_sql = ", ".join(cols_to_insert)
                    placeholders = ", ".join("%s" for _ in vals)
                    cur.execute(
                        f"INSERT INTO `{tbl}` ({cols_sql}) VALUES ({placeholders})",
                        vals
                    )

                conn.commit()

                msg_parts = []
                if updates:
                    msg_parts.append(f"{len(updates)} update(s)")
                if deletions:
                    msg_parts.append(f"{len(deletions)} deletion(s)")
                if insertions:
                    msg_parts.append(f"{len(insertions)} insertion(s)")
                st.success(", ".join(msg_parts) + " applied.")
                simple_rerun()
            except Exception as e:
                st.error(f"Error saving changes: {e}")
            finally:
                cur.close(); conn.close()

    # ── TAB 2: SQL Editor ─────────────────────────────────────────────────────
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")
        default_sql = (
            "-- Example:\n"
            "SELECT * FROM your_table LIMIT 10;\n\n"
            "-- UPDATE your_table SET col = 'value' WHERE id = 1;"
        )
        sql_code = st.text_area(
            "SQL statements (separate with semicolons)",
            value=default_sql,
            height=200
        )
        if st.button("Execute", key="execute_sql_btn"):
            statements = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not statements:
                st.warning("Nothing to run."); return
            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False
                for idx, stmt in enumerate(statements, start=1):
                    st.markdown(f"##### Statement {idx}")
                    cur.execute(stmt)
                    if cur.with_rows:
                        rows2 = cur.fetchmany(200)
                        cols2 = [d[0] for d in cur.description]
                        st.dataframe(pd.DataFrame(rows2, columns=cols2), use_container_width=True)
                        if cur.rowcount == -1:
                            st.caption("Showing first 200 rows.")
                    else:
                        any_write = True
                        st.success(f"{cur.rowcount} row(s) affected.")
                if any_write:
                    conn.commit()
                    st.success("Changes committed.")
            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                cur.close(); conn.close()
