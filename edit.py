from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")


def render_edit_page(get_connection, simple_rerun):
    """Main entry displayed by app.py."""
    st.title("Edit Database")

    # ── Select database ─────────────────────────────────────────────────────
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

    # ── Tabs: Data Editor vs Table-definition SQL ────────────────────────────
    tab_data, tab_sql = st.tabs(["📝 Data Editor", "🛠️ Table-definition SQL"])

    # ======================================================================
    # TAB 1 – DATA EDITOR
    # ======================================================================
    with tab_data:
        # Fetch tables
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
            return

        tbl = st.selectbox("Table", tables)
        limit = st.number_input("Rows to load", 1, 200, 20, key="row_limit")

        # Load rows
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close(); conn.close()

        df = pd.DataFrame(rows, columns=cols)
        if df.empty:
            st.warning("Table is empty.")
        else:
            # Guess primary key column
            pk_guess = next((c for c in cols if "id" in c.lower()), cols[0])
            pk_col = st.selectbox("Primary-key column", cols, index=cols.index(pk_guess))

            # Editable DataFrame with dynamic rows
            edited_df = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key="data_editor",
            )

            # Action buttons
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save Changes", key="save_changes_btn"):
                    changes = []
                    for i, row in edited_df.iterrows():
                        orig = df.iloc[i]
                        for c in cols:
                            if row[c] != orig[c]:
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

            with col2:
                delete_keys = st.multiselect(
                    "Select rows to delete", df[pk_col].tolist(), key="delete_rows"
                )
                if delete_keys and st.button("Delete Selected Rows", key="delete_btn"):
                    try:
                        conn = get_connection(db); cur = conn.cursor()
                        for pk_val in delete_keys:
                            cur.execute(
                                f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s", (pk_val,)
                            )
                        conn.commit()
                        st.success(f"Deleted {len(delete_keys)} row(s).")
                        simple_rerun()
                    except Exception as e:
                        st.error(f"Error deleting rows: {e}")
                    finally:
                        cur.close(); conn.close()

        st.markdown("---")
        # Add new row section
        with st.expander("Add new row"):
            try:
                conn = get_connection(db); cur = conn.cursor()
                cur.execute(f"DESCRIBE `{tbl}`")
                cols_meta = cur.fetchall()
            finally:
                cur.close(); conn.close()

            with st.form("add_row_form"):
                inputs: dict[str, object] = {}
                for field, col_type, nullable, key, default, extra in cols_meta:
                    if "auto_increment" in extra.lower():
                        continue
                    label = f"{field} ({col_type})"
                    if "int" in col_type:
                        inputs[field] = st.number_input(
                            label, value=int(default) if default is not None else 0, step=1, key=f"add_{field}"
                        )
                    else:
                        inputs[field] = st.text_input(
                            label, value=default or "", key=f"add_{field}"
                        )
                if st.form_submit_button("Insert Row"):
                    columns_str = ", ".join(f"`{f}`" for f in inputs.keys())
                    placeholders = ", ".join("%s" for _ in inputs)
                    values = list(inputs.values())
                    try:
                        conn = get_connection(db); cur = conn.cursor()
                        cur.execute(
                            f"INSERT INTO `{tbl}` ({columns_str}) VALUES ({placeholders})",
                            values,
                        )
                        conn.commit()
                        st.success("Row inserted successfully.")
                        simple_rerun()
                    except Exception as e:
                        st.error(f"Insert failed: {e}")
                    finally:
                        cur.close(); conn.close()

    # ======================================================================
    # TAB 2 – TABLE-DEFINITION / DDL SQL + Free SQL Editor
    # ======================================================================
    with tab_sql:
        st.caption(
            "Run CREATE / ALTER statements to change table structures. "
            "Multiple statements are allowed; each **must** end with a semicolon."
        )
        # Helper: show CREATE TABLE
        try:
            conn = get_connection(db); cur = conn.cursor()
            cur.execute("SHOW TABLES")
            tables_sql = [t[0] for t in cur.fetchall()]
        finally:
            cur.close(); conn.close()
        helper_col1, helper_col2 = st.columns([2, 1])
        with helper_col1:
            showdef_tbl = st.selectbox(
                "Show current definition for table (optional)",
                ["<Choose table>"] + tables_sql,
                key="ddl_tbl",
            )
        with helper_col2:
            if showdef_tbl != "<Choose table>" and st.button("Show CREATE TABLE", key="btn_show_create"):
                try:
                    conn = get_connection(db); cur = conn.cursor()
                    cur.execute(f"SHOW CREATE TABLE `{showdef_tbl}`")
                    create_sql = cur.fetchone()[1]
                    st.code(create_sql, language="sql")
                except Exception as e:
                    st.error(e)
                finally:
                    cur.close(); conn.close()

        # DDL input
        ddl = st.text_area(
            "Table-definition SQL",
            "ALTER TABLE your_table\n  ADD COLUMN new_col INT;",
            height=200,
            key="ddl_sql",
        )
        if st.button("Apply DDL", key="apply_ddl"):
            stmts = [s.strip() for s in re.split(r";\s*", ddl) if s.strip()]
            if not stmts:
                st.info("No SQL statements found.")
            else:
                try:
                    conn = get_connection(db); cur = conn.cursor()
                    for stmt in stmts:
                        cur.execute(stmt + ";")
                    conn.commit()
                    st.success(f"Applied {len(stmts)} DDL statement(s).")
                    simple_rerun()
                except Exception as e:
                    st.error(f"DDL execution failed: {e}")
                finally:
                    cur.close(); conn.close()

        st.markdown("---")
        # Free SQL editor
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
            key="custom_sql",
        )
        if st.button("Execute SQL", key="exec_sql"):
            statements = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not statements:
                st.warning("Nothing to run.")
            else:
                any_write = False
                try:
                    conn = get_connection(db); cur = conn.cursor()
                    for idx, stmt in enumerate(statements, start=1):
                        st.markdown(f"##### Statement {idx}")
                        cur.execute(stmt)
                        if cur.with_rows:
                            rows_out = cur.fetchmany(200)
                            cols_out = [d[0] for d in cur.description]
                            st.dataframe(pd.DataFrame(rows_out, columns=cols_out), use_container_width=True)
                            if cur.rowcount == -1:
                                st.caption("Showing first 200 rows.")
                        else:
                            any_write = True
                            st.success(f"{cur.rowcount} row(s) affected.")
                    if any_write:
                        conn.commit()
                        st.success(f"Executed {len(statements)} statement(s).")
                        simple_rerun()
                except Exception as e:
                    st.error(f"Execution failed: {e}")
                finally:
                    cur.close(); conn.close()
