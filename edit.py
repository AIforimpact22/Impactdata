from __future__ import annotations
import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

# --------------------------------------------------------------------------- #
#  Main entry point                                                           #
# --------------------------------------------------------------------------- #
def render_edit_page(get_connection, simple_rerun):
    """Main entry displayed by app.py."""
    st.title("Edit Database")

    # ── Select database ───────────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases found.")
        return

    db = st.selectbox("Database", dbs)

    # ── Tabs: Data Editor vs SQL Editor ───────────────────────────────────────
    tab_data, tab_sql = st.tabs(["📝 Data Editor", "🛠️ SQL Editor"])

    # ======================================================================
    # TAB 1  –  DATA EDITOR
    # ======================================================================
    with tab_data:
        # ── Fetch available tables ──────────────────────────────────────────
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
        cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
            return

        tbl = st.selectbox("Table", tables)

        # ── Fetch column metadata ───────────────────────────────────────────
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"DESCRIBE `{tbl}`")
        cols_meta = cur.fetchall()  # (Field, Type, Null, Key, Default, Extra)
        cur.close(); conn.close()

        col_headers = [c[0] for c in cols_meta]

        # ── Add new row expander ───────────────────────────────────────────
        with st.expander("➕ Add new row"):
            new_row: dict[str, object] = {}
            for field, col_type, nullable, key, default, extra in cols_meta:
                if "auto_increment" in extra.lower():
                    continue
                label = f"{field} ({col_type})"
                if "int" in col_type:
                    new_row[field] = st.number_input(label, value=0, step=1, key=f"add_{field}")
                else:
                    new_row[field] = st.text_input(label, value="", key=f"add_{field}")
            if st.button("Insert new row", key="btn_insert_row"):
                cols_str = ", ".join(f"`{f}`" for f in new_row.keys())
                vals = list(new_row.values())
                placeholders = ", ".join("%s" for _ in vals)
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    cur.execute(
                        f"INSERT INTO `{tbl}` ({cols_str}) VALUES ({placeholders})",
                        vals,
                    )
                    conn.commit()
                    st.success("✅ Row inserted successfully!")
                    simple_rerun()
                except Exception as e:
                    st.error(f"Insert failed: {e}")
                finally:
                    cur.close(); conn.close()

        # ── Load existing rows ──────────────────────────────────────────────
        limit = st.number_input("Rows to load", min_value=1, max_value=1000, value=20, key="edit_limit")
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty.")
            return

        df = pd.DataFrame(rows, columns=col_headers)

        # ── Delete selected rows via multiselect ───────────────────────────
        pk_guess = col_headers[0]
        pk_col = st.selectbox("Primary key column", col_headers, index=col_headers.index(pk_guess), key="pk_col")
        to_delete = st.multiselect("Select rows to delete", df[pk_col].tolist(), key="to_delete")
        if to_delete and st.button("Delete selected rows", key="btn_delete_rows"):
            try:
                conn = get_connection(db)
                cur = conn.cursor()
                for pk in to_delete:
                    cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s", (pk,))
                conn.commit()
                st.success(f"✅ Deleted {len(to_delete)} row(s)")
                simple_rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")
            finally:
                cur.close(); conn.close()

        # ── Edit existing data & handle updates/deletions ────────────────
        edited = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor",
        )

        if st.button("Save changes", key="btn_save_changes"):
            # Detect deletions
            orig_pks = [orig[col_headers.index(pk_col)] for orig in rows]
            edited_pks = edited[pk_col].tolist()
            deleted_pks = [pk for pk in orig_pks if pk not in edited_pks]
            # Detect updates
            changes: list[tuple[str, object, str, object]] = []
            for i, row in edited.iterrows():
                orig = rows[i]
                for col in col_headers:
                    if row[col] != orig[col_headers.index(col)]:
                        changes.append((col, row[col], pk_col, row[pk_col]))
            if not deleted_pks and not changes:
                st.info("No changes detected.")
            else:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    # Apply deletions
                    for pk in deleted_pks:
                        cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s", (pk,))
                    # Apply updates
                    for col, new_val, pk, pk_val in changes:
                        cur.execute(
                            f"UPDATE `{tbl}` SET `{col}` = %s WHERE `{pk}` = %s",
                            (new_val, pk_val),
                        )
                    conn.commit()
                    parts = []
                    if deleted_pks:
                        parts.append(f"{len(deleted_pks)} deletion(s)")
                    if changes:
                        parts.append(f"{len(changes)} update(s)")
                    st.success("✅ " + " and ".join(parts) + " applied!")
                    simple_rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")
                finally:
                    cur.close(); conn.close()

    # ======================================================================
    # TAB 2  –  FREE SQL EDITOR
    # ======================================================================
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")
        default_sql = (
            "-- Example:\n"
            "SELECT * FROM your_table LIMIT 10;\n\n"
            "-- UPDATE your_table SET col = 'value' WHERE id = 1;"
        )
        sql_code = st.text_area(
            "SQL statements (separated by semicolons)",
            value=default_sql,
            height=200,
            key="sql_input",
        )
        if st.button("Execute SQL", key="btn_execute_sql"):
            stmts = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not stmts:
                st.warning("Nothing to run.")
            else:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    any_write = False
                    for idx, stmt in enumerate(stmts, start=1):
                        st.markdown(f"##### Statement {idx}")
                        cur.execute(stmt)
                        if cur.with_rows:
                            res = cur.fetchmany(200)
                            cols = [d[0] for d in cur.description]
                            st.dataframe(pd.DataFrame(res, columns=cols), use_container_width=True)
                            if cur.rowcount == -1:
                                st.caption("Showing first 200 rows.")
                        else:
                            any_write = True
                            st.success(f"{cur.rowcount} row(s) affected.")
                    if any_write:
                        conn.commit()
                        st.success("✅ Changes committed.")
                        simple_rerun()
                except Exception as e:
                    st.error(f"Execution error: {e}")
                finally:
                    cur.close(); conn.close()
