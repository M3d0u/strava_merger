"""Streamlite of the application"""

from datetime import datetime
from typing import List

import pandas as pd
import streamlit as st

from utils.domain import StravaActivity
from utils.strava_client import StravaAPIClient

st.set_page_config(page_title="Strava Activity Merger", page_icon="🏃‍♂️", layout="wide")


# ==========================================
# SECURITY GATE (BASIC AUTH)
# ==========================================
def check_password() -> bool:
    """Check password and session state"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Affichage du formulaire de login si non authentifié
    st.markdown("### 🔒 Accès réservé")
    password_input = st.text_input("Entrez le mot de passe de l'application :", type="password")

    if st.button("Se connecter", type="primary"):
        if password_input == st.secrets["APP_PASSWORD"]:
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("❌ Mot de passe incorrect.")

    return False


if not check_password():
    st.stop()

st.title("🏃‍♂️ Strava Activity Merger")

client = StravaAPIClient()
raw_data = client.fetch_activities(limit=12)

if not raw_data:
    st.error("Impossible de récupérer les activités.")
    st.stop()

activities: List[StravaActivity] = [StravaActivity.from_api(a) for a in raw_data]

# ==========================================
# AUTOMATIC COMMUTE MERGE ACTION BLOC
# ==========================================
commute_pairs = StravaActivity.detect_commutes(activities)

if commute_pairs:
    st.info(f"💡 **Mode Automatique** : {len(commute_pairs)} paire(s) de Vélotaf détectée(s) !")
    for idx, pair in enumerate(commute_pairs):
        date_label = datetime.fromisoformat(str(pair[0].raw.get("start_date_local"))).strftime("%d/%m/%Y")
        col_info, col_btn = st.columns([3, 1])

        with col_info:
            st.markdown(f"🚲 **Commute du {date_label}** ({pair[0].distance_km}km + {pair[1].distance_km}km)")

        with col_btn:
            if st.button(f"⚡ Fusionner le {date_label}", key=f"auto_merge_{idx}"):
                with st.spinner("Consolidation en cours..."):
                    gpx_xml = StravaActivity.merge_to_gpx(client, pair)
                    upload_res = client.upload_gpx(gpx_xml, f"💼 Vélotaf - {date_label}")

                    if upload_res and "id" in upload_res:
                        for act in pair:
                            act.delete(client)
                        st.success("Succès !")
                        st.cache_data.clear()
                        st.rerun()
    st.divider()

# ==========================================
# RENDER MANUAL TABLE
# ==========================================

display_df = pd.DataFrame([a.model_dump() for a in activities]).drop(columns=["raw", "streams"])

edited_df = st.data_editor(
    display_df,
    column_config={
        "selection": st.column_config.CheckboxColumn("Sélection", required=True),
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "date": "Date",
        "name": "Nom",
        "activity_type": "Type",
        "distance_km": "Distance (km)",
        "duration": "Durée",
    },
    disabled=["id", "date", "name", "activity_type", "distance_km", "duration"],
    hide_index=True,
)

selected_indices: List[int] = edited_df[edited_df["selection"]].index.tolist()
selected_activities: List[StravaActivity] = [activities[idx] for idx in selected_indices]

st.divider()

if len(selected_activities) >= 2:
    st.success(f"⚡ {len(selected_activities)} activités prêtes à être consolidées.")
    new_name = st.text_input("Nom de la nouvelle activité :", value=f"Fusion : {selected_activities[0].name}")
    clean_old = st.checkbox("Supprimer automatiquement les activités d'origine", value=True)

    if st.button("🚀 Exécuter le pipeline de fusion", type="primary"):
        with st.spinner("Génération du fichier de fusion..."):
            gpx_xml = StravaActivity.merge_to_gpx(client, selected_activities)
            upload_res = client.upload_gpx(gpx_xml, new_name)

            if upload_res and "id" in upload_res:
                if clean_old:
                    for act in selected_activities:
                        act.delete(client)
                st.balloons()
                st.cache_data.clear()
                st.rerun()
else:
    st.info("Veuillez cocher au moins 2 activités dans le tableau ci-dessus pour activer la fusion.")
