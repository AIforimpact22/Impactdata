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
    #  TAB 1 – Spreadsheet-style editor + add/delete                       #
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

        # Data editor for updates
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

        # ---------------------------------------------------------------- #
        #  Add new row                                                     #
        # ---------------------------------------------------------------- #
        st.markdown("---")
        with st.expander("Add New Row", expanded=False):
            # Fetch column metadata
            conn = get_connection(db); cur = conn.cursor()
            cur.execute(f"DESCRIBE `{tbl}`")
            meta = cur.fetchall()  # (Field, Type, Null, Key, Default, Extra)
            cur.close(); conn.close()

            with st.form("add_row_form"):
                new_vals = {}
                for field, col_type, nullable, key, default, extra in meta:
                    if "auto_increment" in extra.lower():
                        continue
                    label = f"{field} ({col_type})"
                    if "int" in col_type:
                        val = st.number_input(label, value=default or 0)
                    else:
                        val = st.text_input(label, value=default or "")
                    new_vals[field] = val
                add_submit = st.form_submit_button("Insert Row")

            if add_submit:
                cols_str = ", ".join(f"`{f}`" for f in new_vals.keys())
                ph = ", ".join("%s" for _ in new_vals)
                vals = list(new_vals.values())
                try:
                    conn = get_connection(db); cur = conn.cursor()
                    cur.execute(
                        f"INSERT INTO `{tbl}` ({cols_str}) VALUES ({ph})", vals
                    )
                    conn.commit()
                    st.success("New row added.")
                    simple_rerun()
                except Exception as e:
                    st.error(e)
                finally:
                    cur.close(); conn.close()

        # ---------------------------------------------------------------- #
        #  Delete rows                                                     #
        # ---------------------------------------------------------------- #
        st.markdown("---")
        with st.expander("Delete Rows", expanded=False):
            pks = [r[cols.index(pk_col)] for r in rows]
            to_delete = st.multiselect(
                f"Select `{pk_col}` values to delete", pks)
            if st.button("Delete Selected Rows"):
                if not to_delete:
                    st.info("No rows selected.")
                else:
                    try:
                        conn = get_connection(db); cur = conn.cursor()
                        for pk_val in to_delete:
                            cur.execute(
                                f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s", (pk_val,)
                            )
                        conn.commit()
                        st.success(f"Deleted {len(to_delete)} row(s).")
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

                    if cur.with_rows:
                        rows = cur.fetchmany(200)
                        cols2 = [d[0] for d in cur.description]
                        st.dataframe(pd.DataFrame(rows, columns=cols2),
                                     use_container_width=True)
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
