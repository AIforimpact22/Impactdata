from __future__ import annotations
"""
edit.py  –  Unified Data Editor: add, delete, and update rows from a single grid.
"""

import re
import streamlit as st
import pandas as pd

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

def render_edit_page(get_connection, simple_rerun):
    st.title("Edit Database")

    # ── Select database
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

    # =====================================================================
    # TAB 1 – DATA EDITOR (add/delete/update via one grid)
    # =====================================================================
    with tab_data:
        # Fetch tables
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
        cur.close(); conn.close()

        if not tables:
            st.info("No tables in this database.")
            return
        tbl = st.selectbox("Table", tables)

        # Fetch column metadata
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"DESCRIBE `{tbl}`")
        cols_meta = cur.fetchall()  # returns tuples: (Field, Type, Null, Key, Default, Extra)
        cur.close(); conn.close()

        headers = [col[0] for col in cols_meta]
        # Identify auto-increment columns
        auto_inc_cols = {
            field for (field, _type, _null, _key, _default, extra)
            in cols_meta if "auto_increment" in extra.lower()
        }

        # Load existing data
        limit = st.number_input("Rows to load", min_value=1, max_value=1000, value=20, key="load_limit")
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty.")
            return

        orig_df = pd.DataFrame(rows, columns=headers)

        st.markdown("### Edit, add or delete rows directly:")
        edited_df = st.experimental_data_editor(
            orig_df,
            num_rows="dynamic",
            use_container_width=True,
            row_deletable=True,
            key="editor",
        )

        if st.button("Save Changes", key="save_all"):
            # Determine primary key (first column with Key='PRI', else headers[0])
            pk_col = headers[0]
            for field, _type, _null, key, _default, extra in cols_meta:
                if key.upper() == "PRI":
                    pk_col = field
                    break

            orig_pks = set(orig_df[pk_col].tolist())
            edited_pks = set(edited_df[pk_col].dropna().tolist())

            # Deletions = orig PKs missing in edited
            to_delete = orig_pks - edited_pks

            # Inserts = rows where PK is null or not in orig_pks
            new_rows = edited_df[edited_df[pk_col].isna() | ~edited_df[pk_col].isin(orig_pks)]

            # Updates = existing rows where any non-PK, non-auto-inc cell changed
            updates = []
            for _, row in edited_df.iterrows():
                pk_val = row[pk_col]
                if pk_val in orig_pks:
                    orig_row = orig_df[orig_df[pk_col] == pk_val].iloc[0]
                    for col in headers:
                        if col == pk_col or col in auto_inc_cols:
                            continue
                        v_new = row[col]
                        v_old = orig_row[col]
                        if pd.isna(v_new) and pd.isna(v_old):
                            continue
                        if v_new != v_old:
                            updates.append((col, v_new, pk_col, pk_val))

            # Apply in DB
            try:
                conn = get_connection(db)
                cur = conn.cursor()
                # Deletions
                for pk in to_delete:
                    cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}`=%s", (pk,))
                # Inserts
                for _, nr in new_rows.iterrows():
                    cols = [c for c in headers if c not in auto_inc_cols]
                    vals = [nr[c] for c in cols]
                    cols_clause = ", ".join(f"`{c}`" for c in cols)
                    ph = ", ".join("%s" for _ in cols)
                    cur.execute(f"INSERT INTO `{tbl}` ({cols_clause}) VALUES ({ph})", vals)
                # Updates
                for col, v, pkc, pkv in updates:
                    cur.execute(f"UPDATE `{tbl}` SET `{col}`=%s WHERE `{pkc}`=%s", (v, pkv))
                conn.commit()

                msgs = []
                if to_delete:
                    msgs.append(f"{len(to_delete)} deletion(s)")
                if not new_rows.empty:
                    msgs.append(f"{len(new_rows)} insertion(s)")
                if updates:
                    msgs.append(f"{len(updates)} update(s)")
                st.success("✅ " + " and ".join(msgs) + " applied!")
                simple_rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
            finally:
                cur.close(); conn.close()

    # =====================================================================
    # TAB 2 – FREE SQL EDITOR
    # =====================================================================
    with tab_sql:
        st.subheader(f"Run custom SQL against `{db}`")
        default_sql = "-- Example:\nSELECT * FROM your_table LIMIT 10;\n\n-- UPDATE your_table SET col='x' WHERE id=1;"
        sql_code = st.text_area("SQL statements (semicolon-separated)", value=default_sql, height=200, key="sql_input")
        if st.button("Execute SQL", key="exec_sql"):
            stmts = [s.strip() for s in re.split(r";\s*", sql_code) if s.strip()]
            if not stmts:
                st.warning("Nothing to run.")
            else:
                try:
                    conn = get_connection(db)
                    cur = conn.cursor()
                    any_write = False
                    for i, stmt in enumerate(stmts, start=1):
                        st.markdown(f"##### Statement {i}")
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
