from __future__ import annotations
"""
edit.py  –  Unified Data Editor: add, delete, and update rows from a single grid.
"""
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
    # TAB 1  –  DATA EDITOR (add, delete, update via single grid)
    # ======================================================================
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
        cols_meta = cur.fetchall()  # (Field, Type, Null, Key, Default, Extra)
        cur.close(); conn.close()
        headers = [c[0] for c in cols_meta]

        # Identify auto-increment columns correctly
        auto_inc_cols = {field for field, *_, extra in cols_meta if 'auto_increment' in extra.lower()}

        # Load existing data
        limit = st.number_input(
            "Rows to load", min_value=1, max_value=1000, value=50, key="load_limit"
        )
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM `{tbl}` LIMIT {limit}")
        rows = cur.fetchall()
        cur.close(); conn.close()

        if not rows:
            st.warning("Table is empty.")
            return

        orig_df = pd.DataFrame(rows, columns=headers)

        st.markdown("### Edit, add, or delete rows directly below:")
                edited_df = st.experimental_data_editor(
            orig_df,
            num_rows="dynamic",
            use_container_width=True,
            row_deletable=True,
            key="data_editor",
        )
        )

        if st.button("Save Changes", key="btn_save_all"):
            # Determine primary key column (first field in header list)
            pk_col = headers[0]

            # Detect deletions
            orig_pks = set(orig_df[pk_col].tolist())
            edited_pks = set(edited_df[pk_col].dropna().tolist())
            deleted_pks = orig_pks - edited_pks

            # Detect new inserts (rows with NaN or PK not in original)
            new_rows_df = edited_df[edited_df[pk_col].isna() | ~edited_df[pk_col].isin(orig_pks)]

            # Detect updates
            updates = []
            for _, row in edited_df.iterrows():
                pk_val = row[pk_col]
                if pk_val in orig_pks:
                    orig_row = orig_df[orig_df[pk_col] == pk_val].iloc[0]
                    for col in headers:
                        if col == pk_col or col in auto_inc_cols:
                            continue
                        if pd.isna(row[col]) and pd.isna(orig_row[col]):
                            continue
                        if row[col] != orig_row[col]:
                            updates.append((col, row[col], pk_col, pk_val))

            # Apply changes
            try:
                conn = get_connection(db)
                cur = conn.cursor()
                # Delete
                for pk in deleted_pks:
                    cur.execute(f"DELETE FROM `{tbl}` WHERE `{pk_col}` = %s", (pk,))
                # Insert
                for _, new_row in new_rows_df.iterrows():
                    insert_cols = [c for c in headers if c not in auto_inc_cols]
                    vals = [new_row[c] for c in insert_cols]
                    cols_clause = ", ".join(f"`{c}`" for c in insert_cols)
                    placeholders = ", ".join("%s" for _ in insert_cols)
                    cur.execute(
                        f"INSERT INTO `{tbl}` ({cols_clause}) VALUES ({placeholders})",
                        vals,
                    )
                # Update
                for col, new_val, pk, pk_val in updates:
                    cur.execute(
                        f"UPDATE `{tbl}` SET `{col}` = %s WHERE `{pk}` = %s",
                        (new_val, pk_val),
                    )
                conn.commit()
                parts = []
                if deleted_pks:
                    parts.append(f"{len(deleted_pks)} deletion(s)")
                if len(new_rows_df) > 0:
                    parts.append(f"{len(new_rows_df)} insertion(s)")
                if updates:
                    parts.append(f"{len(updates)} update(s)")
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
