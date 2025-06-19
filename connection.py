"""
Connection-Info page, imported by app.py.

render_connection_page(get_connection, db_config)
-------------------------------------------------
• get_connection : a callable from app.py
• db_config      : the same DB_CONFIG dict, for host/port/user display
"""

import streamlit as st

EXCLUDED = ("information_schema", "mysql", "performance_schema", "sys")

def render_connection_page(get_connection, db_config):
    st.title("Database Connection Info")

    # list databases
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SHOW DATABASES")
    dbs = [d[0] for d in cur.fetchall() if d[0] not in EXCLUDED]
    cur.close(); conn.close()

    if not dbs:
        st.info("No user-created databases yet.")
        return

    db = st.selectbox("Database", dbs)

    # plain snippets
    st.subheader("Shell")
    st.code(f"mysql -h {db_config['host']} -P {db_config['port']} "
            f"-u {db_config['user']} -p {db}", language="bash")

    st.subheader("Python")
    st.code(
        f"""import mysql.connector
conn = mysql.connector.connect(
    host="{db_config['host']}",
    port={db_config['port']},
    user="{db_config['user']}",
    password="YOUR_PASSWORD",
    database="{db}"
)""",
        language="python",
    )

    st.subheader("PHP (PDO)")
    st.code(
        f"""$pdo = new PDO('mysql:host={db_config['host']};
port={db_config['port']};dbname={db}',
'{db_config['user']}',
'YOUR_PASSWORD');""",
        language="php",
    )

    st.markdown(
        """
> **Replace** `YOUR_PASSWORD` with your real password.  
> Ensure your client can reach `{}:{}`.
""".format(db_config["host"], db_config["port"])
    )
