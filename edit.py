"""
Edit-Database page for the Streamlit app.

Two tabs:
    • 📝 Data Editor        – edit row values (original behaviour)
    • 🛠️ Table-definition   – run DDL / CREATE / ALTER statements

Usage from app.py
-----------------
    from edit import render_edit_page
    render_edit_page(get_connection, simple_rerun)

Parameters expected
-------------------
get_connection(db_name: str | None) → mysql.connector connection
simple_rerun()                      → calls st.rerun() after setting a flag
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")


def render_edit_page(get_connection, simple_rerun):
    """Main entry displayed by app.py."""
    st.title("Edit Database")

    # ── select database ────────────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases found.")
        return

    db = st.selectbox("Database", dbs)

    # ── tabs: Data vs SQL ──────────────────────────────────────────────────
    tab_data, tab_sql = st.tabs(["📝 Data Editor", "🛠️ Table-definition SQL"])

    # ======================================================================
    # TAB 1  –  DATA EDITOR
    # ======================================================================
    with tab_data:
        # fetch list of tables ------------------------------------------------
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
        else:
            tbl = st.selectbox("Table", tables, key="data_tbl")
            limit = st.number_input("Rows to load", 1, 200, 20, key="row_limit")

            # pull rows for editing
            conn = get_connection(db); cur = conn.cursor()
            cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close(); conn.close()

            if not rows:
                st.warning("Table is empty.")
            else:
                pk_guess = cols[0] if "id" in cols[0].lower() else cols[0]
                pk_col = st.selectbox(
                    "Primary-key column", cols, index=cols.index(pk_guess)
                )

                edited_df = st.data_editor(
                    pd.DataFrame(rows, columns=cols),
                    num_rows="dynamic",
                    use_container_width=True,
                    key="editor",
                )

                if st.button("Save Changes"):
                    changes = []
                    for i, row in edited_df.iterrows():
                        orig = rows[i]
                        for c in cols:
                            if row[c] != orig[cols.index(c)]:
                                changes.append((c, row[c], pk_col, row[pk_col]))

                    if not changes:
                        st.info("No changes detected.")
                    else:
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
                            st.error(f"Error saving: {e}")
                        finally:
                            cur.close(); conn.close()

    # ======================================================================
    # TAB 2  –  TABLE-DEFINITION / DDL SQL
    # ======================================================================
    with tab_sql:
        st.caption(
            "Run CREATE / ALTER statements to change table structures. "
            "Multiple statements are allowed; each **must** end with a semicolon."
        )

        # optional helper: show CREATE TABLE -------------------------------
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables_sql = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if tables_sql:
            helper_col1, helper_col2 = st.columns([2, 1])
            with helper_col1:
                showdef_tbl = st.selectbox(
                    "Show current definition for table (optional)",
                    ["<Choose table>"] + tables_sql,
                    key="ddl_tbl",
                )
            with helper_col2:
                if (
                    showdef_tbl
                    and showdef_tbl != "<Choose table>"
                    and st.button("Show CREATE TABLE", key="btn_show_create")
                ):
                    try:
                        conn = get_connection(db); cur = conn.cursor()
                        cur.execute(f"SHOW CREATE TABLE `{showdef_tbl}`")
                        create_sql = cur.fetchone()[1]
                        st.code(create_sql, language="sql")
                    except Exception as e:
                        st.error(e)
                    finally:
                        cur.close(); conn.close()

        # SQL input ---------------------------------------------------------
        ddl = st.text_area(
            "Table-definition SQL",
            "ALTER TABLE your_table\n  ADD COLUMN new_col INT;",
            height=200,
            key="ddl_sql",
        )

        if st.button("Apply DDL"):
            stmts = [s.strip() for s in re.split(r";\s*", ddl) if s.strip()]
            if not stmts:
                st.info("No SQL statements found.")
            else:
                try:
                    conn = get_connection(db); cur = conn.cursor()
                    for stmt in stmts:
                        cur.execute(stmt + ";")
                    conn.commit()
                    st.success(f"Executed {len(stmts)} statement(s) successfully.")
                    simple_rerun()
                except Exception as e:
                    st.error(f"Execution failed: {e}")
                finally:
                    cur.close(); conn.close()
