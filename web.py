import streamlit as st
import requests
import pandas as pd

# Tving bredt layout og lyst tema
st.set_page_config(layout="wide", initial_sidebar_state="expanded")

# Overskrift og beskrivelse
st.title("Website Kundestatus")
st.write("Søg efter rådgiver og/eller kundenavn for at filtrere resultatet.")

# Vis spinner mens data hentes
with st.spinner("Henter data fra Podio..."):
    @st.cache_data(show_spinner=False)
    def fetch_data():
        url = "https://workflow-automation.podio.com/podiofeed.php?c=7116&a=582163&f=7874"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        df = pd.json_normalize(data)

        # Omdøb kolonner
        df = df.rename(columns={
            "web-designer": "webdesigner",
            "hvem-har-bolden": "hvemharbolden",
            "staging-site": "stagingsite"
        })

        # Rens alle tekstfelter
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

        # Erstat 'Designer' eller 'Rådgiver' med navnet fra den tilsvarende kolonne uden e-mail
        def clean_name(name):
            return name.split(" (email")[0].strip()

        df["hvemharbolden"] = df.apply(lambda row: clean_name(row["webdesigner"]) if row["hvemharbolden"].strip().lower() == "designer"
                                       else clean_name(row["radgiver"]) if row["hvemharbolden"].strip().lower() == "rådgiver"
                                       else row["hvemharbolden"], axis=1)

        return df

    df = fetch_data()

# Søgefelter vises med det samme
radgiver_input = st.text_input("Søg efter rådgiver")
status_input = st.text_input("Søg efter kundenavn")

# Filtrering
if radgiver_input:
    df = df[df["radgiver"].fillna("").str.lower().str.contains(radgiver_input.lower())]
if status_input:
    df = df[df["titel"].fillna("").str.lower().str.contains(status_input.lower())]

st.write(f"Fundet {len(df)} resultater.")

# Gør staging-links klikbare
def make_clickable(link):
    if pd.isna(link) or not link.strip().startswith("http"):
        return ""
    return f'<a href="{link}" target="_blank">Link til side</a>'

if "stagingsite" in df.columns:
    df["stagingsite"] = df["stagingsite"].apply(make_clickable)

# Definér kolonner og visningsnavne
kolonner = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
kolonner = [col for col in kolonner if col in df.columns]

df_visning = df[kolonner].copy()

# Opret ekstra kolonne til at markere rækker med match
if not df_visning.empty:
    df_visning["row_class"] = df_visning.apply(
        lambda row: "highlight-row" if row["hvemharbolden"].strip() == row["radgiver"].strip() else "",
        axis=1
    )
else:
    df_visning["row_class"] = ""

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

# Tabel-styling
st.markdown("""
    <style>
    table {
        width: 100%;
    }
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
        overflow-wrap: break-word;
    }
    table td:nth-child(2),
    table td:nth-child(3) {
        max-width: 180px;
        white-space: normal;
        word-break: break-word;
        overflow-wrap: break-word;
    }
    table td:nth-child(5) {
        max-width: 700px;
        white-space: normal;
        word-break: break-word;
        overflow-wrap: break-word;
    }
    .highlight-row {
        background-color: rgba(255, 0, 0, 0.1);
    }
    </style>
""", unsafe_allow_html=True)

# Konstruer HTML-tabel med styling
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