# add.py
"""
add.py  –  Insert new rows into any table.

Public API (used by app.py):
    render_add_page(get_connection, simple_rerun)

- get_connection(db_name:str|None)  → mysql.connector connection
- simple_rerun()                    → sets a flag then st.rerun()
"""

from __future__ import annotations
import streamlit as st

def render_add_page(get_connection, simple_rerun):
    st.title("Add Data to Table")

    # ── choose DATABASE first ───────────────────────────────────────────────
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [
            d[0] for d in cur.fetchall()
            if d[0] not in ("information_schema", "mysql", "performance_schema", "sys")
        ]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return
    db = st.selectbox("Database", dbs)

    # ── choose TABLE ─────────────────────────────────────────────────────────
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [t[0] for t in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not tables:
        st.info("No tables in this database."); return
    tbl = st.selectbox("Table", tables)

    # ── fetch COLUMN metadata ────────────────────────────────────────────────
    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(f"DESCRIBE `{tbl}`")
        cols = cur.fetchall()  # (Field, Type, Null, Key, Default, Extra)
    finally:
        cur.close(); conn.close()

    # ── build INPUT form ─────────────────────────────────────────────────────
    with st.form("insert_form"):
        inputs: dict[str, object] = {}
        for field, col_type, nullable, key, default, extra in cols:
            # skip auto-increment columns
            if "auto_increment" in extra.lower():
                continue

            label = f"{field} ({col_type})"
            if "int" in col_type:
                # use text_input for ints, then cast
                default_str = str(default) if default is not None else "0"
                val_str = st.text_input(label, value=default_str)
                try:
                    val_int = int(val_str)
                except ValueError:
                    st.error(f"Invalid integer for `{field}`; please enter a whole number.")
                    st.stop()
                inputs[field] = val_int
            else:
                inputs[field] = st.text_input(label, value=default or "")

        submit = st.form_submit_button("Insert Row")

    if not submit:
        return

    # ── perform INSERT ──────────────────────────────────────────────────────
    columns = ", ".join(f"`{col}`" for col in inputs.keys())
    placeholders = ", ".join("%s" for _ in inputs)
    values = list(inputs.values())

    try:
        conn = get_connection(db); cur = conn.cursor()
        cur.execute(
            f"INSERT INTO `{tbl}` ({columns}) VALUES ({placeholders})",
            values
        )
        conn.commit()
        st.success("✅ Row inserted successfully!")
        simple_rerun()
    except Exception as e:
        st.error(f"Insert failed: {e}")
    finally:
        cur.close(); conn.close()
