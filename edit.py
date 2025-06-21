"""
edit.py – Table spreadsheet editor  +  free-form SQL editor.

Public API (imported by app.py)
--------------------------------
    render_edit_page(get_connection, simple_rerun)

Required callbacks
------------------
get_connection(db_name:str|None)  → mysql.connector connection
simple_rerun()                    → sets a flag then st.rerun()
"""
from __future__ import annotations

import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql",
                    "performance_schema", "sys")


# --------------------------------------------------------------------------- #
#  Main entry point                                                           #
# --------------------------------------------------------------------------- #
def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # ───────────────────────────────────────────────────────────────────────
    # Choose DATABASE first
    # ───────────────────────────────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return

    db = st.selectbox("Database", dbs)

    # Two tabs
    tab_sheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # ======================================================================
    # TAB 1 – Spreadsheet Editor
    # ======================================================================
    with tab_sheet:
        # ------------------------------------------------------------------
        # pick table & row limit
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this DB."); return

        tbl = st.selectbox("Table", tables)
        limit = st.number_input("Rows to load", 1, 500, 20)

        # ------------------------------------------------------------------
        # pull rows
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty (you can still add rows).")

        # choose PK column (for UPDATE / DELETE)
        pk_guess = cols[0] if "id" in cols[0].lower() else cols[0]
        pk_col = st.selectbox("Primary-key column", cols,
                              index=cols.index(pk_guess))

        # original DataFrame (for diffing)
        orig_df = pd.DataFrame(rows, columns=cols)

        # editable grid
        edited_df = st.data_editor(
            orig_df,
            num_rows="dynamic",          # allows adding rows
            use_container_width=True,
            key="sheet_editor"
        )

        if st.button("Save Changes", key="save_btn"):
            try:
                conn = get_connection(db); cur = conn.cursor()

                # ----------------- PREP ORIGINAL / EDITED -----------------
                # ensure NaNs are turned into None for DB inserts
                edited_df = edited_df.where(pd.notnull(edited_df), None)

                orig_pk_set   = set(orig_df[pk_col].tolist())
                edited_pk_set = set(
                    edited_df[pk_col].dropna().tolist()
                )  # pk may be None for new rows

                # --------------------- DELETES ----------------------------
                to_delete = orig_pk_set - edited_pk_set
                delete_cnt = 0
                for pk_val in to_delete:
                    cur.execute(
                        f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s",
                        (pk_val,)
                    )
                    delete_cnt += cur.rowcount

                # -------------------- UPDATES -----------------------------
                update_cnt = 0
                for _, row in edited_df.iterrows():
                    pk_val = row[pk_col]
                    if pk_val in orig_pk_set:
                        # compare with original row
                        orig_row = orig_df.loc[
                            orig_df[pk_col] == pk_val
                        ].iloc[0]
                        for c in cols:
                            if row[c] != orig_row[c]:
                                cur.execute(
                                    f"UPDATE `{tbl}` SET `{c}`=%s "
                                    f"WHERE `{pk_col}`=%s",
                                    (row[c], pk_val)
                                )
                                update_cnt += cur.rowcount

                # -------------------- INSERTS -----------------------------
                insert_cnt = 0
                for _, row in edited_df.iterrows():
                    pk_val = row[pk_col]
                    if pk_val not in orig_pk_set:
                        # new row – build INSERT (skip completely-blank rows)
                        if all(row[c] in (None, "", pd.NA) for c in cols
                               if c != pk_col):
                            continue
                        placeholders = ", ".join("%s" for _ in cols)
                        col_list     = ", ".join(f"`{c}`" for c in cols)
                        cur.execute(
                            f"INSERT INTO `{tbl}` ({col_list}) "
                            f"VALUES ({placeholders})",
                            tuple(row[c] for c in cols)
                        )
                        insert_cnt += cur.rowcount

                conn.commit()
                msg = []
                if insert_cnt: msg.append(f"🟢 {insert_cnt} insert")
                if update_cnt: msg.append(f"🟡 {update_cnt} update")
                if delete_cnt: msg.append(f"🔴 {delete_cnt} delete")
                if msg:
                    st.success(" | ".join(msg) + " operation(s) committed.")
                else:
                    st.info("Nothing to save – no changes detected.")

                simple_rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Save failed: {e}")
            finally:
                cur.close(); conn.close()

    # ======================================================================
    # TAB 2 – Free SQL / DDL Editor
    # ======================================================================
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")

        default_sql = (
            "-- Example:\n"
            "SELECT * FROM your_table LIMIT 10;\n\n"
            "-- UPDATE your_table SET col = 'value' WHERE id = 1;"
        )
        sql_code = st.text_area(
            "SQL statements (one or more, separated by semicolons)",
            value=default_sql,
            height=200,
        )

        if st.button("Execute", key="execute_sql_btn"):
            stmts = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not stmts:
                st.warning("Nothing to run."); return

            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False

                for idx, stmt in enumerate(stmts, 1):
                    st.markdown(f"##### Statement {idx}")
                    cur.execute(stmt)

                    if cur.with_rows:          # SELECT (or similar)
                        rows = cur.fetchmany(200)
                        cols = [d[0] for d in cur.description]
                        st.dataframe(
                            pd.DataFrame(rows, columns=cols),
                            use_container_width=True,
                        )
                        if cur.rowcount == -1:
                            st.caption("Showing first 200 rows.")
                    else:                       # UPDATE / INSERT / DELETE
                        any_write = True
                        st.success(f"{cur.rowcount} row(s) affected.")

                if any_write:
                    conn.commit()
                    st.success("Changes committed.")
                    simple_rerun()

            except Exception as e:
                st.error(f"Execution failed: {e}")
            finally:
                cur.close(); conn.close()
