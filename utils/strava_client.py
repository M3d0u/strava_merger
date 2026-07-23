"""Strava api wrapper"""

from typing import Any, cast

import requests
import streamlit as st


class StravaAPIClient:
    def __init__(self) -> None:
        self.client_id: str = st.secrets["STRAVA_CLIENT_ID"]
        self.client_secret: str = st.secrets["STRAVA_CLIENT_SECRET"]
        self.refresh_token: str = st.secrets["STRAVA_REFRESH_TOKEN"]
        self._access_token: str | None = None

    @property
    def access_token(self) -> str:
        """Récupère ou rafraîchit le token d'accès via le cache Streamlit."""
        if not self._access_token:
            self._access_token = self._refresh_access_token()
        return cast(str, self._access_token)

    @st.cache_data(ttl=3000)  # type: ignore[misc]
    def _refresh_access_token(_self) -> str | None:  # _self évite que Streamlit ne cache l'instance
        """Rotate token OAuth"""
        payload = {
            "client_id": _self.client_id,
            "client_secret": _self.client_secret,
            "refresh_token": _self.refresh_token,
            "grant_type": "refresh_token",
        }
        res = requests.post("https://www.strava.com/oauth/token", data=payload)
        if res.status_code == 200:
            token: str = res.json()["access_token"]
            return token
        return None

    @st.cache_data(ttl=600)  # type: ignore[misc]
    def fetch_streams(_self, activity_id: int) -> Any:
        """Retrieve activity streams"""
        headers = {"Authorization": f"Bearer {_self.access_token}"}
        url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
        params = {"keys": "latlng,time,altitude,heartrate", "key_by_type": "true"}
        res = requests.get(url, headers=headers, params=params)
        return res.json() if res.status_code == 200 else {}

    def fetch_activities(self, limit: int = 12) -> Any:
        """Retrieve recent activities"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        res = requests.get(
            f"https://www.strava.com/api/v3/athlete/activities?per_page={limit}",
            headers=headers,
        )
        return res.json() if res.status_code == 200 else []

    def upload_gpx(self, gpx_xml: str, name: str) -> dict[str, Any] | None:
        """Upload GPX file to Strava"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        files = {"file": ("merged.gpx", gpx_xml, "application/gpx+xml")}
        data = {"name": name, "data_type": "gpx"}
        res = requests.post("https://www.strava.com/api/v3/uploads", headers=headers, data=data, files=files)
        try:
            return cast(dict[str, Any], res.json())
        except Exception:
            return None

    def link_to_delete_activity(self, activity_id: int) -> str:
        """Create a direct link to delete an activity."""
        return f"https://www.strava.com/activities/{activity_id}"

    def rename_activity(self, activity_id: int, new_name: str, description: str | None = None) -> Any:
        """Rename an activity."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data: dict[str, Any] = {"name": new_name}
        if description is not None:
            data["description"] = description
        res = requests.put(f"https://www.strava.com/api/v3/activities/{activity_id}", headers=headers, data=data)
        return res.json() if res.status_code in [200, 201] else None

    def check_upload_status(self, upload_id: int) -> dict[str, Any] | None:
        """Check the background processing status of an uploaded activity."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
        res = requests.get(url, headers=headers)
        try:
            return cast(dict[str, Any], res.json())
        except Exception:
            return None

    def mute_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Mute the activity (hide it from home and club feeds)."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        data = {"hide_from_home": "true"}
        res = requests.put(f"https://www.strava.com/api/v3/activities/{activity_id}", headers=headers, data=data)
        return res.json() if res.status_code in [200, 201] else None
