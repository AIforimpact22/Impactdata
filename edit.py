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

# --------------------------------------------------------------------------- #
#  Main entry point                                                           #
# --------------------------------------------------------------------------- #
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

    # ── two editing modes (tabs) ────────────────────────────────────────────
    tab_spreadsheet, tab_sql = st.tabs(["Spreadsheet Editor", "SQL Editor"])

    # --------------------------------------------------------------------- #
    #  TAB 1 – Spreadsheet-style editor (existing behaviour)                #
    # --------------------------------------------------------------------- #
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

        if st.button("Save Changes", key="save_changes_btn"):
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

    # --------------------------------------------------------------------- #
    #  TAB 2 – Free SQL editor                                              #
    # --------------------------------------------------------------------- #
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")

        default_sql = "-- Example:\n" \
                      "SELECT * FROM your_table LIMIT 10;\n\n" \
                      "-- UPDATE your_table SET col = 'value' WHERE id = 1;"
        sql_code = st.text_area("SQL statements (one or more, separated by semicolons)",
                                value=default_sql, height=200)

        execute_btn = st.button("Execute", key="execute_sql_btn")

        if execute_btn:
            statements = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not statements:
                st.warning("Nothing to run."); return

            try:
                conn = get_connection(db); cur = conn.cursor()
                any_write = False

                for idx, stmt in enumerate(statements, start=1):
                    st.markdown(f"##### Statement {idx}")
                    cur.execute(stmt)

                    if cur.with_rows:      # SELECT (or similar returning rows)
                        rows = cur.fetchmany(200)
                        cols = [d[0] for d in cur.description]
                        st.dataframe(pd.DataFrame(rows, columns=cols),
                                     use_container_width=True)
                        if cur.rowcount == -1:
                            st.caption("Showing first 200 rows.")
                    else:                  # UPDATE / INSERT / DELETE, etc.
                        any_write = True
                        st.success(f"{cur.rowcount} row(s) affected.")

                if any_write:
                    conn.commit()
                    st.success("Changes committed.")

            except Exception as e:
                st.error(f"Error: {e}")
            finally:
                cur.close(); conn.close()
