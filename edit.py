"""
edit.py – Spreadsheet-style editor + free-form SQL editor.

Imported by app.py:
    from edit import render_edit_page
"""
from __future__ import annotations
import re
import streamlit as st
import pandas as pd
import numpy as np

EXCLUDED_SYS_DBS = (
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
)

# ─────────────────────────────────────────────────────────────────────────────
# Utility: convert numpy / pandas scalars to plain-Python objects
# ─────────────────────────────────────────────────────────────────────────────
def _py(val):
    """Return a DB-safe pure-Python value (no numpy scalars)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, np.generic):
        return val.item()
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────
def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # --------------------------------------------------------------------- #
    # 1 – Pick database
    # --------------------------------------------------------------------- #
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases.")
        return

    db = st.selectbox("Database", dbs)
    tab_sheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # =====================================================================
    # TAB 1 – Spreadsheet Editor
    # =====================================================================
    with tab_sheet:
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this DB.")
            return

        tbl   = st.selectbox("Table", tables)
        limit = st.number_input("Rows to load", 1, 500, 20)

        # ----- Pull rows & column metadata --------------------------------
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()

        # Detect generated columns
        cur.execute(f"SHOW COLUMNS FROM `{tbl}`")
        desc = cur.fetchall()   # Field, Type, Null, Key, Default, Extra
        generated_cols = {
            field for field, *_ , extra in desc
            if "GENERATED" in extra.upper()
        }
        cur.close(); conn.close()

        # Detect PK column
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute(f"SHOW KEYS FROM `{tbl}` WHERE Key_name='PRIMARY'")
            pk_info = cur.fetchone()
        finally:
            cur.close(); conn.close()

        pk_col_auto = pk_info[4] if pk_info else cols[0]   # Column_name
        pk_col = st.selectbox(
            "Primary-key column",
            cols,
            index=cols.index(pk_col_auto),
        )

        # DataFrames
        orig_df = pd.DataFrame(rows, columns=cols)
        edited_df = st.data_editor(
            orig_df,
            num_rows="dynamic",
            use_container_width=True,
            key="sheet_editor",
        ).where(pd.notnull, None)   # convert pd.NA → None

        # ------------------------------------------------------------------
        # SAVE
        # ------------------------------------------------------------------
        if st.button("Save Changes", key="save_btn"):
            try:
                conn = get_connection(db); cur = conn.cursor()

                orig_pk_set = set(orig_df[pk_col].dropna())

                # ---------- DELETES ---------------------------------------
                edited_pk_set = set(edited_df[pk_col].dropna())
                del_pks = orig_pk_set - edited_pk_set
                del_cnt = 0
                for pk_val in del_pks:
                    cur.execute(
                        f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s",
                        (_py(pk_val),),
                    )
                    del_cnt += cur.rowcount

                # ---------- UPDATES ---------------------------------------
                upd_cnt = 0
                for pk_val in edited_pk_set & orig_pk_set:
                    row_old = orig_df.loc[orig_df[pk_col] == pk_val].iloc[0]
                    row_new = edited_df.loc[edited_df[pk_col] == pk_val].iloc[0]

                    for c in cols:
                        if c in generated_cols:
                            continue
                        if row_new[c] != row_old[c]:
                            cur.execute(
                                f"UPDATE `{tbl}` SET `{c}`=%s "
                                f"WHERE `{pk_col}`=%s",
                                (_py(row_new[c]), _py(pk_val)),
                            )
                            upd_cnt += cur.rowcount

                # ---------- INSERTS ---------------------------------------
                ins_cnt = 0
                insert_cols = [c for c in cols if c not in generated_cols]
                placeholders = ", ".join("%s" for _ in insert_cols)
                col_list     = ", ".join(f"`{c}`" for c in insert_cols)

                for _, row in edited_df.iterrows():
                    pk_val = row[pk_col]
                    is_new = pk_val in (None, "", 0) or pk_val not in orig_pk_set
                    if not is_new:
                        continue

                    # Skip completely blank rows
                    if all(
                        (pd.isna(row[c]) or row[c] == "")
                        for c in insert_cols
                    ):
                        continue

                    cur.execute(
                        f"INSERT INTO `{tbl}` ({col_list}) VALUES ({placeholders})",
                        tuple(_py(row[c]) for c in insert_cols),
                    )
                    ins_cnt += cur.rowcount

                # ---------- COMMIT & FEEDBACK -----------------------------
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

    # =====================================================================
    # TAB 2 – Free SQL / DDL Editor
    # =====================================================================
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")

        default_sql = (
            "-- Example:\n"
            "SELECT * FROM your_table LIMIT 10;\n\n"
            "-- CREATE TRIGGER ... BEGIN ... END;"
        )
        sql_code = st.text_area(
            "SQL statements (semicolon-separated)",
            value=default_sql,
            height=220,
        )

        if st.button("Execute", key="exec_sql"):
            # Strip client-side DELIMITER commands if present
            cleaned_sql = "\n".join(
                line for line in sql_code.splitlines()
                if not line.strip().upper().startswith("DELIMITER")
            )

            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False

                for idx, result in enumerate(
                        cur.execute(cleaned_sql, multi=True), start=1):
                    if result.with_rows:  # SELECT
                        st.markdown(f"##### Result set {idx}")
                        st.dataframe(
                            pd.DataFrame(
                                result.fetchall(),
                                columns=[d[0] for d in result.description],
                            ),
                            use_container_width=True,
                        )
                    else:                # UPDATE / INSERT / DDL
                        any_write = True
                        st.success(
                            f"Statement {idx}: {result.rowcount} row(s) affected."
                        )

                if any_write:
                    conn.commit()
                    st.success("Changes committed.")
                    simple_rerun()

            except Exception as e:
                conn.rollback()
                st.error(f"Execution failed: {e}")
            finally:
                cur.close(); conn.close()
