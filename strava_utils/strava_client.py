"""Strava api wrapper"""

from typing import Any, cast

import requests
import streamlit as st

from strava_utils.constants import (
    STRAVA_FIELD_DESCRIPTION,
    STRAVA_FIELD_HIDE_FROM_HOME,
    STRAVA_FIELD_NAME,
    STRAVA_SUFFIX_ACTIVITY,
    STRAVA_SUFFIX_ATHLETE,
    STRAVA_SUFFIX_UPLOAD,
    STRAVA_URL,
)


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

    def _build_header(self):
        """Build header for API requests"""
        return {"Authorization": f"Bearer {self.access_token}"}

    @st.cache_data(ttl=3000)  # type: ignore[misc]
    def _refresh_access_token(_self) -> str | None:  # _self évite que Streamlit ne cache l'instance
        """Rotate token OAuth"""
        payload = {
            "client_id": _self.client_id,
            "client_secret": _self.client_secret,
            "refresh_token": _self.refresh_token,
            "grant_type": "refresh_token",
        }
        res = requests.post(f"{STRAVA_URL}/oauth/token", data=payload)
        if res.status_code == 200:
            token: str = res.json()["access_token"]
            return token
        return None

    @st.cache_data(ttl=600)  # type: ignore[misc]
    def fetch_streams(_self, activity_id: int) -> Any:
        """Retrieve activity streams"""
        url = f"{STRAVA_URL}/{STRAVA_SUFFIX_ACTIVITY}{activity_id}/streams"
        params = {"keys": "latlng,time,altitude,heartrate", "key_by_type": "true"}
        res = requests.get(url, headers=_self._build_header(), params=params)
        return res.json() if res.status_code == 200 else {}

    def fetch_activities(self, limit: int = 12) -> Any:
        """Retrieve recent activities"""
        res = requests.get(
            f"{STRAVA_URL}/{STRAVA_SUFFIX_ATHLETE}/activities?per_page={limit}",
            headers=self._build_header(),
        )
        return res.json() if res.status_code == 200 else []

    def fetch_athlete(self) -> dict[str, Any]:
        """Retrieve the complete athlete profile (including bikes and shoes)."""
        res = requests.get(f"{STRAVA_URL}/{STRAVA_SUFFIX_ATHLETE}", headers=self._build_header())
        return res.json() if res.status_code == 200 else {}

    def upload_gpx(self, gpx_xml: str, name: str, description: str | None = None) -> dict[str, Any] | None:
        """Upload GPX file to Strava"""
        files = {"file": ("merged.gpx", gpx_xml, "application/gpx+xml")}
        data: dict[str, Any] = {STRAVA_FIELD_NAME: name, "data_type": "gpx"}
        if description is not None:
            data[STRAVA_FIELD_DESCRIPTION] = description
        res = requests.post(f"{STRAVA_URL}/{STRAVA_SUFFIX_UPLOAD}", headers=self._build_header(), data=data, files=files)
        try:
            return cast(dict[str, Any], res.json())
        except Exception:
            return None

    def link_to_delete_activity(self, activity_id: int) -> str:
        """Create a direct link to delete an activity."""
        return f"{STRAVA_URL}/activities/{activity_id}"

    def rename_activity(self, activity_id: int, new_name: str, description: str | None = None) -> Any:
        """Rename an activity."""
        data: dict[str, Any] = {STRAVA_FIELD_NAME: new_name}
        if description is not None:
            data[STRAVA_FIELD_DESCRIPTION] = description
        res = requests.put(f"{STRAVA_URL}/{STRAVA_SUFFIX_ACTIVITY}/{activity_id}", headers=self._build_header(), data=data)
        return res.json() if res.status_code in [200, 201] else None

    def check_upload_status(self, upload_id: int) -> dict[str, Any] | None:
        """Check the background processing status of an uploaded activity."""
        url = f"{STRAVA_URL}/{STRAVA_SUFFIX_UPLOAD}/{upload_id}"
        res = requests.get(url, headers=self._build_header())
        try:
            return cast(dict[str, Any], res.json())
        except Exception:
            return None

    def mute_activity(self, activity_id: int) -> dict[str, Any] | None:
        """Mute the activity (hide it from home and club feeds)."""
        data = {STRAVA_FIELD_HIDE_FROM_HOME: "true"}
        res = requests.put(f"{STRAVA_URL}/{STRAVA_SUFFIX_ACTIVITY}/{activity_id}", headers=self._build_header(), data=data)
        return res.json() if res.status_code in [200, 201] else None
