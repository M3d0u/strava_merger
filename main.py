"""Streamlit user interface presentation layer."""

from datetime import datetime

import pandas as pd
import streamlit as st

from utils.domain import StravaActivity, StravaActivityDisplay
from utils.service import StravaService

# Set modern, wide page layout
st.set_page_config(page_title="Strava Activity Merger", page_icon="🏃‍♂️", layout="wide", initial_sidebar_state="collapsed")

# Custom minimalistic CSS to elevate native Streamlit elements
st.markdown(
    """
    <style>
    /* Clean up block padding */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    /* Soften background elements */
    div[data-testid="stExpander"], div[data-testid="element-container"] { border-radius: 8px; }
    </style>
""",
    unsafe_allow_html=True,
)


# ==========================================
# SECURITY GATE (BASIC AUTH)
# ==========================================
def check_password() -> bool:
    """Check password and session state with clean layout"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # Centered clean login box layout
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        st.write("")
        st.write("")
        with st.container(border=True):
            st.markdown("### 🔒 Accès réservé")
            password_input = st.text_input("Mot de passe de l'application :", type="password")
            if st.button("Se connecter", type="primary", width="stretch"):
                if password_input == st.secrets["APP_PASSWORD"]:
                    st.session_state.password_correct = True
                    st.rerun()
                else:
                    st.error("❌ Mot de passe incorrect.")
    return False


if not check_password():
    st.stop()


# ==========================================
# REUSABLE UI PIPELINE COMPONENT HELPERS
# ==========================================
def render_merged_gpx_download_button(activities_to_merge: list[StravaActivity], target_name: str, key: str | None = None) -> None:
    """Render a download button for the compiled merged GPX file."""
    try:
        merged_gpx = StravaActivity.merge_to_gpx(activities_to_merge)
        st.download_button(
            label="📥 Télécharger le GPX fusionné",
            data=merged_gpx,
            file_name=f"{target_name.replace(' ', '_')}.gpx",
            mime="application/gpx+xml",
            width="stretch",
            key=key,
        )
    except Exception as e:
        st.error(f"Impossible de générer le GPX fusionné : {e}")


def render_success_view(dialog_success_key: str, activities_to_merge: list[StravaActivity], target_name: str) -> None:
    """Render the success message and download button for the merged GPX."""
    st.success("Nouvelle activité consolidée créée avec succès ! 🎉")
    render_merged_gpx_download_button(activities_to_merge, target_name, key="success_upload_gpx_download")

    if st.button("🔄 Rafraîchir la page", type="primary", width="stretch"):
        del st.session_state[dialog_success_key]
        st.cache_data.clear()
        st.rerun()


def render_activities_actions(activities_to_merge: list[StravaActivity], service: StravaService) -> None:
    """Render delete links and GPX download buttons for original activities."""
    for act in activities_to_merge:
        col_del, col_dl = st.columns([1, 1])
        with col_del:
            delete_url = service.get_delete_url(act)
            st.link_button(f"🗑️ Supprimer : {act.name} ({act.distance_km} km)", url=delete_url, width="stretch")
        with col_dl:
            try:
                gpx_data = StravaActivity.merge_to_gpx([act])
                st.download_button(
                    label=f"📥 Télécharger GPX : {act.name}",
                    data=gpx_data,
                    file_name=f"{act.name.replace(' ', '_')}_{act.id}.gpx",
                    mime="application/gpx+xml",
                    width="stretch",
                )
            except Exception as e:
                st.error(f"Impossible de générer le GPX de {act.name} : {e}")


# ==========================================
# REUSABLE UI PIPELINE COMPONENT
# ==========================================
@st.dialog("🔄 Validation de la fusion", width="large")  # type: ignore[misc]
def render_merge_pipeline_dialog(service: StravaService, activities_to_merge: list[StravaActivity], target_name: str) -> None:
    """Launch manual deletion prompts and handle final unified processing uploads."""
    # Ensure a state variable to track the merge success of the current dialog session
    dialog_success_key = f"merge_success_{'-'.join(str(act.id) for act in activities_to_merge)}"
    if dialog_success_key not in st.session_state:
        st.session_state[dialog_success_key] = False

    if st.session_state[dialog_success_key]:
        render_success_view(dialog_success_key, activities_to_merge, target_name)
        st.stop()

    # Pre-fetch streams if they aren't loaded to enable individual GPX downloads
    for act in activities_to_merge:
        if not act.streams:
            with st.spinner(f"Récupération des données pour {act.name}..."):
                act.streams = service.client.fetch_streams(act.id)

    st.warning(
        "⚠️ **Strava rejette les doublons géospatiaux.** Vous devez impérativement supprimer "
        "les activités d'origine via les liens ci-dessous avant d'envoyer la nouvelle fusion."
    )

    st.write("### 1. Sauvegarder et Supprimer les doublons d'origine")
    render_activities_actions(activities_to_merge, service)

    st.divider()
    st.write("### 2. Finaliser la synchronisation")
    st.caption("Une fois les suppressions validées sur votre profil Strava, lancez la création :")

    if st.button("🚀 Confirmer & lancer la fusion", type="primary", width="stretch"):
        with st.spinner("Génération du GPX et synchronisation..."):
            success, error_msg = service.merge_and_upload(activities_to_merge, target_name)
            if success:
                st.session_state[dialog_success_key] = True
                st.rerun()
            else:
                st.error("Une erreur est survenue lors de l'envoi vers Strava.")
                if error_msg:
                    st.error(f"⚠️ **Détails de l'erreur :** {error_msg}")

                # Allow download of the compiled GPX even if upload failed
                st.warning("📥 **Vous pouvez tout de même télécharger le fichier GPX fusionné ci-dessous :**")
                render_merged_gpx_download_button(activities_to_merge, target_name, key="failed_upload_gpx_download")


# ==========================================
# MAIN APP INTERFACE
# ==========================================

# Simple title layout
st.title("🏃‍♂️ Strava Activity Merger")
st.caption("Fusion de trajets et renommages d'entraînements.")
st.write("")

# Instantiate application coordinator
service = StravaService()

with st.spinner("Récupération de vos activités récentes..."):
    activities = service.get_recent_activities(limit=12)

if not activities:
    st.error("Impossible de récupérer les activités récentes de votre profil Strava.")
    st.stop()

# Detect automated workflow opportunities
commute_pairs = StravaActivity.detect_commutes(activities)
weight_info = StravaActivity.detect_WeightTraining(activities)
run_activities = StravaActivity.detect_Run(activities)


# ==========================================
# SECTION: SMART SUGGESTIONS
# ==========================================
if commute_pairs or weight_info or run_activities:
    st.subheader("💡 Actions Recommandées")

    if commute_pairs:
        with st.container(border=True):
            st.markdown("#### 🚲 Fusions Vélotaf Détectées")
            for idx, pair in enumerate(commute_pairs):
                date_label = datetime.fromisoformat(str(pair[0].raw.get("start_date_local"))).strftime("%d/%m/%Y")
                col_info, col_btn = st.columns([3, 1], vertical_alignment="center")

                with col_info:
                    st.markdown(f"**Trajet du {date_label}**  \n`Aller/Retour : {pair[0].distance_km} km + {pair[1].distance_km} km`")
                with col_btn:
                    if st.button("⚡ Fusionner", key=f"auto_merge_{idx}", width="stretch"):
                        render_merge_pipeline_dialog(service, pair, f"💼 Vélotaf - {date_label}")

    if weight_info:
        for weight in weight_info:
            activity, new_name = weight
            with st.container(border=True):
                st.markdown("#### 💪 Activités Musculation Détectées")
                col_info, col_btn = st.columns([3, 1], vertical_alignment="center")

                with col_info:
                    st.markdown(f"Activité générique détectée :  \n`Renommer vers : {new_name}`")
                with col_btn:
                    if st.button("🏷️ Renommer", key="auto_rename", width="stretch"):
                        service.rename_activity(activity.id, new_name)
                        st.success("Activité mise à jour avec succès ! 🎉")
                        st.cache_data.clear()
                        st.rerun()

    if run_activities:
        with st.container(border=True):
            st.markdown("#### 🏃‍♂️ Activités Course Détectées")
            for idx, (activity, suggested_name, suggested_desc) in enumerate(run_activities):
                col_info, col_btn = st.columns([3, 1], vertical_alignment="center")

                with col_info:
                    st.markdown(f"**{activity.name}**  \n`Distance : {activity.distance_km} km` (le {activity.date})")
                    user_name = st.text_input(
                        "Nouveau nom de l'activité :",
                        value=suggested_name,
                        key=f"run_name_{activity.id}_{idx}",
                    )
                    user_desc = st.text_area(
                        "Description de l'activité (météo incluse) :",
                        value=suggested_desc,
                        key=f"run_desc_{activity.id}_{idx}",
                        height=100,
                    )
                with col_btn:
                    if st.button("🏷️ Renommer & Enregistrer", key=f"run_rename_btn_{activity.id}_{idx}", type="primary", width="stretch"):
                        with st.spinner("Mise à jour sur Strava..."):
                            service.rename_activity(activity.id, user_name, description=user_desc)
                            st.success("Activité mise à jour avec succès ! 🎉")
                            st.cache_data.clear()
                            st.rerun()
    st.write("")


# ==========================================
# SECTION: WORKSPACE / MANUAL SELECTION
# ==========================================
st.subheader("📋 Sélection Manuelle")

# Build visual dataframe structure
display_df = pd.DataFrame([StravaActivityDisplay.from_activity(a).model_dump() for a in activities])

edited_df = st.data_editor(
    display_df,
    column_config={
        "selection": st.column_config.CheckboxColumn("Sélection", required=True, default=False),
        "id": st.column_config.NumberColumn("ID", format="%d"),
        "date": "Date",
        "name": "Nom",
        "activity_type": "Type",
        "distance_km": "Distance (km)",
        "duration": "Durée",
    },
    disabled=["id", "date", "name", "activity_type", "distance_km", "duration"],
    hide_index=True,
    width="stretch",
)

# Extract dynamic selections
selected_indices = edited_df[edited_df["selection"]].index.tolist()
selected_activities = [activities[idx] for idx in selected_indices]

# Context-aware dynamic bottom action panel
if len(selected_activities) >= 2:
    st.write("")
    with st.container(border=True):
        st.markdown(f"### ⚡ Fusionner les {len(selected_activities)} activités sélectionnées")

        col_input, col_action = st.columns([2, 1], vertical_alignment="bottom")
        with col_input:
            new_name = st.text_input("Nom pour l'activité finale :", value=f"Fusion : {selected_activities[0].name}")
        with col_action:
            if st.button("🚀 Lancer la fusion", type="primary", width="stretch"):
                render_merge_pipeline_dialog(service, selected_activities, new_name)
