import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import re
import os

# ---------------------------------------------------------
# Secrets / config
# ---------------------------------------------------------
# Python 3.9 kompatibel (ingen str | None syntaks)
def get_secret(key, section=None):
    if section and section in st.secrets and key in st.secrets[section]:
        return str(st.secrets[section][key])
    if key in st.secrets:
        return str(st.secrets.get(key))
    return os.getenv(key)

KODE = get_secret("LOGIN_KODE")

# Hent Podio keys
PODIO_CLIENT_ID = get_secret("client_id", section="podio")
PODIO_CLIENT_SECRET = get_secret("client_secret", section="podio")
PODIO_APP_ID = get_secret("app_id", section="podio") 
PODIO_APP_TOKEN = get_secret("app_token", section="podio")

# Fail-fast
missing = []
if not KODE: missing.append("LOGIN_KODE")
if not PODIO_CLIENT_ID: missing.append("podio.client_id")
if not PODIO_CLIENT_SECRET: missing.append("podio.client_secret")

if missing:
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")
    st.error(f"Mangler secrets: {', '.join(missing)}")
    st.stop()

# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------
if "adgang_ok" in st.session_state and st.session_state.adgang_ok:
    st.set_page_config(layout="wide", initial_sidebar_state="auto")
else:
    st.set_page_config(layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------
# Kodebeskyttelse
# ---------------------------------------------------------
def check_access():
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
    st.title("Website Kundestatus (API)")
with col2:
    with st.expander("🔧"):
        kun_vis_rode = st.checkbox("🔴", key="kun_rod")
        kun_vis_gronne = st.checkbox("🟢", key="kun_gron")
        kun_vis_morkerod = st.checkbox("⚫", key="kun_morkerod")

query_params = st.query_params
url_search = query_params.get("search", "")

# ---------------------------------------------------------
# Hent data (DIREKTE PODIO API UDEN LIBRARY)
# ---------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=600)
def fetch_podio_data():
    try:
        # 1. Hent Access Token (Login)
        auth_url = "https://api.podio.com/oauth/token"
        auth_data = {
            "grant_type": "app",
            "app_id": PODIO_APP_ID,
            "app_token": PODIO_APP_TOKEN,
            "client_id": PODIO_CLIENT_ID,
            "client_secret": PODIO_CLIENT_SECRET
        }
        auth_res = requests.post(auth_url, data=auth_data)
        
        if auth_res.status_code != 200:
            st.error(f"Kunne ikke logge ind i Podio. Tjek secrets. Fejl: {auth_res.text}")
            return pd.DataFrame()

        access_token = auth_res.json()['access_token']

        # 2. Hent Items (Her var fejlen før - rettet til 'Bearer')
        items_url = f"https://api.podio.com/item/app/{PODIO_APP_ID}/?limit=500"
        headers = {"Authorization": f"Bearer {access_token}"}
        
        items_res = requests.get(items_url, headers=headers)
        
        if items_res.status_code != 200:
            st.error(f"Kunne ikke hente items. Fejl: {items_res.text}")
            return pd.DataFrame()

        raw_items = items_res.json()
        
        # 3. Parse JSON strukturen til fladt format
        processed_rows = []
        for item in raw_items['items']:
            row = {
                "titel": item.get('title', ''),
                "item_id": item.get('item_id')
            }
            
            # Gennemgå alle felter i itemet
            for field in item['fields']:
                external_id = field['external_id'] # F.eks. "web-designer"
                values = field['values']
                
                # Uddrag værdi baseret på felttype
                val_str = ""
                if not values:
                    val_str = ""
                elif field['type'] == 'app': # Relationsfelt
                    val_str = values[0]['value'].get('title', '')
                elif field['type'] == 'contact': # Kontaktperson
                    val_str = values[0]['value'].get('name', '')
                elif field['type'] == 'date': # Dato
                    start = values[0].get('start_date_utc', '')
                    val_str = start
                elif field['type'] == 'category': # Kategori
                    val_str = values[0]['value'].get('text', '')
                else:
                    # Standard tekst/tal
                    val_str = values[0].get('value', '')
                
                row[external_id] = str(val_str)
            
            processed_rows.append(row)
            
        df = pd.DataFrame(processed_rows)
        return df

    except Exception as e:
        st.error(f"Podio API fejl: {e}")
        return pd.DataFrame()

# Behandling af data (samme logik som før)
def process_dataframe(df):
    if df.empty:
        return pd.DataFrame(columns=["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"])

    # Rename kolonner
    df = df.rename(columns={
        "web-designer": "webdesigner",
        "hvem-har-bolden": "hvemharbolden",
        "staging-site": "stagingsite",
        "radgiver": "radgiver", 
        "status": "status",
        "kommentarer": "kommentarer"
    })

    # Rens tekst
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()

    def clean_name(name):
        return str(name).split(" (email")[0].strip()

    # Sikr kolonner findes
    for required in ["kommentarer", "status", "radgiver", "webdesigner", "hvemharbolden"]:
        if required not in df.columns:
            df[required] = ""

    # Logik: Hvem har bolden
    df["hvemharbolden"] = df.apply(
        lambda row: clean_name(row["webdesigner"])
        if str(row["hvemharbolden"]).strip().lower() == "designer"
        else clean_name(row["radgiver"])
        if str(row["hvemharbolden"]).strip().lower() == "rådgiver"
        else row["hvemharbolden"],
        axis=1
    )

    # Mørkerød flag logic
    def er_morkerod(kommentar, status):
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

with st.spinner("Henter data sikkert fra Podio API..."):
    raw_df = fetch_podio_data()
    df = process_dataframe(raw_df)

# ---------------------------------------------------------
# Global søgning
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
def make_clickable(link):
    if pd.isna(link) or len(str(link)) < 5: 
        return ""
    clean_link = str(link).strip()
    if not clean_link.startswith("http"):
        clean_link = "http://" + clean_link
    return f'<a href="{clean_link}" target="_blank" rel="noopener noreferrer">Link til side</a>'

if "stagingsite" in df.columns:
    df["stagingsite"] = df["stagingsite"].apply(make_clickable)

# ---------------------------------------------------------
# Visning
# ---------------------------------------------------------
kolonner = ["titel", "radgiver", "webdesigner", "status", "kommentarer", "hvemharbolden", "stagingsite"]
for col in kolonner:
    if col not in df.columns:
        df[col] = ""

df_visning = df[kolonner].copy()

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

if kun_vis_rode:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-red"]
elif kun_vis_gronne:
    df_visning = df_visning[df_visning["row_class"] == "highlight-row-green"]
elif kun_vis_morkerod:
    df_visning = df_visning[df_visning["morkerod"]]

st.write(f"Fundet {len(df_visning)} resultater.")

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
    table td:nth-child(1), table td:nth-child(4), table td:nth-child(6) { max-width: 150px; white-space: normal; word-break: break-word; }
    table td:nth-child(2), table td:nth-child(3) { max-width: 180px; white-space: normal; word-break: break-word; }
    table td:nth-child(5) { max-width: 700px; white-space: normal; word-break: break-word; }
    .highlight-row-red { background-color: rgba(255, 0, 0, 0.1); }
    .highlight-row-green { background-color: rgba(0, 255, 0, 0.08); }
    tr td { background-color: inherit; }
    tr.morkerod td { background-color: rgba(213, 2, 2, 0.55) !important; color: white; }
    a { text-decoration: underline; }
    </style>
""", unsafe_allow_html=True)

def style_rows(row):
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