import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import re
import os

# ---------------------------------------------------------
# Secrets / config
# ---------------------------------------------------------
def get_secret(key: str, default: str | None = None) -> str | None:
    """
    Henter først fra Streamlit secrets, ellers fra environment variables.
    """
    if key in st.secrets:
        return str(st.secrets.get(key))
    return os.getenv(key, default)

KODE = get_secret("LOGIN_KODE")
PODIO_FEED_URL = get_secret("PODIO_FEED_URL")

# Fail-fast med klare beskeder (så du ikke får "blank skærm" uden forklaring)
missing = []
if not KODE:
    missing.append("LOGIN_KODE")
if not PODIO_FEED_URL:
    missing.append("PODIO_FEED_URL")

if missing:
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")
    st.error(
        "Mangler nødvendige secrets/variabler: "
        + ", ".join(missing)
        + ".\n\nTilføj dem i Streamlit Secrets (secrets.toml) eller som environment variables."
    )
    st.stop()

# ---------------------------------------------------------
# Page config (bevarer din logik)
# ---------------------------------------------------------
if "adgang_ok" in st.session_state and st.session_state.adgang_ok:
    st.set_page_config(layout="wide", initial_sidebar_state="auto")
else:
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------
# Kodebeskyttelse
# ---------------------------------------------------------
def check_access() -> bool:
    if "adgang_ok" not in st.session_state:
        st.session_state.adgang_ok = False

    if not st.session_state.adgang_ok:
        with st.sidebar:
            kode = st.text_input("Adgangskode", type="password")
            if kode == KODE:
                st.session_state.adgang_ok = True
                st.rerun()
            elif kode:
                st.error("Forkert kode.")
        return False

    return True

if not check_access():
    st.stop()

# ---------------------------------------------------------
# Titel og filtre
# ---------------------------------------------------------
col1, col2 = st.columns([18, 1])
with col1:
    st.title("Website Kundestatus")
with col2:
    with st.expander("🔧"):
        kun_vis_rode = st.checkbox("🔴", key="kun_rod")
        kun_vis_gronne = st.checkbox("🟢", key="kun_gron")
        kun_vis_morkerod = st.checkbox("⚫", key="kun_morkerod")

# Hent søgeord fra URL
query_params = st.query_params
url_search = query_params.get("search", "")

# ---------------------------------------------------------
# Hent data
# ---------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=1200)  # automatisk opdatering hver 20. minut
def fetch_data(feed_url: str) -> pd.DataFrame:
    response = requests.get(feed_url, timeout=30)
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

    def clean_name(name: str) -> str:
        return str(name).split(" (email")[0].strip()

    # Beskyt mod manglende kolonner i feed'et
    for required in ["kommentarer", "status", "radgiver", "webdesigner", "hvemharbolden"]:
        if required not in df.columns:
            df[required] = ""

    df["hvemharbolden"] = df.apply(
        lambda row: clean_name(row["webdesigner"])
        if str(row["hvemharbolden"]).strip().lower() == "designer"
        else clean_name(row["radgiver"])
        if str(row["hvemharbolden"]).strip().lower() == "rådgiver"
        else row["hvemharbolden"],
        axis=1
    )

    # Mørkerød flag
    def er_morkerod(kommentar: str, status: str) -> bool:
        match = re.match(r"(\d{2})[/-](\d{2})[/-](\d{2,4})", str(kommentar))
        if not match:
            return False
        dag, måned, år = match.groups()
        år = "20" + år if len(år) == 2 else år
        try:
            kommentar_dato = datetime(int(år), int(måned), int(dag))
            tre_måneder_siden = datetime.now() - timedelta(days=90)
            return kommentar_dato < tre_måneder_siden and str(status).lower() not in ["web: online", "annulleret"]
        except Exception:
            return False

    df["morkerod"] = df.apply(lambda row: er_morkerod(row["kommentarer"], row["status"]), axis=1)

    return df

with st.spinner("Henter data fra Podio..."):
    try:
        df = fetch_data(PODIO_FEED_URL)
    except requests.RequestException as e:
        st.error(f"Kunne ikke hente data fra feedet. Tjek PODIO_FEED_URL.\n\nFejl: {e}")
        st.stop()
    except ValueError as e:
        st.error(f"Feedet returnerede ikke gyldig JSON.\n\nFejl: {e}")
        st.stop()

# ---------------------------------------------------------
# Global søgning (og fra URL hvis sat)
# ---------------------------------------------------------
global_search = st.text_input(
    "",
    placeholder="🔎 Søg i hele tabellen (kundenavn, rådgiver, status, kommentar osv.)",
    value=url_search
)

if global_search:
    søg = global_search.lower()
    søg_i = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
    for col in søg_i:
        if col not in df.columns:
            df[col] = ""
    df = df[df[søg_i].apply(lambda row: row.astype(str).str.lower().str.contains(søg).any(), axis=1)]

# ---------------------------------------------------------
# Klikbare links
# ---------------------------------------------------------
def make_clickable(link: str) -> str:
    if pd.isna(link) or not str(link).strip().startswith("http"):
        return ""
    return f'<a href="{link}" target="_blank" rel="noopener noreferrer">Link til side</a>'

if "stagingsite" in df.columns:
    df["stagingsite"] = df["stagingsite"].apply(make_clickable)

# ---------------------------------------------------------
# Kolonner og visning
# ---------------------------------------------------------
kolonner = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
for col in kolonner:
    if col not in df.columns:
        df[col] = ""

df_visning = df[kolonner].copy()

# Highlight rows
if not df_visning.empty:
    df_visning["row_class"] = df.apply(
        lambda row: "highlight-row-red" if str(row["hvemharbolden"]).strip() == str(row["radgiver"]).strip()
        else "highlight-row-green" if str(row["hvemharbolden"]).strip() == str(row["webdesigner"]).split(" (email")[0].strip()
        else "",
        axis=1
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

# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
st.markdown("""
    <style>
    table { width: 100%; border-collapse: collapse; }
    table th {
        text-align: left !important;
        font-weight: bold !important;
        padding: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    table td { padding: 8px; vertical-align: top; }
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
    .highlight-row-red { background-color: rgba(255, 0, 0, 0.1); }
    .highlight-row-green { background-color: rgba(0, 255, 0, 0.08); }
    tr td { background-color: inherit; }
    tr.morkerod td {
        background-color: rgba(213, 2, 2, 0.55) !important;
        color: white;
    }
    a { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# HTML-tabel
# ---------------------------------------------------------
def style_rows(row: pd.Series) -> str:
    row_class = row.get("row_class", "")
    extra_class = "morkerod" if row.get("morkerod") else ""
    all_classes = f"{row_class} {extra_class}".strip()
    cols = [c for c in df_visning.columns if c not in ["row_class", "morkerod"]]
    return f'<tr class="{all_classes}">' + "".join([f"<td>{row[col]}</td>" for col in cols]) + "</tr>"

cols = [c for c in df_visning.columns if c not in ["row_class", "morkerod"]]
table_html = "<table><thead><tr>" + "".join([f"<th>{col}</th>" for col in cols]) + "</tr></thead><tbody>"

if not df_visning.empty:
    table_html += "".join(df_visning.apply(style_rows, axis=1).tolist())
else:
    table_html += f'<tr><td colspan="{len(cols)}">Ingen resultater fundet.</td></tr>'

table_html += "</tbody></table>"
st.write(table_html, unsafe_allow_html=True)
