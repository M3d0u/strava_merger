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


# ==========================================
# REUSABLE UI PIPELINE COMPONENT
# ==========================================
@st.dialog("🔄 Validation de la fusion")  # type: ignore[misc]
def render_merge_pipeline_dialog(client: StravaAPIClient, activities_to_merge: List[StravaActivity], target_name: str) -> None:
    """Launch the process: give deletion links, then handle the upload."""
    st.warning(
        "⚠️ **Strava rejette les doublons géospatiaux.** Vous devez impérativement supprimer "
        "les activités d'origine via les liens ci-dessous avant d'envoyer la nouvelle fusion."
        "(C'est malheureusement impossible via l'api)"
    )

    for act in activities_to_merge:
        delete_url = act.delete(client)
        st.link_button(f"🗑️ Supprimer sur Strava : {act.name} ({act.distance_km}km)", url=delete_url, use_container_width=True)

    st.divider()
    st.write("Une fois les suppressions validées sur votre profil Strava, finalisez l'opération :")

    if st.button("🚀 Confirmer & Téléverser la fusion", type="primary", use_container_width=True):
        with st.spinner("Génération du GPX et synchronisation..."):
            gpx_xml = StravaActivity.merge_to_gpx(client, activities_to_merge)
            upload_res = client.upload_gpx(gpx_xml, target_name)

            if upload_res and "id" in upload_res:
                st.success("Nouvelle activité consolidée créée avec succès ! 🎉")
                st.cache_data.clear()
                st.rerun()


st.title("🏃‍♂️ Strava Activity Merger")

client = StravaAPIClient()
if client is None:
    st.error(f"Erreur d'authentification Strava : {client}")
    st.stop()
    RuntimeError("Streamlit execution stopped")

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
                render_merge_pipeline_dialog(client, pair, f"💼 Vélotaf - {date_label}")

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

    if st.button("🚀 Exécuter le pipeline de fusion", type="primary"):
        render_merge_pipeline_dialog(client, selected_activities, new_name)
else:
    st.info("Veuillez cocher au moins 2 activités dans le tableau ci-dessus pour activer la fusion.")
