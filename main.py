"""Streamlite of the application"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from utils.merge_helpers import (
    detect_commute_pairs,
    merge_activities_to_gpx,
)
from utils.strava_helpers import (
    delete_activity,
    fetch_recent_activities,
    get_access_token,
    upload_gpx,
)

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
st.write("Sélectionnez les activités à fusionner.")

token = get_access_token()
raw_activities = fetch_recent_activities(token, limit=12)

if not raw_activities:
    st.error("Impossible de récupérer les activités. Vérifiez vos configurations de tokens.")
    st.stop()

# Build du catalogue
data_records: List[Dict[str, Any]] = []
for a in raw_activities:
    data_records.append(
        {
            "Sélection": False,
            "ID": a["id"],
            "Date": datetime.fromisoformat(a["start_date"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M"),
            "Nom": a["name"],
            "Type": a["type"],
            "Distance (km)": round(a["distance"] / 1000, 2),
            "Durée": str(timedelta(seconds=a["moving_time"])),
            "_raw": a,
        }
    )

df = pd.DataFrame(data_records)

# ==========================================
# AUTOMATIC COMMUTE MERGE ACTION BLOC
# ==========================================
commute_pairs = detect_commute_pairs(raw_activities)

if commute_pairs:
    st.info(f"💡 **Mode Automatique** : {len(commute_pairs)} paire(s) de Vélotaf (Matin/Soir) détectée(s) !")

    for idx, pair in enumerate(commute_pairs):
        date_label = datetime.fromisoformat(pair[0]["start_date_local"].replace("Z", "")).strftime("%d/%m/%Y")
        col_info, col_btn = st.columns([3, 1])

        with col_info:
            st.markdown(f"🚲 **Commute du {date_label}** ({round(pair[0]['distance']/1000, 1)}km + {round(pair[1]['distance']/1000, 1)}km)")

        with col_btn:
            if st.button(f"⚡ Fusionner le {date_label}", key=f"auto_merge_{idx}"):
                with st.spinner(f"Consolidation du Vélotaf du {date_label}..."):
                    auto_name = f"💼 Vélotaf - {date_label}"

                    # Run Pipeline
                    gpx_xml = merge_activities_to_gpx(token, pair)
                    upload_res = upload_gpx(token, gpx_xml, auto_name)

                    if upload_res and "id" in upload_res:
                        st.toast(f"Vélotaf du {date_label} téléversé !", icon="✅")

                        # Nettoyage automatique des 2 activités sources
                        for act in pair:
                            delete_activity(token, int(act["id"]))

                        st.balloons()
                        st.success(f"Fait ! Commute du {date_label} traité.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Échec de l'upload automatique.")
    st.divider()

# ==========================================
# RENDER MANUAL TABLE
# ==========================================

edited_df = st.data_editor(
    df.drop(columns=["_raw"]),
    column_config={"Sélection": st.column_config.CheckboxColumn(required=True)},
    disabled=["ID", "Date", "Nom", "Type", "Distance (km)", "Durée"],
    hide_index=True,
)

# Extraction des payloads originaux basés sur la sélection utilisateur
selected_indices: List[int] = edited_df[edited_df["Sélection"] == True].index.tolist()  # noqa: E712
selected_activities: List[Dict[str, Any]] = [data_records[idx]["_raw"] for idx in selected_indices]

st.divider()

if len(selected_activities) >= 2:
    st.success(f"⚡ {len(selected_activities)} activités prêtes à être consolidées.")

    default_name = f"Fusion : {selected_activities[0]['name']}"
    new_activity_name = st.text_input("Nom de la nouvelle activité consolidée :", value=default_name)

    col1, _ = st.columns(2)
    with col1:
        clean_old = st.checkbox("Supprimer automatiquement les activités d'origine après fusion", value=True)

    if st.button("🚀 Exécuter le pipeline de fusion", type="primary"):
        with st.spinner("Processing des streams et génération du GPX..."):
            gpx_xml = merge_activities_to_gpx(token, selected_activities)
            upload_res = upload_gpx(token, gpx_xml, new_activity_name)

            if upload_res and "id" in upload_res:
                st.toast("Fichier GPX téléversé avec succès !", icon="✅")

                if clean_old:
                    with st.spinner("Nettoyage des activités sources..."):
                        for act in selected_activities:
                            success = delete_activity(token, int(act["id"]))
                            if success:
                                st.caption(f"Activité {act['id']} supprimée.")
                            else:
                                st.warning(f"Échec de la suppression pour l'activité {act['id']}.")

                st.balloons()
                st.success("Opération terminée avec succès ! Vous pouvez rafraîchir l'application.")
                st.cache_data.clear()
            else:
                st.error(f"Erreur lors de l'upload chez Strava : {upload_res}")
else:
    st.info("Veuillez cocher au moins 2 activités dans le tableau ci-dessus pour activer la fusion.")
