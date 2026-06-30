"""Streamlit user interface presentation layer."""

from datetime import datetime
from typing import List

import pandas as pd
import streamlit as st

from utils.domain import StravaActivity
from utils.service import StravaService

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
def render_merge_pipeline_dialog(service: StravaService, activities_to_merge: List[StravaActivity], target_name: str) -> None:
    """Launch manual deletion prompts and handle final unified processing uploads."""
    st.warning(
        "⚠️ **Strava rejette les doublons géospatiaux.** Vous devez impérativement supprimer "
        "les activités d'origine via les liens ci-dessous avant d'envoyer la nouvelle fusion."
    )

    for act in activities_to_merge:
        delete_url = service.get_delete_url(act)
        st.link_button(f"🗑️ Supprimer sur Strava : {act.name} ({act.distance_km}km)", url=delete_url, use_container_width=True)

    st.divider()
    st.write("Une fois les suppressions validées sur votre profil Strava, finalisez l'opération :")

    if st.button("🚀 Confirmer & Téléverser la fusion", type="primary", use_container_width=True):
        with st.spinner("Génération du GPX et synchronisation..."):
            success = service.merge_and_upload(activities_to_merge, target_name)
            if success:
                st.success("Nouvelle activité consolidée créée avec succès ! 🎉")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Une erreur est survenue lors de l'envoi vers Strava.")


st.title("🏃‍♂️ Strava Activity Merger")

# Instantiate our application coordinator
service = StravaService()
activities = service.get_recent_activities(limit=12)

if not activities:
    st.error("Impossible de récupérer les activités.")
    st.stop()


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
                render_merge_pipeline_dialog(service, pair, f"💼 Vélotaf - {date_label}")

    st.divider()


# ==========================================
# AUTOMATIC WEIGHT TRAINING RENAMING
# ==========================================
weight_info = StravaActivity.detect_WeightTraining(activities)

if weight_info:
    activity, new_name = weight_info
    st.info("💡 **Mode Automatique** : Activité muscu à renommer détectée !")
    col_info, col_btn = st.columns([3, 1])

    with col_info:
        st.markdown(f"**{new_name}**")
    with col_btn:
        # FIXED: Routed through service and uses the correct parameters
        if st.button("Renommer l'activité", key="auto_rename"):
            print("old name: ", activity.name)
            print("new name: ", new_name)
            service.rename_activity(activity.id, new_name)
            st.success("Activité renommée ! Actualisation...")
            st.cache_data.clear()
            st.rerun()


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
        render_merge_pipeline_dialog(service, selected_activities, new_name)
else:
    st.info("Veuillez cocher au moins 2 activités dans le tableau ci-dessus pour activer la fusion.")
