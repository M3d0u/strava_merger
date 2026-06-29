"""Helper function to merge activities"""

from datetime import datetime, timedelta
from datetime import time as dt_time
from typing import Any, Dict, List, Optional

import gpxpy
import gpxpy.gpx
import streamlit as st
from lxml import etree as mod_etree

from utils.strava_helpers import fetch_activity_streams


def detect_commute_pairs(activities: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Analyse activites to detect commute pairs."""
    # Groupement temporaire par date (YYYY-MM-DD)
    by_date: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}

    # Définition des fenêtres de tir
    morning_start = dt_time(7, 50)
    morning_end = dt_time(8, 50)
    evening_start = dt_time(17, 30)
    evening_end = dt_time(19, 00)

    for act in activities:
        if act.get("type") != "Ride":
            continue

        local_dt = datetime.fromisoformat(act["start_date_local"].replace("Z", ""))
        date_str = local_dt.date().isoformat()
        act_time = local_dt.time()

        if date_str not in by_date:
            by_date[date_str] = {"morning": None, "evening": None}

        if morning_start <= act_time <= morning_end:
            by_date[date_str]["morning"] = act
        elif evening_start <= act_time <= evening_end:
            by_date[date_str]["evening"] = act

    commute_groups: List[List[Dict[str, Any]]] = []
    for _, pair in by_date.items():
        if pair["morning"] and pair["evening"]:
            commute_groups.append([pair["morning"], pair["evening"]])

    return commute_groups


def merge_activities_to_gpx(token: str, selected_activities: List[Dict[str, Any]]) -> str:
    """Transform and merge multiple strava activites into a single gpx xml file."""
    gpx = gpxpy.gpx.GPX()
    gpx_track = gpxpy.gpx.GPXTrack()
    gpx.tracks.append(gpx_track)

    # Tri chronologique des activités sources
    sorted_activities = sorted(selected_activities, key=lambda x: str(x["start_date"]))

    for act in sorted_activities:
        # Un segment distinct par trajet pour éviter la ligne droite fantôme
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)

        start_dt = datetime.fromisoformat(act["start_date"].replace("Z", "+00:00"))
        streams = fetch_activity_streams(token, int(act["id"]))

        if "latlng" not in streams:
            st.warning(f"Pas de données GPS trouvées pour l'activité {act['id']}.")
            continue

        latlng: List[List[float]] = streams["latlng"]["data"]
        time_offsets: List[int] = streams["time"]["data"]
        altitudes: List[Optional[float]] = streams.get("altitude", {}).get("data", [None] * len(latlng))
        hr: List[Optional[int]] = streams.get("heartrate", {}).get("data", [None] * len(latlng))

        for i in range(len(latlng)):
            point_time = start_dt + timedelta(seconds=int(time_offsets[i]))

            point = gpxpy.gpx.GPXTrackPoint(
                latitude=latlng[i][0],
                longitude=latlng[i][1],
                elevation=altitudes[i],
                time=point_time,
            )

            if hr[i] is not None:
                ns_url = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
                gpx_extension_element = mod_etree.Element(f"{{{ns_url}}}TrackPointExtension")
                hr_element = mod_etree.Element(f"{{{ns_url}}}hr")
                hr_element.text = str(int(hr[i]))  # type: ignore
                gpx_extension_element.append(hr_element)
                point.extensions.append(gpx_extension_element)

            gpx_segment.points.append(point)

    gpx_str: str = gpx.to_xml()
    return gpx_str
