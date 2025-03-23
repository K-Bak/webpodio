import streamlit as st
import requests
import pandas as pd

# Tving bredt layout og lyst tema
st.set_page_config(layout="wide", initial_sidebar_state="expanded")

# Titel og filter-knapper i samme række
col1, col2 = st.columns([8, 1])
with col1:
    st.title("Website Kundestatus")
with col2:
    kun_vis_rode = st.checkbox("🔴", key="kun_rod")
    kun_vis_gronne = st.checkbox("🟢", key="kun_gron")

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
    df_visning["row_class"] = df_visning.apply(
        lambda row: "highlight-row-red" if row["hvemharbolden"].strip() == row["radgiver"].strip()
        else "highlight-row-green" if row["hvemharbolden"].strip() == row["webdesigner"].split(" (email")[0].strip()
        else "", axis=1
    )
else:
    df_visning["row_class"] = ""

# Filtrering
if kun_vis_rode:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-red"]
elif kun_vis_gronne:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-green"]

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
    </style>
""", unsafe_allow_html=True)

# HTML-tabel
def style_rows(row):
    cls = row["row_class"]
    return f'<tr class="{cls}">' + "".join([f"<td>{row[col]}</td>" for col in df_visning.columns if col != "row_class"]) + "</tr>"

table_html = "<table><thead><tr>" + "".join([f"<th>{col}</th>" for col in df_visning.columns if col != "row_class"]) + "</tr></thead><tbody>"
if not df_visning.empty:
    table_html += "".join(df_visning.apply(style_rows, axis=1).tolist())
else:
    table_html += '<tr><td colspan="7">Ingen resultater fundet.</td></tr>'
table_html += "</tbody></table>"

st.write(table_html, unsafe_allow_html=True)