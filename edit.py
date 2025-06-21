from __future__ import annotations
"""
edit.py  –  Table spreadsheet editor + free-form SQL editor with add/delete functionality.
"""
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")


def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # Select database
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases found.")
        return
    db = st.selectbox("Database", dbs)

    tab_data, tab_sql = st.tabs(["📝 Data Editor", "🛠️ SQL Editor"])

    # ----------------------
    # TAB: Data Editor
    # ----------------------
    with tab_data:
        # Select table
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
        cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
            return
        tbl = st.selectbox("Table", tables)

        # Fetch columns
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"DESCRIBE `{tbl}`")
        cols_meta = cur.fetchall()  # (Field, Type, Null, Key, Default, Extra)
        cur.close(); conn.close()
        col_names = [c[0] for c in cols_meta]

        # --- Add new row form ---
        with st.form("add_row_form"):
            st.markdown("### ➕ Add New Row")
            new_vals: dict[str, object] = {}
            for field, col_type, *_ in cols_meta:
                if "auto_increment" in col_type.lower():
                    continue
                label = f"{field} ({col_type})"
                if "int" in col_type:
                    new_vals[field] = st.number_input(label, value=0, step=1, key=f"add_{field}")
                else:
                    new_vals[field] = st.text_input(label, value="", key=f"add_{field}")
            add_sub = st.form_submit_button("Insert Row")
        if add_sub:
            cols_str = ", ".join(f"`{f}`" for f in new_vals)
            placeholders = ", ".join("%s" for _ in new_vals)
            try:
                conn = get_connection(db)
                cur = conn.cursor()
                cur.execute(
                    f"INSERT INTO `{tbl}` ({cols_str}) VALUES ({placeholders})",
                    list(new_vals.values()),
                )
                conn.commit()
                st.success("Inserted new row.")
                simple_rerun()
            except Exception as e:
                st.error(f"Insert failed: {e}")
            finally:
                cur.close(); conn.close()

        # --- Load existing data ---
        limit = st.number_input("Rows to load", min_value=1, max_value=1000, value=20, key="load_limit")
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        rows = cur.fetchall()
        headers = [d[0] for d in cur.description]
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty.")
            return
        df = pd.DataFrame(rows, columns=headers)

        # --- Delete rows form ---
        with st.form("delete_rows_form"):
            st.markdown("### 🗑️ Delete Rows")
            pk_guess = headers[0]
            pk_col = st.selectbox("Primary key column", headers, index=0, key="del_pk_col")
            to_del = st.multiselect("Select PK(s) to delete", df[pk_col].tolist(), key="del_select")
            del_sub = st.form_submit_button("Delete Selected Rows")
        if del_sub:
            if to_del:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    for pk in to_del:
                        cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s", (pk,))
                    conn.commit()
                    st.success(f"Deleted {len(to_del)} row(s).")
                    simple_rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
                finally:
                    cur.close(); conn.close()
            else:
                st.info("No rows selected to delete.")

        # --- In-place edits ---
        st.markdown("### ✏️ Edit Rows")
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor",
        )
        if st.button("Save Changes", key="save_edit_btn"):
            # detect changes
            changes: list[tuple[str, object, str, object]] = []
            for i, row in edited.iterrows():
                orig = rows[i]
                for col in headers:
                    if row[col] != orig[headers.index(col)]:
                        changes.append((col, row[col], headers[0], row[headers[0]]))
            if not changes:
                st.info("No changes detected.")
            else:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    for col, new_val, pk, pk_val in changes:
                        cur.execute(
                            f"UPDATE `{tbl}` SET `{col}`=%s WHERE `{pk}`=%s",
                            (new_val, pk_val),
                        )
                    conn.commit()
                    st.success(f"Applied {len(changes)} update(s).")
                    simple_rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")
                finally:
                    cur.close(); conn.close()

    # ----------------------
    # TAB: SQL Editor
    # ----------------------
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")
        default = "-- Enter SQL statements; separate with semicolons"
        sql = st.text_area("SQL", value=default, height=200, key="sql_text")
        if st.button("Execute SQL", key="exec_sql_btn"):
            stmts = [s.strip() for s in re.split(r";\s*", sql) if s.strip()]
            if not stmts:
                st.warning("Nothing to run.")
            else:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    any_write = False
                    for idx, stmt in enumerate(stmts, start=1):
                        st.markdown(f"#### Statement {idx}")
                        cur.execute(stmt)
                        if cur.with_rows:
                            res = cur.fetchmany(200)
                            cols = [d[0] for d in cur.description]
                            st.dataframe(pd.DataFrame(res, columns=cols), use_container_width=True)
                        else:
                            any_write = True
                            st.success(f"{cur.rowcount} row(s) affected.")
                    if any_write:
                        conn.commit()
                        st.success("Changes committed.")
                        simple_rerun()
                except Exception as e:
                    st.error(f"SQL execution failed: {e}")
                finally:
                    cur.close(); conn.close()
