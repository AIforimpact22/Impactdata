# edit_db_page.py  ────────────────────────────────────────────────────────────
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple, Any

import numpy as np
import pandas as pd
import sqlparse          # pip install sqlparse
import streamlit as st    # pip install streamlit>=1.35

# ---------------------------------------------------------------------------#
# Configuration
# ---------------------------------------------------------------------------#
EXCLUDED_SYS_DBS = ("information_schema", "mysql",
                    "performance_schema", "sys")
MAX_PREVIEW_ROWS = 1_000          # hard-limit shown in the editor
SHOW_SQL_IN_SUCCESS_TOAST = True  # turn off if noise


# ---------------------------------------------------------------------------#
# Utility helpers
# ---------------------------------------------------------------------------#
def _py(val: Any) -> Any:
    """Convert DB/NumPy/pandas scalars to pure Python types (for MySQLdb)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, np.generic):
        return val.item()
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    return val


def _get_primary_keys(cur, table: str) -> Tuple[str, ...]:
    """Return tuple of primary-key column names for *table*."""
    cur.execute("SHOW KEYS FROM `{}` WHERE Key_name='PRIMARY'".format(table))
    return tuple(row[4] for row in cur.fetchall())  # column_name is index 4


def _upsert_row(cur, db: str, table: str,
                pk_cols: Sequence[str],
                old_row: Dict[str, Any] | None,
                new_row: Dict[str, Any]) -> None:
    """
    INSERT a new row or UPDATE an existing one.

    * If *old_row* is None → INSERT (ignore duplicates).
    * Else → UPDATE only the modified columns.
    """
    cols = list(new_row.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    set_clause = ", ".join("`{0}`=%s".format(c) for c in cols)

    if old_row is None:  # INSERT
        sql = "INSERT INTO `{0}`.`{1}` ({2}) VALUES ({3})".format(
            db, table, ", ".join(f"`{c}`" for c in cols), placeholders
        )
        cur.execute(sql, tuple(_py(new_row[c]) for c in cols))
    else:                # UPDATE
        diff_cols = [c for c in cols if old_row.get(c) != new_row.get(c)]
        if not diff_cols:
            return  # nothing changed
        set_clause = ", ".join("`{0}`=%s".format(c) for c in diff_cols)
        where_clause = " AND ".join("`{0}`=%s".format(c) for c in pk_cols)
        sql = ("UPDATE `{0}`.`{1}` SET {2} WHERE {3}"
               .format(db, table, set_clause, where_clause))
        cur.execute(
            sql,
            tuple(_py(new_row[c]) for c in diff_cols) +
            tuple(_py(old_row[c]) for c in pk_cols)
        )


def _detect_changes(orig_df: pd.DataFrame,
                    edited_df: pd.DataFrame,
                    pk_cols: Sequence[str]) -> Tuple[
                        List[Tuple[Dict[str, Any] | None, Dict[str, Any]]],
                        List[Dict[str, Any]]
                    ]:
    """
    Compare *orig_df* vs *edited_df*.

    Returns (rows_to_upsert, errors) where:

    * rows_to_upsert = list of (old_row_dict | None, new_row_dict)
      – old_row_dict is None for new INSERTs.
    * errors = list of human-readable problems (duplicate PK etc.)
    """
    rows: Dict[Tuple[Any, ...], Dict[str, Any]] = {
        tuple(orig_df.loc[i, pk_cols]): orig_df.loc[i].to_dict()
        for i in orig_df.index
    }
    to_upsert: List[Tuple[Dict[str, Any] | None, Dict[str, Any]]] = []
    errors: List[Dict[str, Any]] = []

    for _, row in edited_df.iterrows():
        pk_vals = tuple(row[c] for c in pk_cols)
        new_row = row.to_dict()
        if any(pd.isna(v) for v in pk_vals):
            errors.append(
                {"row": new_row, "err": "Primary-key value missing (NULL)"}
            )
            continue
        old_row = rows.get(pk_vals)
        to_upsert.append((old_row, new_row))
    return to_upsert, errors


# ---------------------------------------------------------------------------#
# Main Streamlit page
# ---------------------------------------------------------------------------#
def render_edit_page(get_connection, simple_rerun):
    st.title("📝 Edit Database")

    # ------------------------------------------------------------------#
    # Database picker
    # ------------------------------------------------------------------#
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    cur.close()
    conn.close()

    if not dbs:
        st.info("No user-created databases found.")
        return

    db = st.selectbox("Database", dbs)
    tab_sheet, tab_sql, tab_new = st.tabs(
        ["Spreadsheet Editor", "SQL Editor", "New Table"]
    )

    # ================================================================
    # TAB 1  Spreadsheet Editor
    # ================================================================
    with tab_sheet:
        st.subheader(f"Spreadsheet view – `{db}`")

        # -------- table picker --------
        conn = get_connection(db)
        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
        cur.close()
        conn.close()

        if not tables:
            st.info(f"No tables in **{db}** yet. Create one ➜ _New Table_ tab.")
            st.stop()

        table = st.selectbox("Table", tables, key="tbl_picker")

        # -------- load data --------
        @st.cache_data(show_spinner=False)
        def _load_table(db: str, table: str) -> pd.DataFrame:
            conn = get_connection(db)
            df = pd.read_sql(
                f"SELECT * FROM `{table}` LIMIT {MAX_PREVIEW_ROWS}", conn
            )
            conn.close()
            return df

        df_orig = _load_table(db, table)

        if df_orig.empty:
            st.warning("Table is empty – add rows below ⬇")
        else:
            st.caption(f"Showing ≤ {MAX_PREVIEW_ROWS} rows")

        # -------- editable dataframe --------
        df_edit = st.data_editor(
            df_orig,
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_{db}_{table}",
        )

        # -------- save button --------
        if st.button("💾 Save changes to database", help="Insert / update"):
            with st.spinner("Writing changes…"):
                conn = get_connection(db)
                cur = conn.cursor()

                pk_cols = _get_primary_keys(cur, table)
                if not pk_cols:
                    st.error(
                        f"Table **{table}** has no PRIMARY KEY → cannot "
                        "reliably update rows."
                    )
                    cur.close()
                    conn.close()
                    st.stop()

                rows_to_upsert, errs = _detect_changes(
                    df_orig, df_edit, pk_cols
                )
                if errs:
                    st.error(
                        f"❌ {len(errs)} row(s) skipped because of errors; "
                        "see details below."
                    )
                    st.json(errs, expanded=False)

                wrote = 0
                for old_row, new_row in rows_to_upsert:
                    try:
                        _upsert_row(cur, db, table, pk_cols,
                                    old_row, new_row)
                        wrote += 1
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Write error: {exc}")

                conn.commit()
                cur.close()
                conn.close()

                if wrote:
                    toast_msg = f"✅ {wrote} row(s) written."
                    if SHOW_SQL_IN_SUCCESS_TOAST:
                        st.success(toast_msg, icon="💾")
                    else:
                        st.toast(toast_msg)
                simple_rerun()

    # ================================================================
    # TAB 2  SQL Editor
    # ================================================================
    with tab_sql:
        st.subheader(f"Run SQL against `{db}`")

        default_sql = "-- Type SQL here (multiple statements OK)\nSELECT NOW();"
        sql_text = st.text_area(
            "SQL input",
            value=st.session_state.get("sql_buf", default_sql),
            height=260,
            key="sql_textarea",
        )

        if st.button("▶ Run", key="run_sql_btn"):
            st.session_state["sql_buf"] = sql_text
            statements = [
                s.strip() for s in sqlparse.split(sql_text) if s.strip()
            ]
            if not statements:
                st.warning("Nothing to execute.")
                st.stop()

            conn = get_connection(db)
            cur = conn.cursor()

            for i, stmt in enumerate(statements, 1):
                st.markdown(f"##### Statement {i}")
                try:
                    cur.execute(stmt)
                    if cur.description:  # SELECT etc.
                        cols = [d[0] for d in cur.description]
                        rows = cur.fetchall()
                        df = pd.DataFrame(rows, columns=cols)
                        st.dataframe(df, use_container_width=True)
                        st.caption(f"{len(df):,} row(s) returned")
                    else:
                        conn.commit()
                        st.success(f"{cur.rowcount:,} row(s) affected")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Execution error: {exc}")
                    conn.rollback()
                    break  # stop at first failure

            cur.close()
            conn.close()

    # ================================================================
    # TAB 3  Create New Table
    # ================================================================
    with tab_new:
        st.subheader(f"Create a new table in `{db}`")

        create_tpl = (
            "-- Write a full CREATE TABLE statement.\n"
            "CREATE TABLE example_table (\n"
            "  id INT AUTO_INCREMENT PRIMARY KEY,\n"
            "  name VARCHAR(100),\n"
            "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
            ") ENGINE=InnoDB "
            "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        )

        create_sql = st.text_area(
            "CREATE TABLE statement",
            value=st.session_state.get("create_sql", create_tpl),
            height=300,
            key="create_sql_area",
        )

        if st.button("🚀 Execute CREATE TABLE", key="exec_create"):
            st.session_state["create_sql"] = create_sql
            try:
                conn = get_connection(db)
                cur = conn.cursor()
                cur.execute(create_sql)
                conn.commit()
                st.success("Table created successfully!")
                simple_rerun()
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                st.error(f"Creation failed: {exc}")
            finally:
                cur.close()
                conn.close()
