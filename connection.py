"""
Connection-Info page split out from app.py.

Expose a single function:

    render_connection_page(get_connection)

`get_connection` is injected by app.py, so this file
contains **zero duplicated credentials**.
"""

import streamlit as st

EXCLUDED_SYS_DBS = ("information_schema", "mysql", "performance_schema", "sys")

def render_connection_page(get_connection):
    """Display connection snippets for any user-created database."""
    st.title("Database Connection Info")
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SHOW DATABASES")
        dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED_SYS_DBS]
    finally:
        cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases."); return

    db = st.selectbox("Choose a database", dbs)

    st.markdown("### MySQL CLI")
    st.code(
        f"mysql -h {conn.server_host} -P {conn.server_port} "
        f"-u {conn.user} -p {db}",
        language="bash",
    )

    st.markdown("### Python (mysql-connector-python)")
    st.code(
        f"""import mysql.connector
conn = mysql.connector.connect(
    host="{conn.server_host}",
    port={conn.server_port},
    user="{conn.user}",
    password="YOUR_PASSWORD",
    database="{db}"
)""",
        language="python",
    )

    st.markdown("### PHP (PDO)")
    st.code(
        f"""$pdo = new PDO('mysql:host={conn.server_host};port={conn.server_port};dbname={db}',
               '{conn.user}', 'YOUR_PASSWORD');""",
        language="php",
    )

    st.markdown(
        """
---
- **Replace** `YOUR_PASSWORD` with your actual password.
- Ensure your client can reach the server/IP & port shown above.
---
"""
    )
