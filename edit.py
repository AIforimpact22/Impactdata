import streamlit as st
import pandas as pd
import os
import altair as alt
from PIL import Image
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
import sqlite3

# --------------------------------------------------
# Basic configuration
# --------------------------------------------------
st.set_page_config(page_title="Wasp Biodiversity", layout="wide")

CSV_PATH  = r"C:\Users\sourc\OneDrive\Desktop\Python\Diyari\wasp_biodiversity_100.csv"
LOGO_PATH = r"C:\Users\sourc\OneDrive\Desktop\Python\Diyari\images.jpeg"

# --------------------------------------------------
# Helpers
# --------------------------------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

def append_to_csv(new_row: dict, path: str) -> None:
    pd.DataFrame([new_row]).to_csv(path, mode="a", header=False, index=False)

def append_bulk_csv(df_new: pd.DataFrame, path: str) -> None:
    df_new.to_csv(path, mode="a", header=False, index=False)

def save_full_dataset(df_new: pd.DataFrame, path: str) -> None:
    df_new.to_csv(path, index=False)

def clear_cache_and_rerun():
    st.cache_data.clear()
    st.experimental_rerun()

# --------------------------------------------------
# Sidebar & navigation
# --------------------------------------------------
st.sidebar.markdown("### 🐝 Wasp Biodiversity App")
if os.path.exists(LOGO_PATH):
    st.sidebar.image(Image.open(LOGO_PATH), use_container_width=True)
else:
    st.sidebar.warning("Logo image not found.")

PAGES = [
    "Home", "Visualization", "Add", "Edit (Form)",
    "Spreadsheet", "SQL", "Predict"
]
page = st.sidebar.radio("Go to", PAGES)

# --------------------------------------------------
# Load main dataset
# --------------------------------------------------
if not os.path.exists(CSV_PATH):
    st.error(f"CSV not found at:\n{CSV_PATH}")
    st.stop()

df = load_data(CSV_PATH)

# =====================================================================
# 1. HOME
# =====================================================================
if page == "Home":
    st.title("🪰 Wasp Biodiversity Database")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📊 Dataset Overview", "🔍 Filter by Species",
         "🌍 Filter by Location", "🧬 Filter by Family"]
    )

    with tab1:
        st.subheader("Full Dataset")
        st.markdown(f"**Total records:** {len(df)}")
        st.dataframe(df, use_container_width=True)

    with tab2:
        species = st.multiselect("Select Species", df["Species"].unique())
        view = df[df["Species"].isin(species)] if species else df
        st.markdown(f"**Records:** {len(view)}")
        st.dataframe(view, use_container_width=True)

    with tab3:
        location = st.multiselect("Select Location", df["Location"].unique())
        view = df[df["Location"].isin(location)] if location else df
        st.markdown(f"**Records:** {len(view)}")
        st.dataframe(view, use_container_width=True)

    with tab4:
        family = st.multiselect("Select Family", df["Family"].unique())
        view = df[df["Family"].isin(family)] if family else df
        st.markdown(f"**Records:** {len(view)}")
        st.dataframe(view, use_container_width=True)

# =====================================================================
# 2. VISUALIZATION
# =====================================================================
elif page == "Visualization":
    st.title("📈 Data Visualization")

    tab1, tab2, tab3 = st.tabs(
        ["Abundance by Species", "Aggressiveness by Nesting", "Species Count by Location"]
    )

    with tab1:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x=alt.X("Species", sort="-y"),
                    y="Abundance",
                    color="Species")
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)

    with tab2:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="Nesting Type",
                    y="mean(Aggressiveness)",
                    color="Nesting Type")
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)

    with tab3:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="Location",
                    y="count()",
                    color="Location")
            .properties(height=400)
        )
        st.altair_chart(chart, use_container_width=True)

# =====================================================================
# 3. ADD
# =====================================================================
elif page == "Add":
    st.title("➕ Add New Data")
    tab1, tab2 = st.tabs(["Add Single Record", "Upload Bulk CSV"])

    # ---- single record ----
    with tab1:
        with st.form("add_single_form"):
            new_id = int(df["ID"].max()) + 1
            col1, col2 = st.columns(2)
            with col1:
                species = st.text_input("Species")
                family  = st.text_input("Family")
                color   = st.text_input("Color")
            with col2:
                location = st.text_input("Location")
                abundance = st.number_input("Abundance", min_value=0, step=1)
                aggressiveness = st.slider("Aggressiveness (1-5)", 1, 5, 2)
            nesting = st.selectbox("Nesting Type", ["Ground", "Aerial", "Wood", "Other"])
            submitted = st.form_submit_button("Add Record")

            if submitted:
                if all([species, family, location, color]):
                    append_to_csv({
                        "ID": new_id, "Species": species, "Family": family,
                        "Location": location, "Abundance": abundance,
                        "Color": color, "Aggressiveness": aggressiveness,
                        "Nesting Type": nesting
                    }, CSV_PATH)
                    st.success(f"Added record for **{species}**.")
                    clear_cache_and_rerun()
                else:
                    st.error("All text fields are required!")

    # ---- bulk upload ----
    with tab2:
        st.markdown("Columns must match exactly: "
                    "`ID,Species,Family,Location,Abundance,Color,Aggressiveness,Nesting Type`")
        up = st.file_uploader("Upload CSV", type="csv")
        if up:
            try:
                new_df = pd.read_csv(up)
                st.dataframe(new_df.head(), use_container_width=True)
                if st.button("Append to Database"):
                    append_bulk_csv(new_df, CSV_PATH)
                    st.success(f"Appended {len(new_df)} rows.")
                    clear_cache_and_rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")

