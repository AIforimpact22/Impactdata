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
        dbs = [d[0] for d in cur.fetchall()
               if d[0] not in ("information_schema", "mysql",
                               "performance_schema", "sys")]
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
        cols = cur.fetchall()  # list of (Field, Type, Null, Key, Default, Extra)
    finally:
        cur.close(); conn.close()

    # ── build INPUT form ─────────────────────────────────────────────────────
    with st.form("insert_form"):
        inputs: dict[str, object] = {}
        for field, col_type, nullable, key, default, extra in cols:
            # skip auto-increment
            if "auto_increment" in extra.lower():
                continue
            label = f"{field} ({col_type})"
            if "int" in col_type:
                # ensure value is float for number_input
                default_val = float(default) if default is not None else 0.0
                val = st.number_input(label, value=default_val, step=1.0)
            else:
                val = st.text_input(label, value=default or "")
            inputs[field] = val
        submit = st.form_submit_button("Insert Row")

    if not submit:
        return

    # ── perform INSERT ──────────────────────────────────────────────────────
    columns = ", ".join(f"`{f}`" for f in inputs.keys())
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
