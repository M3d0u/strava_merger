"""Pydantic schema and domain entity representing a strava activity."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any

import gpxpy
import gpxpy.gpx
import requests
from pydantic import BaseModel, Field

from strava_utils.constants import (
    STRAVA_FIELD_DATA,
    STRAVA_FIELD_DISTANCE,
    STRAVA_FIELD_ID,
    STRAVA_FIELD_MOVING_TIME,
    STRAVA_FIELD_NAME,
    STRAVA_FIELD_START_DATE,
    STRAVA_FIELD_START_DATE_LOCAL,
    STRAVA_FIELD_START_LATLNG,
    STRAVA_FIELD_TYPE,
    STRAVA_STREAM_ALTITUDE,
    STRAVA_STREAM_HEARTRATE,
    STRAVA_STREAM_LATLNG,
    STRAVA_STREAM_TIME,
)


class StravaActivityDisplay(BaseModel):
    selection: bool = False
    id: int
    date: str
    name: str
    activity_type: str
    distance_km: float
    duration: str

    @classmethod
    def from_activity(cls, activity: StravaActivity) -> StravaActivityDisplay:
        """Create a display projection from a full StravaActivity."""
        return cls(
            selection=activity.selection,
            id=activity.id,
            date=activity.date,
            name=activity.name,
            activity_type=activity.activity_type,
            distance_km=activity.distance_km,
            duration=activity.duration,
        )


class StravaActivity(BaseModel):
    selection: bool = False
    id: int
    date: str
    name: str
    activity_type: str
    distance_km: float
    duration: str
    raw: dict[str, Any] = Field(default_factory=dict)
    streams: list[Any] | dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> StravaActivity:
        """Factory to validate, transform, and instantiate schema from API data.

        Args:
            payload (dict[str, Any]): Raw activity data from Strava API.
        Returns:
            StravaActivity: An instance of the StravaActivity class initialized with the validated and transformed data.
        """
        distance_meters = float(payload.get(STRAVA_FIELD_DISTANCE, 0.0))
        moving_seconds = int(payload.get(STRAVA_FIELD_MOVING_TIME, 0))

        parsed_date = datetime.fromisoformat(payload[STRAVA_FIELD_START_DATE].replace("Z", "+00:00"))
        date_str = parsed_date.strftime("%Y-%m-%d %H:%M")
        duration_str = str(timedelta(seconds=moving_seconds))

        return cls(
            id=int(payload[STRAVA_FIELD_ID]),
            date=date_str,
            name=str(payload[STRAVA_FIELD_NAME]),
            activity_type=str(payload[STRAVA_FIELD_TYPE]),
            distance_km=round(distance_meters / 1000, 2),
            duration=duration_str,
            raw=payload,
        )

    @staticmethod
    def _normalize_streams(streams: Any) -> dict[str, Any]:
        """Normalize streams to always be a dict of streams keyed by type.

        Args:
            streams (Any): The raw streams data from the Strava API, which can be a list or a dict.
        Returns:
            dict[str, Any]: A normalized dictionary of streams keyed by their type.
        """
        if not streams:
            return {}
        if isinstance(streams, dict):
            if STRAVA_FIELD_TYPE in streams and STRAVA_FIELD_DATA in streams:
                type_val = streams.get(STRAVA_FIELD_TYPE)
                if isinstance(type_val, str):
                    return {type_val: streams}
            return streams
        if isinstance(streams, list):
            normalized = {}
            for stream in streams:
                if isinstance(stream, dict) and STRAVA_FIELD_TYPE in stream:
                    type_val = stream.get(STRAVA_FIELD_TYPE)
                    if isinstance(type_val, str):
                        normalized[type_val] = stream
            return normalized
        return {}

    @staticmethod
    def merge_to_gpx(activities: list[StravaActivity]) -> str:
        """Pure CPU-Bound pipeline merging domain entities into a GPX XML.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances to merge.

        Returns:
            str: A string representation of the merged GPX XML.
        """
        gpx = gpxpy.gpx.GPX()

        # Register Garmin extension namespace properly at the root level to keeps the XML clean and fully compatible with Strava's parser
        gpx.nsmap["gpxtpx"] = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        sorted_acts = sorted(activities, key=lambda x: str(x.raw.get(STRAVA_FIELD_START_DATE, "")))

        for act in sorted_acts:
            streams_dict = StravaActivity._normalize_streams(act.streams)

            if STRAVA_STREAM_LATLNG not in streams_dict or STRAVA_STREAM_TIME not in streams_dict:
                raise ValueError(
                    f"L'activité '{act.name}' ne contient pas de données de tracé ou de temps (flux de données incomplets). "
                    "Impossible de procéder à la fusion."
                )

            start_dt = datetime.fromisoformat(str(act.raw.get(STRAVA_FIELD_START_DATE, "")).replace("Z", "+00:00"))
            latlng: list[list[float]] = streams_dict[STRAVA_STREAM_LATLNG][STRAVA_FIELD_DATA]
            time_offsets: list[int] = streams_dict[STRAVA_STREAM_TIME][STRAVA_FIELD_DATA]
            altitudes: list[float | None] = streams_dict.get(STRAVA_STREAM_ALTITUDE, {}).get(STRAVA_FIELD_DATA, [None] * len(latlng))
            hr: list[int | None] = streams_dict.get(STRAVA_STREAM_HEARTRATE, {}).get(STRAVA_FIELD_DATA, [None] * len(latlng))

            # Defensive check to avoid index mismatch errors
            num_points = min(len(latlng), len(time_offsets))
            if num_points == 0:
                raise ValueError(f"L'activité '{act.name}' ne contient aucun point de tracé valide.")

            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)

            for i in range(num_points):
                point_time = start_dt + timedelta(seconds=int(time_offsets[i]))
                point = gpxpy.gpx.GPXTrackPoint(
                    latitude=latlng[i][0],
                    longitude=latlng[i][1],
                    elevation=altitudes[i],
                    time=point_time,
                )

                # Use standard xml.etree.ElementTree instead of lxml
                heartrate_value = hr[i]
                if heartrate_value is not None:
                    ns_url = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
                    ext_element = ET.Element(f"{{{ns_url}}}TrackPointExtension")
                    hr_element = ET.Element(f"{{{ns_url}}}hr")
                    hr_element.text = str(int(heartrate_value))
                    ext_element.append(hr_element)
                    point.extensions.append(ext_element)

                gpx_segment.points.append(point)

        if gpx.get_track_points_no() == 0:
            raise ValueError("Le fichier GPX généré ne contient aucun point de tracé.")

        return str(gpx.to_xml())

    @staticmethod
    def detect_commutes(activities: list[StravaActivity]) -> list[list[StravaActivity]] | None:
        """Detect commute windows by grouping non-emoji ride activities by day.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.

        Returns:
            list[list[StravaActivity]] | None: Returns a list of StravaActivity
            instances occurring on the same day, or None if no groups are found.
        """
        by_date: dict[str, list[StravaActivity]] = {}

        for act in activities:
            # Skip non-ride activities (allow Ride and EBikeRide)
            if act.activity_type not in ("Ride", "EBikeRide"):
                continue

            # Skip activities starting with an emoji
            first_char = act.name[0] if act.name else ""
            if first_char and ord(first_char) > 10000:
                continue

            # Parse local date string
            local_date_str = str(act.raw.get(STRAVA_FIELD_START_DATE_LOCAL, ""))
            local_dt = datetime.fromisoformat(local_date_str.replace("Z", ""))
            date_str = local_dt.date().isoformat()

            if date_str not in by_date:
                by_date[date_str] = []

            by_date[date_str].append(act)

        # Filter for dates with at least 2 rides
        daily_groups = [acts for acts in by_date.values() if len(acts) >= 2]

        return daily_groups if daily_groups else None

    @staticmethod
    def detect_WeightTraining(activities: list[StravaActivity]) -> list[tuple[StravaActivity, str]]:
        """Detect unnamed or default weight training sessions.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.

        Returns:
            list[tuple[StravaActivity, str]]: Returns a list of tuples containing the
            weight training activities and the new names to assign.
        """
        weight_activities = [act for act in activities if act.activity_type == "WeightTraining"]
        if not weight_activities:
            return []

        sorted_activities = sorted(weight_activities, key=lambda x: str(x.raw.get(STRAVA_FIELD_START_DATE, "")))
        most_recent_activity = sorted_activities[-1]

        if "Push" not in most_recent_activity.name and "Pull" not in most_recent_activity.name:
            has_prev_pull = len(sorted_activities) > 1 and "Pull" in sorted_activities[-2].name
            new_name = "🏋️‍♀️ Push" if has_prev_pull else "🏋️‍♀️ Pull"
            return [(most_recent_activity, new_name)]

        return []

    @staticmethod
    def _fetch_weather_data(lat: float, lon: float, local_dt: datetime) -> tuple[float | None, int | None]:
        """Fetch temperature and weather code from Open-Meteo for the given coordinate and datetime.

        Args:
            lat (float): Latitude of the location.
            lon (float): Longitude of the location.
            local_dt (datetime): Local datetime of the activity.

        Returns:
            tuple[float | None, int | None]: Returns a tuple containing the temperature and weather code."""
        try:
            date_str = local_dt.strftime("%Y-%m-%d")
            local_hour = local_dt.hour
            days_diff = (datetime.now().date() - local_dt.date()).days

            # Use forecast endpoint for recent data, archive for older data
            if days_diff < 90:
                url = "https://api.open-meteo.com/v1/forecast"
            else:
                url = "https://archive-api.open-meteo.com/v1/archive"

            params = {
                "latitude": lat,
                "longitude": lon,
                "start_date": date_str,
                "end_date": date_str,
                "hourly": "temperature_2m,weather_code",
                "timezone": "auto",
            }

            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                hourly = data.get("hourly", {})
                temps = hourly.get("temperature_2m", [])
                codes = hourly.get("weather_code", [])
                if temps and codes:
                    # Match by local hour index (0-23)
                    idx = min(max(0, local_hour), len(temps) - 1)
                    temp_val = temps[idx]
                    code_val = codes[idx]
                    return float(temp_val) if temp_val is not None else None, int(code_val) if code_val is not None else None
        except Exception:
            pass
        return None, None

    @staticmethod
    def _get_weather_emoji_and_desc(code: int) -> tuple[str, str]:
        """Map WMO weather code to weather emoji and French description.

        Args:
            code (int): WMO weather code.

        Returns:
            tuple[str, str]: Returns a tuple containing the weather emoji and description.
        """
        mapping = {
            0: ("☀️", "Ciel dégagé"),
            1: ("🌤️", "Généralement dégagé"),
            2: ("⛅", "Partiellement nuageux"),
            3: ("☁️", "Couvert"),
            45: ("🌫️", "Brouillard"),
            48: ("🌫️", "Brouillard givrant"),
            51: ("🌧️", "Bruine légère"),
            53: ("🌧️", "Bruine modérée"),
            55: ("🌧️", "Bruine dense"),
            56: ("❄️", "Bruine verglaçante légère"),
            57: ("❄️", "Bruine verglaçante dense"),
            61: ("🌧️", "Pluie légère"),
            63: ("🌧️", "Pluie modérée"),
            65: ("🌧️", "Pluie forte"),
            66: ("❄️", "Pluie verglaçante légère"),
            67: ("❄️", "Pluie verglaçante forte"),
            71: ("❄️", "Neige légère"),
            73: ("❄️", "Neige modérée"),
            75: ("❄️", "Neige forte"),
            77: ("❄️", "Grains de neige"),
            80: ("🌦️", "Averses de pluie légères"),
            81: ("🌦️", "Averses de pluie modérées"),
            82: ("🌦️", "Averses de pluie violentes"),
            85: ("❄️", "Averses de neige légères"),
            86: ("❄️", "Averses de neige fortes"),
            95: ("⛈️", "Orage"),
            96: ("⛈️", "Orage avec grêle légère"),
            99: ("⛈️", "Orage avec grêle forte"),
        }
        return mapping.get(code, ("❓", "Météo inconnue"))

    @staticmethod
    def _get_activity_local_datetime(run_act: StravaActivity) -> datetime | None:
        """Extract local datetime of the activity from its raw payload.

        Args:
            run_act (StravaActivity): StravaActivity instance.

        Returns:
            datetime | None: Returns a datetime object representing the local datetime
        """
        start_date_local = run_act.raw.get(STRAVA_FIELD_START_DATE_LOCAL)
        if start_date_local:
            try:
                return datetime.fromisoformat(str(start_date_local).replace("Z", ""))
            except Exception:
                pass

        start_date_utc = run_act.raw.get(STRAVA_FIELD_START_DATE)
        if start_date_utc:
            try:
                return datetime.fromisoformat(str(start_date_utc).replace("Z", "+00:00"))
            except Exception:
                pass

        return None

    @staticmethod
    def _get_weather_description(run_act: StravaActivity) -> str:
        """Retrieve and format weather description for the activity.

        Args:
            run_act (StravaActivity): StravaActivity instance.

        Returns:
            str: Returns a string representing the weather description.
        """
        latlng = run_act.raw.get(STRAVA_FIELD_START_LATLNG)
        if latlng and isinstance(latlng, (list, tuple)) and len(latlng) == 2:
            lat, lon = float(latlng[0]), float(latlng[1])
            local_dt = StravaActivity._get_activity_local_datetime(run_act)
            if local_dt:
                temp, code = StravaActivity._fetch_weather_data(lat, lon, local_dt)
                if temp is not None and code is not None:
                    emoji, desc = StravaActivity._get_weather_emoji_and_desc(code)
                    return f"{emoji} {temp}°C, {desc}"
        return ""

    @staticmethod
    def _get_activity_emoji(activity_type: str) -> str:
        """Map activity type to a default emoji.

        Args:
            activity_type (str): The type of the activity.

        Returns:
            str: The corresponding emoji for the activity type.
        """
        emoji_map = {
            "Run": "🏃‍♂️",
            "Ride": "🚴‍♂️",
            "VirtualRide": "🚴‍♂️",
            "EBikeRide": "🚴‍♂️",
            "Walk": "🚶‍♂️",
            "Hike": "🥾",
            "Swim": "🏊‍♂️",
            "AlpineSki": "⛷️",
            "WeightTraining": "🏋️‍♀️",
        }
        return emoji_map.get(activity_type, "🏃‍♂️")

    @classmethod
    def detect_GeneralActivities(cls, activities: list[StravaActivity]) -> list[tuple[StravaActivity, str, str]]:
        """Detect activities and build suggested names with activity emojis + weather descriptions.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.

        Returns:
            list[tuple[StravaActivity, str, str]]: Tuples containing (activity, suggested_name, suggested_description)
        """
        suggestions: list[tuple[StravaActivity, str, str]] = []

        # Find any activities detected as commutes to exclude them (hierarchical logic)
        commute_groups = cls.detect_commutes(activities) or []
        commute_ids = {act.id for group in commute_groups for act in group}

        for act in activities:
            # Skip already handle activites
            if act.activity_type == "WeightTraining" or act.id in commute_ids:
                continue

            # Check if name already starts with an emoji to prevent duplicate renaming suggestions
            first_char = act.name[0] if act.name else ""
            if ord(first_char) > 10000:
                continue

            emoji = cls._get_activity_emoji(act.activity_type)
            suggested_name = f"{emoji} {act.name}"
            suggested_desc = cls._get_weather_description(act)

            suggestions.append((act, suggested_name, suggested_desc))

        return suggestions

    @classmethod
    def generate_merge_description(cls, activities: list[StravaActivity]) -> str | None:
        """Generate a unified weather description for a list of activities.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.

        Returns:
            str | None: Returns a string representing the weather description, or None.
        """
        sorted_acts = sorted(activities, key=lambda x: str(x.raw.get(STRAVA_FIELD_START_DATE, "")))
        meteo_lines = []
        act_nbr = 1
        for act in sorted_acts:
            weather = cls._get_weather_description(act)
            if weather:
                prefix = f"Départ {act_nbr}"
                act_nbr += 1
                meteo_lines.append(f"{prefix} : {weather}")

        return "\n".join(meteo_lines) if meteo_lines else None