# =====================================================================
# 4. EDIT (Form)
# =====================================================================
elif page == "Edit (Form)":
    st.title("✏️ Edit Record (Form)")
    rec_id = st.number_input("Enter ID to edit", min_value=1, step=1)
    record = df[df["ID"] == rec_id]

    if record.empty:
        st.warning("No such ID.")
    else:
        row = record.iloc[0]
        with st.form("edit_form"):
            species = st.text_input("Species", row["Species"])
            family  = st.text_input("Family", row["Family"])
            location = st.text_input("Location", row["Location"])
            abundance = st.number_input("Abundance", 0, None, int(row["Abundance"]))
            color = st.text_input("Color", row["Color"])
            aggressiveness = st.slider("Aggressiveness", 1, 5, int(row["Aggressiveness"]))
            nesting = st.selectbox("Nesting Type", ["Ground","Aerial","Wood","Other"],
                                   index=["Ground","Aerial","Wood","Other"].index(row["Nesting Type"]))
            if st.form_submit_button("Save Changes"):
                df.loc[df["ID"] == rec_id] = [
                    rec_id, species, family, location, abundance,
                    color, aggressiveness, nesting
                ]
                save_full_dataset(df, CSV_PATH)
                st.success("Saved.")
                clear_cache_and_rerun()

# =====================================================================
# 5. SPREADSHEET (data_editor)
# =====================================================================
elif page == "Spreadsheet":
    st.title("📝 Spreadsheet Editor")
    st.caption("Edit cells directly, then click **Save** to persist.")
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, key="sheet"
    )
    if st.button("Save Spreadsheet"):
        save_full_dataset(edited, CSV_PATH)
        st.success("CSV saved.")
        clear_cache_and_rerun()

# =====================================================================
# 6. SQL
# =====================================================================
elif page == "SQL":
    st.title("🔍 SQL Editor")
    st.caption("Run SQLite queries against the current dataset (`data` table).")

    # Create in-memory sqlite DB
    conn = sqlite3.connect(":memory:")
    df.to_sql("data", conn, index=False, if_exists="replace")

    default_q = "SELECT * FROM data LIMIT 10;"
    query = st.text_area("SQL Query", default_q, height=150)
    if st.button("Run Query"):
        try:
            result = pd.read_sql_query(query, conn)
            st.dataframe(result, use_container_width=True)
        except Exception as e:
            st.error(str(e))

# =====================================================================
# 7. PREDICT
# =====================================================================
elif page == "Predict":
    st.title("🔮 Predict Features from Species")

    species_list = df["Species"].unique().tolist()
    choice = st.selectbox("Choose Species", species_list)

    if st.button("Run Prediction"):
        work = df.drop(columns=["ID"]).copy()

        # Encode input
        enc_species = LabelEncoder()
        work["Species_enc"] = enc_species.fit_transform(work["Species"])

        targets = ["Family", "Location", "Abundance", "Color", "Aggressiveness", "Nesting Type"]
        enc_target, models = {}, {}

        for tgt in targets:
            if work[tgt].dtype == "object":
                le = LabelEncoder()
                work[f"{tgt}_enc"] = le.fit_transform(work[tgt])
                enc_target[tgt] = le
                model = RandomForestClassifier(random_state=0).fit(
                    work[["Species_enc"]], work[f"{tgt}_enc"])
            else:
                model = RandomForestRegressor(random_state=0).fit(
                    work[["Species_enc"]], work[tgt])
            models[tgt] = model

        if choice not in enc_species.classes_:
            st.error("Species not found in training data.")
        else:
            X = pd.DataFrame({"Species_enc": [enc_species.transform([choice])[0]]})
            out = {}
            for tgt in targets:
                pred = models[tgt].predict(X)[0]
                if tgt in enc_target:
                    pred = enc_target[tgt].inverse_transform([int(pred)])[0]
                out[tgt] = pred

            st.success(f"Predictions for **{choice}**")
            st.json(out)
