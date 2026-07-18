"""Streamlit user interface presentation layer."""

from datetime import datetime
import pandas as pd
import streamlit as st

from utils.domain import StravaActivity
from utils.service import StravaService

# Set modern, wide page layout
st.set_page_config(
    page_title="Strava Activity Merger", 
    page_icon="🏃‍♂️", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom minimalistic CSS to elevate native Streamlit elements
st.markdown("""
    <style>
    /* Clean up block padding */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    /* Soften background elements */
    div[data-testid="stExpander"], div[data-testid="element-container"] { border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)


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
            if st.button("Se connecter", type="primary", use_container_width=True):
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
@st.dialog("🔄 Validation de la fusion", width="large")  # type: ignore[misc]
def render_merge_pipeline_dialog(service: StravaService, activities_to_merge: list[StravaActivity], target_name: str) -> None:
    """Launch manual deletion prompts and handle final unified processing uploads."""
    st.warning(
        "⚠️ **Strava rejette les doublons géospatiaux.** Vous devez impérativement supprimer "
        "les activités d'origine via les liens ci-dessous avant d'envoyer la nouvelle fusion."
    )

    st.write("### 1. Supprimer les doublons d'origine")
    for act in activities_to_merge:
        delete_url = service.get_delete_url(act)
        st.link_button(
            f"🗑️ Supprimer : {act.name} ({act.distance_km} km)", 
            url=delete_url, 
            use_container_width=True
        )

    st.divider()
    st.write("### 2. Finaliser la synchronisation")
    st.caption("Une fois les suppressions validées sur votre profil Strava, lancez la création :")
    
    if st.button("🚀 Confirmer & Téléverser la fusion", type="primary", use_container_width=True):
        with st.spinner("Génération du GPX et synchronisation..."):
            success, error_msg = service.merge_and_upload(activities_to_merge, target_name)
            if success:
                st.success("Nouvelle activité consolidée créée avec succès ! 🎉")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Une erreur est survenue lors de l'envoi vers Strava.")
                if error_msg:
                    st.error(f"⚠️ **Détails de l'erreur :** {error_msg}")


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


# ==========================================
# SECTION: SMART SUGGESTIONS
# ==========================================
if commute_pairs or weight_info:
    st.subheader("💡 Actions Recommandées")
    
    # Process Automated Commutes
    if commute_pairs:
        with st.container(border=True):
            st.markdown("#### 🚲 Fusions Vélotaf Détectées")
            for idx, pair in enumerate(commute_pairs):
                date_label = datetime.fromisoformat(str(pair[0].raw.get("start_date_local"))).strftime("%d/%m/%Y")
                col_info, col_btn = st.columns([3, 1], vertical_alignment="middle")
                
                with col_info:
                    st.markdown(f"**Trajet du {date_label}**  \n`Aller/Retour : {pair[0].distance_km} km + {pair[1].distance_km} km`")
                with col_btn:
                    if st.button(f"⚡ Fusionner", key=f"auto_merge_{idx}", use_container_width=True):
                        render_merge_pipeline_dialog(service, pair, f"💼 Vélotaf - {date_label}")
    
    # Process Weight Training Shortcuts
    if weight_info:
        activity, new_name = weight_info
        with st.container(border=True):
            st.markdown("#### 💪 Renommage Musculation")
            col_info, col_btn = st.columns([3, 1], vertical_alignment="middle")
            
            with col_info:
                st.markdown(f"Activité générique détectée :  \n`Renommer vers : {new_name}`")
            with col_btn:
                if st.button("🏷️ Renommer", key="auto_rename", use_container_width=True):
                    service.rename_activity(activity.id, new_name)
                    st.success("Activité mise à jour !")
                    st.cache_data.clear()
                    st.rerun()
    st.write("")


# ==========================================
# SECTION: WORKSPACE / MANUAL SELECTION
# ==========================================
st.subheader("📋 Sélection Manuelle")

# Build visual dataframe structure
display_df = pd.DataFrame([a.model_dump() for a in activities]).drop(columns=["raw", "streams"])

# Inject empty Selection column at the start if missing
if "selection" not in display_df.columns:
    display_df.insert(0, "selection", False)

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
    use_container_width=True,
)

# Extract dynamic selections
selected_indices = edited_df[edited_df["selection"]].index.tolist()
selected_activities = [activities[idx] for idx in selected_indices]

# Context-aware dynamic bottom action panel
if len(selected_activities) >= 2:
    st.write("")
    with st.container(border=True):
        st.markdown(f"### ⚡ Consolider les {len(selected_activities)} activités sélectionnées")
        
        col_input, col_action = st.columns([2, 1], vertical_alignment="bottom")
        with col_input:
            new_name = st.text_input(
                "Nom personnalisé pour l'activité finale :", 
                value=f"Fusion : {selected_activities[0].name}"
            )
        with col_action:
            if st.button("🚀 Ouvrir le pipeline de fusion", type="primary", use_container_width=True):
                render_merge_pipeline_dialog(service, selected_activities, new_name)