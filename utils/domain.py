"""Pydantic schema and domain entity representing a strava activity."""

from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any, Dict, List

import gpxpy
import gpxpy.gpx
from lxml import etree as mod_etree
from pydantic import BaseModel, Field


class StravaActivity(BaseModel):
    selection: bool = False
    id: int
    date: str
    name: str
    activity_type: str
    distance_km: float
    duration: str
    raw: Dict[str, Any] = Field(default_factory=dict)
    streams: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "StravaActivity":
        """Factory to validate, transform, and instantiate schema from API data."""
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
    def merge_to_gpx(activities: List["StravaActivity"]) -> str:
        """Pure CPU-Bound pipeline merging domain entities into a GPX XML."""
        gpx = gpxpy.gpx.GPX()
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        sorted_acts = sorted(activities, key=lambda x: str(x.raw.get("start_date", "")))

        for act in sorted_acts:
            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)

            if "latlng" not in act.streams:
                continue

            start_dt = datetime.fromisoformat(str(act.raw.get("start_date", "")).replace("Z", "+00:00"))
            latlng: List[List[float]] = act.streams["latlng"]["data"]
            time_offsets: List[int] = act.streams["time"]["data"]
            altitudes: List[float | None] = act.streams.get("altitude", {}).get("data", [None] * len(latlng))
            hr: List[int | None] = act.streams.get("heartrate", {}).get("data", [None] * len(latlng))

            for i in range(len(latlng)):
                point_time = start_dt + timedelta(seconds=int(time_offsets[i]))
                point = gpxpy.gpx.GPXTrackPoint(
                    latitude=latlng[i][0],
                    longitude=latlng[i][1],
                    elevation=altitudes[i],
                    time=point_time,
                )

                heartrate_value = hr[i]
                if heartrate_value is not None:
                    ns_url = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
                    ext_element = mod_etree.Element(f"{{{ns_url}}}TrackPointExtension")
                    hr_element = mod_etree.Element(f"{{{ns_url}}}hr")
                    hr_element.text = str(int(heartrate_value))
                    ext_element.append(hr_element)
                    point.extensions.append(ext_element)

                gpx_segment.points.append(point)

        return str(gpx.to_xml())

    @staticmethod
    def detect_commutes(activities: List["StravaActivity"]) -> List[List["StravaActivity"]] | None:
        """Detect morning and evening commute windows."""
        by_date: Dict[str, Dict[str, "StravaActivity" | None]] = {}
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

        pairs: List[List["StravaActivity"]] = []
        for pair in by_date.values():
            if pair["morning"] and pair["evening"]:
                pairs.append([pair["morning"], pair["evening"]])

        return pairs if pairs else None  # FIXED: Bug fix here (previously returned None)

    @staticmethod
    def detect_WeightTraining(activities: List["StravaActivity"]) -> tuple["StravaActivity", str] | None:
        """Detect unnamed or default weight training sessions."""
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
