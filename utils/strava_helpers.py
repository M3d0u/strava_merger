"""Helpers functions to interact with Strava API"""

from typing import Any, Dict, List, Optional

import requests
import streamlit as st


@st.cache_data(ttl=3000)  # type: ignore[misc]
def get_access_token() -> str:
    """Effectue la rotation du token via le Refresh Token des secrets."""
    payload = {
        "client_id": st.secrets["STRAVA_CLIENT_ID"],
        "client_secret": st.secrets["STRAVA_CLIENT_SECRET"],
        "refresh_token": st.secrets["STRAVA_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
        "scope": "activity:read_all,activity:write"
    }
    res = requests.post("https://www.strava.com/oauth/token", data=payload)
    if res.status_code == 200:
        token: str = res.json()["access_token"]
        return token
    else:
        st.error(f"Erreur d'authentification Strava : {res.text}")
        st.stop()
        raise RuntimeError("Streamlit execution stopped")


@st.cache_data(ttl=120)  # type: ignore[misc]
def fetch_recent_activities(token: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Récupère les métadonnées des dernières activités de l'athlète."""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(
        f"https://www.strava.com/api/v3/athlete/activities?per_page={limit}",
        headers=headers,
    )
    if res.status_code == 200:
        activities: List[Dict[str, Any]] = res.json()
        return activities
    return []


def fetch_activity_streams(token: str, activity_id: int) -> Dict[str, Any]:
    """Récupère les streams de données géospatiales et physiologiques."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {"keys": "latlng,time,altitude,heartrate", "key_by_type": "true"}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200:
        streams: Dict[str, Any] = res.json()
        return streams
    return {}


def upload_gpx(token: str, gpx_xml_data: str, name: str) -> Optional[Dict[str, Any]]:
    """Téléverse le payload XML GPX sur Strava."""
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("merged.gpx", gpx_xml_data, "application/gpx+xml")}
    data = {"name": name, "data_type": "gpx"}
    res = requests.post(
        "https://www.strava.com/api/v3/uploads",
        headers=headers,
        data=data,
        files=files,
    )
    print(res.status_code, res.text)
    if res.status_code in [200, 201]:
        response: Dict[str, Any] = res.json()
        return response
    return None


def delete_activity(token: str, activity_id: int) -> bool:
    """Supprime une activité spécifique par son ID."""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.delete(f"https://www.strava.com/api/v3/activities/{activity_id}", headers=headers)
    print(f"Delete Activity {activity_id} - Status Code: {res.status_code}")
    return res.status_code == 204
