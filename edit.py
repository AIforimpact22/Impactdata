"""
edit.py – Spreadsheet-style data editor + free-form SQL editor.

Imported by app.py
------------------
    from edit import render_edit_page

Public API
----------
render_edit_page(get_connection, simple_rerun)

Expected callbacks
------------------
get_connection(db: str | None) -> mysql.connector connection
simple_rerun()                  -> sets a flag then st.rerun()
"""
from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = (
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
)


# --------------------------------------------------------------------------- #
#  Main entry                                                                  #
# --------------------------------------------------------------------------- #
def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # ────────────────────────────────────────────────────────────────────
    # 1. Pick database
    # ────────────────────────────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return

    db = st.selectbox("Database", dbs)

    # Tabs
    tab_sheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # ======================================================================
    # TAB 1 – Spreadsheet Editor
    # ======================================================================
    with tab_sheet:
        # 1-a. Pick table
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

        # 1-b. Pull rows
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        # 1-c. Detect PK column
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute(
                f"SHOW KEYS FROM `{tbl}` WHERE Key_name='PRIMARY'"
            )
            pk_info = cur.fetchone()
        finally:
            cur.close(); conn.close()

        pk_col_auto = pk_info[4] if pk_info else cols[0]   # Column_name
        pk_col = st.selectbox(
            "Primary-key column",
            cols,
            index=cols.index(pk_col_auto),
        )

        # 1-d. DataFrames
        orig_df = pd.DataFrame(rows, columns=cols)
        edited_df = st.data_editor(
            orig_df,
            num_rows="dynamic",
            use_container_width=True,
            key="sheet_editor",
        )

        # Ensure every pd.NA → None to avoid ambiguity later
        edited_df = edited_df.where(pd.notnull, None)

        # ------------------------------------------------------------------
        # 1-e. SAVE
        # ------------------------------------------------------------------
        if st.button("Save Changes", key="save_btn"):
            try:
                conn = get_connection(db); cur = conn.cursor()

                orig_pk_set = set(orig_df[pk_col].dropna())

                # ---------- DELETES (PK present before, missing after) -----
                edited_pk_set = set(edited_df[pk_col].dropna())
                del_pks = orig_pk_set - edited_pk_set
                del_cnt = 0
                for pk_val in del_pks:
                    cur.execute(
                        f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s",
                        (pk_val,),
                    )
                    del_cnt += cur.rowcount

                # ---------- UPDATES (same PK, changed cells) ---------------
                upd_cnt = 0
                for pk_val in edited_pk_set & orig_pk_set:
                    row_old = orig_df.loc[orig_df[pk_col] == pk_val].iloc[0]
                    row_new = edited_df.loc[edited_df[pk_col] == pk_val].iloc[0]

                    for c in cols:
                        if row_new[c] != row_old[c]:
                            cur.execute(
                                f"UPDATE `{tbl}` SET `{c}`=%s "
                                f"WHERE `{pk_col}`=%s",
                                (row_new[c], pk_val),
                            )
                            upd_cnt += cur.rowcount

                # ---------- INSERTS (new PK or blank PK) -------------------
                ins_cnt = 0
                for _, row in edited_df.iterrows():
                    pk_val = row[pk_col]
                    # insert if PK is NULL / blank / 0 / ""  OR  not in original set
                    is_blank_pk = pk_val in (None, "", 0)
                    if is_blank_pk or pk_val not in orig_pk_set:
                        # skip completely blank placeholder rows
                        if all(pd.isna(row[c]) or row[c] == "" for c in cols):
                            continue
                        placeholders = ", ".join("%s" for _ in cols)
                        col_list     = ", ".join(f"`{c}`" for c in cols)
                        cur.execute(
                            f"INSERT INTO `{tbl}` ({col_list}) VALUES ({placeholders})",
                            tuple(row[c] for c in cols),
                        )
                        ins_cnt += cur.rowcount

                # ---------- COMMIT & FEEDBACK ------------------------------
                if del_cnt or upd_cnt or ins_cnt:
                    conn.commit()
                    parts = []
                    if ins_cnt: parts.append(f"🟢 {ins_cnt} insert")
                    if upd_cnt: parts.append(f"🟡 {upd_cnt} update")
                    if del_cnt: parts.append(f"🔴 {del_cnt} delete")
                    st.success(" | ".join(parts) + " committed.")
                    simple_rerun()
                else:
                    st.info("Nothing to save – no changes detected.")

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
            "SQL statements (semicolon-separated)",
            value=default_sql,
            height=200,
        )

        if st.button("Execute", key="exec_sql"):
            stmts = [
                s.strip() for s in re.split(r";\s*", sql_code) if s.strip()
            ]
            if not stmts:
                st.warning("Nothing to run."); return

            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False

                for idx, stmt in enumerate(stmts, 1):
                    st.markdown(f"##### Statement {idx}")
                    cur.execute(stmt)

                    if cur.with_rows:  # SELECT
                        st.dataframe(
                            pd.DataFrame(
                                cur.fetchall(),
                                columns=[d[0] for d in cur.description],
                            ),
                            use_container_width=True,
                        )
                    else:              # UPDATE / INSERT / DELETE
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
