"""
edit.py – Table spreadsheet editor + free-form SQL editor.

Public API (imported by app.py)
--------------------------------
    render_edit_page(get_connection, simple_rerun)

Callbacks expected
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
    # Choose DATABASE
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

        # pull rows
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        # ── detect PK column from MySQL metadata ───────────────────────────
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute(
                f"SHOW KEYS FROM `{tbl}` WHERE Key_name = 'PRIMARY'")
            pk_info = cur.fetchone()
        finally:
            cur.close(); conn.close()

        pk_col_auto = pk_info[4] if pk_info else cols[0]  # Column_name
        pk_col = st.selectbox("Primary-key column", cols,
                              index=cols.index(pk_col_auto))

        orig_df = pd.DataFrame(rows, columns=cols)

        edited_df = st.data_editor(
            orig_df,
            num_rows="dynamic",
            use_container_width=True,
            key="sheet_editor"
        )

        if st.button("Save Changes", key="save_btn"):
            # Replace NaNs with None to make PyMySQL happy
            edited_df = edited_df.where(pd.notnull(edited_df), None)

            try:
                conn = get_connection(db); cur = conn.cursor()

                # ------------------ differences ---------------------------
                # sets of PK values (None removed)
                orig_pk_set   = set(orig_df[pk_col].dropna())
                edited_pk_set = set(edited_df[pk_col].dropna())

                # *Deletes* = PKs present before but not after
                to_delete = orig_pk_set - edited_pk_set

                # *Updates* = rows with same PK but different cells
                to_update = []
                for pk_val in edited_pk_set & orig_pk_set:
                    row_new = edited_df.loc[edited_df[pk_col] == pk_val].iloc[0]
                    row_old = orig_df.loc[orig_df[pk_col] == pk_val].iloc[0]
                    for c in cols:
                        if row_new[c] != row_old[c]:
                            to_update.append((c, row_new[c], pk_val))

                # *Inserts* = rows whose PK was NA before
                insert_rows = edited_df[edited_df[pk_col].isna()]

                # ---------------- execute SQL -----------------------------
                del_cnt = upd_cnt = ins_cnt = 0

                for pk_val in to_delete:
                    cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s",
                                (pk_val,))
                    del_cnt += cur.rowcount

                for col, new_val, pk_val in to_update:
                    cur.execute(
                        f"UPDATE `{tbl}` SET `{col}`=%s WHERE `{pk_col}`=%s",
                        (new_val, pk_val)
                    )
                    upd_cnt += cur.rowcount

                for _, row in insert_rows.iterrows():
                    if all(row[c] in (None, "", pd.NA) for c in cols):
                        # skip completely blank rows
                        continue
                    placeholders = ", ".join("%s" for _ in cols)
                    col_list = ", ".join(f"`{c}`" for c in cols)
                    cur.execute(
                        f"INSERT INTO `{tbl}` ({col_list}) VALUES ({placeholders})",
                        tuple(row[c] for c in cols)
                    )
                    ins_cnt += cur.rowcount

                if del_cnt or upd_cnt or ins_cnt:
                    conn.commit()
                else:
                    st.info("Nothing to save – no changes detected.")
                    return

                msg = []
                if ins_cnt: msg.append(f"🟢 {ins_cnt} insert")
                if upd_cnt: msg.append(f"🟡 {upd_cnt} update")
                if del_cnt: msg.append(f"🔴 {del_cnt} delete")
                st.success(" | ".join(msg) + " committed.")
                simple_rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Save failed: {e}")
            finally:
                cur.close(); conn.close()

    # ======================================================================
    # TAB 2 – Free SQL / DDL
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

                    if cur.with_rows:   # SELECT or similar
                        rows = cur.fetchmany(200)
                        cols = [d[0] for d in cur.description]
                        st.dataframe(pd.DataFrame(rows, columns=cols),
                                     use_container_width=True)
                        if cur.rowcount == -1:
                            st.caption("Showing first 200 rows.")
                    else:               # UPDATE / INSERT / DELETE
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
