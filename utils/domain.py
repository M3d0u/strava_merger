"""Pydantic schema and domain entity representing a strava activity."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any

import gpxpy
import gpxpy.gpx
from pydantic import BaseModel, Field


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
        distance_meters = float(payload.get("distance", 0.0))
        moving_seconds = int(payload.get("moving_time", 0))

        parsed_date = datetime.fromisoformat(payload["start_date"].replace("Z", "+00:00"))
        date_str = parsed_date.strftime("%Y-%m-%d %H:%M")
        duration_str = str(timedelta(seconds=moving_seconds))

        return cls(
            id=int(payload["id"]),
            date=date_str,
            name=str(payload["name"]),
            activity_type=str(payload["type"]),
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
            if "type" in streams and "data" in streams:
                type_val = streams.get("type")
                if isinstance(type_val, str):
                    return {type_val: streams}
            return streams
        if isinstance(streams, list):
            normalized = {}
            for stream in streams:
                if isinstance(stream, dict) and "type" in stream:
                    type_val = stream.get("type")
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

        sorted_acts = sorted(activities, key=lambda x: str(x.raw.get("start_date", "")))

        for act in sorted_acts:
            streams_dict = StravaActivity._normalize_streams(act.streams)

            if "latlng" not in streams_dict or "time" not in streams_dict:
                raise ValueError(
                    f"L'activité '{act.name}' ne contient pas de données de tracé ou de temps (flux de données incomplets). "
                    "Impossible de procéder à la fusion."
                )

            start_dt = datetime.fromisoformat(str(act.raw.get("start_date", "")).replace("Z", "+00:00"))
            latlng: list[list[float]] = streams_dict["latlng"]["data"]
            time_offsets: list[int] = streams_dict["time"]["data"]
            altitudes: list[float | None] = streams_dict.get("altitude", {}).get("data", [None] * len(latlng))
            hr: list[int | None] = streams_dict.get("heartrate", {}).get("data", [None] * len(latlng))

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
        """Detect morning and evening commute windows.
        
        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.
            
        Returns:
            list[list[StravaActivity]] | None: Returns a list of pairs of StravaActivity 
            instances representing morning and evening commutes, or None if no pairs are found.
        """
        by_date: dict[str, dict[str, StravaActivity | None]] = {}
        m_start, m_end = dt_time(7, 50), dt_time(8, 50)
        e_start, e_end = dt_time(17, 30), dt_time(19, 0)

        for act in activities:
            if act.activity_type != "Ride":
                continue

            local_date_str = str(act.raw.get("start_date_local", ""))
            local_dt = datetime.fromisoformat(local_date_str.replace("Z", ""))
            date_str = local_dt.date().isoformat()
            act_time = local_dt.time()

            if date_str not in by_date:
                by_date[date_str] = {"morning": None, "evening": None}

            if m_start <= act_time <= m_end:
                by_date[date_str]["morning"] = act
            elif e_start <= act_time <= e_end:
                by_date[date_str]["evening"] = act

        pairs: list[list[StravaActivity]] = []
        for pair in by_date.values():
            if pair["morning"] and pair["evening"]:
                pairs.append([pair["morning"], pair["evening"]])

        return pairs if pairs else None

    @staticmethod
    def detect_WeightTraining(activities: list[StravaActivity]) -> tuple[StravaActivity, str] | None:
        """Detect unnamed or default weight training sessions.
        
        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.
            
        Returns:
            tuple[StravaActivity, str] | None: Returns a tuple containing the most recent
            weight training activity and the new name to assign, or None if no renaming is needed."""
        weight_activities = [act for act in activities if act.activity_type == "WeightTraining"]
        if not weight_activities:
            return None

        sorted_activities = sorted(weight_activities, key=lambda x: str(x.raw.get("start_date", "")))
        most_recent_activity = sorted_activities[-1]

        if "Push" not in most_recent_activity.name and "Pull" not in most_recent_activity.name:
            has_prev_pull = len(sorted_activities) > 1 and "Pull" in sorted_activities[-2].name
            new_name = "🏋️‍♀️ Push" if has_prev_pull else "🏋️‍♀️ Pull"
            return most_recent_activity, new_name

        return None
    
    @staticmethod
    def detect_Run(activities: list[StravaActivity]) -> tuple[StravaActivity, str, str] | None:
        """Detect running activities.
        
        Args:
            activities (list[StravaActivity]): List of StravaActivity instances.
            
        Returns:
            tuple[StravaActivity, str, str] | None: Returns a tuple containing the running activity, 
            its future name and meteo description, or None if no running activities are found.
        """
        run_activities = [act for act in activities if act.activity_type == "Run"]
        for run_act in run_activities:
            if "🏃‍♂️" not in run_act.name:
                future_name = f"🏃‍♂️ {run_act.name}"
                meteo_desc = "TO DEFINE"  # Placeholder for future meteo description logic
                return run_act, future_name, meteo_desc
        return None
