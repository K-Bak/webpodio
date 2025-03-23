import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import re

# Tving bredt layout og lyst tema
st.set_page_config(layout="wide", initial_sidebar_state="expanded")

# Titel og avancerede filtre i samme række
col1, col2 = st.columns([12, 1])
with col1:
    st.title("Website Kundestatus")
with col2:
    with st.expander("🔧"):
        kun_vis_rode = st.checkbox("🔴", key="kun_rod")
        kun_vis_gronne = st.checkbox("🟢", key="kun_gron")
        kun_vis_morkerod = st.checkbox("⚫", key="kun_morkerod")

# Hent data
with st.spinner("Henter data fra Podio..."):
    @st.cache_data(show_spinner=False)
    def fetch_data():
        url = "https://workflow-automation.podio.com/podiofeed.php?c=7116&a=582163&f=7874"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        df = pd.json_normalize(data)

        df = df.rename(columns={
            "web-designer": "webdesigner",
            "hvem-har-bolden": "hvemharbolden",
            "staging-site": "stagingsite"
        })

        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

        def clean_name(name):
            return name.split(" (email")[0].strip()

        df["hvemharbolden"] = df.apply(lambda row: clean_name(row["webdesigner"]) if row["hvemharbolden"].strip().lower() == "designer"
                                       else clean_name(row["radgiver"]) if row["hvemharbolden"].strip().lower() == "rådgiver"
                                       else row["hvemharbolden"], axis=1)

        # Mørkerød flag: ældre end 3 måneder OG ikke Web: online eller ANNULLERET
        def er_morkerod(kommentar, status):
            match = re.match(r"(\d{2})[/-](\d{2})[/-](\d{2,4})", kommentar)
            if not match:
                return False
            dag, måned, år = match.groups()
            år = "20" + år if len(år) == 2 else år
            try:
                kommentar_dato = datetime(int(år), int(måned), int(dag))
                tre_måneder_siden = datetime.now() - timedelta(days=90)
                return kommentar_dato < tre_måneder_siden and status.lower() not in ["web: online", "annulleret"]
            except:
                return False

        df["morkerod"] = df.apply(lambda row: er_morkerod(row["kommentarer"], row["status"]), axis=1)

        return df

    df = fetch_data()

# Global søgning
global_search = st.text_input(
    "",
    placeholder="🔎 Søg i hele tabellen (kundenavn, rådgiver, status, kommentar osv.)"
)

if global_search:
    søg = global_search.lower()
    søg_i = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
    df = df[df[søg_i].apply(lambda row: row.astype(str).str.lower().str.contains(søg).any(), axis=1)]

# Klikbare links
def make_clickable(link):
    if pd.isna(link) or not link.strip().startswith("http"):
        return ""
    return f'<a href="{link}" target="_blank">Link til side</a>'

if "stagingsite" in df.columns:
    df["stagingsite"] = df["stagingsite"].apply(make_clickable)

# Kolonner og visning
kolonner = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
df_visning = df[kolonner].copy()

# Highlight rows
if not df_visning.empty:
    df_visning["row_class"] = df.apply(
        lambda row: "highlight-row-red" if row["hvemharbolden"].strip() == row["radgiver"].strip()
        else "highlight-row-green" if row["hvemharbolden"].strip() == row["webdesigner"].split(" (email")[0].strip()
        else "", axis=1
    )
    df_visning["morkerod"] = df["morkerod"]
else:
    df_visning["row_class"] = ""
    df_visning["morkerod"] = False

# Filtrering
if kun_vis_rode:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-red"]
elif kun_vis_gronne:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-green"]
elif kun_vis_morkerod:
    df_visning = df_visning[df_visning["morkerod"]]

st.write(f"Fundet {len(df_visning)} resultater.")

# Visningsnavne
visningsnavne = {
    "titel": "Kundenavn",
    "radgiver": "Rådgiver",
    "webdesigner": "Designer",
    "status": "Status",
    "kommentarer": "Kommentar",
    "hvemharbolden": "Hvem har bolden",
    "stagingsite": "Staging site"
}
df_visning = df_visning.rename(columns=visningsnavne)

# Styling
st.markdown("""
    <style>
    table { width: 100%; }
    table th {
        text-align: left !important;
        font-weight: bold !important;
    }
    table td:nth-child(1),
    table td:nth-child(4),
    table td:nth-child(6) {
        max-width: 150px;
        white-space: normal;
        word-break: break-word;
    }
    table td:nth-child(2),
    table td:nth-child(3) {
        max-width: 180px;
        white-space: normal;
        word-break: break-word;
    }
    table td:nth-child(5) {
        max-width: 700px;
        white-space: normal;
        word-break: break-word;
    }
    .highlight-row-red {
        background-color: rgba(255, 0, 0, 0.1);
    }
    .highlight-row-green {
        background-color: rgba(0, 255, 0, 0.08);
    }
    tr td {
        background-color: inherit;
    }
    tr.morkerod td {
        background-color: rgba(213, 2, 2, 0.55) !important;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# HTML-tabel
def style_rows(row):
    row_class = row["row_class"]
    extra_class = "morkerod" if row.get("morkerod") else ""
    all_classes = f"{row_class} {extra_class}".strip()
    return f'<tr class="{all_classes}">' + "".join([f"<td>{row[col]}</td>" for col in df_visning.columns if col not in ["row_class", "morkerod"]]) + "</tr>"

table_html = "<table><thead><tr>" + "".join([f"<th>{col}</th>" for col in df_visning.columns if col not in ["row_class", "morkerod"]]) + "</tr></thead><tbody>"
if not df_visning.empty:
    table_html += "".join(df_visning.apply(style_rows, axis=1).tolist())
else:
    table_html += '<tr><td colspan="7">Ingen resultater fundet.</td></tr>'
table_html += "</tbody></table>"

st.write(table_html, unsafe_allow_html=True)