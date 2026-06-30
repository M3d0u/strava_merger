"""Pydantic schema and domain entity representing a strava activity."""

from datetime import datetime, time as dt_time, timedelta
from typing import Any, Dict, List, Optional
from lxml import etree as mod_etree
from pydantic import BaseModel, Field
import gpxpy
import gpxpy.gpx
from utils.strava_client import StravaAPIClient


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
        """Factory pour valider, transformer et instancier le schéma depuis l'API."""
        distance_meters = float(payload.get("distance", 0.0))
        moving_seconds = int(payload.get("moving_time", 0))

        # Parsing et formatage des dates/durées pour l'UI
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

    def load_streams(self, client: StravaAPIClient) -> None:
        """Injecte les streams géospatiaux requis pour les calculs géographiques."""
        self.streams = client.fetch_streams(self.id)

    def delete(self, client: StravaAPIClient) -> str:
        """Demande la purge réseau de cette activité spécifique."""
        return client.link_to_delete_activity(self.id)

    @staticmethod
    def merge_to_gpx(client: StravaAPIClient, activities: List["StravaActivity"]) -> str:
        """Pipeline (CPU-Bound) de fusion de n entités Pydantic vers un XML GPX."""
        gpx = gpxpy.gpx.GPX()
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        # Tri chronologique basé sur le timestamp de l'API contenu dans .raw
        sorted_acts = sorted(activities, key=lambda x: str(x.raw.get("start_date", "")))

        for act in sorted_acts:
            gpx_segment = gpxpy.gpx.GPXTrackSegment()
            gpx_track.segments.append(gpx_segment)

            if not act.streams:
                act.load_streams(client)

            if "latlng" not in act.streams:
                continue

            start_dt = datetime.fromisoformat(
                str(act.raw.get("start_date", "")).replace("Z", "+00:00")
            )
            latlng: List[List[float]] = act.streams["latlng"]["data"]
            time_offsets: List[int] = act.streams["time"]["data"]
            altitudes: List[Optional[float]] = act.streams.get("altitude", {}).get(
                "data", [None] * len(latlng)
            )
            hr: List[Optional[int]] = act.streams.get("heartrate", {}).get(
                "data", [None] * len(latlng)
            )

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
                    ext_element = mod_etree.Element(f"{{{ns_url}}}TrackPointExtension")
                    hr_element = mod_etree.Element(f"{{{ns_url}}}hr")
                    hr_element.text = str(int(hr[i]))  # type: ignore
                    ext_element.append(hr_element)
                    point.extensions.append(ext_element)

                gpx_segment.points.append(point)

        return str(gpx.to_xml())

    @staticmethod
    def detect_commutes(activities: List["StravaActivity"]) -> List[List["StravaActivity"]]:
        """Analyse le dataset d'entités pour identifier les fenêtres de Vélotaf."""
        by_date: Dict[str, Dict[str, Optional["StravaActivity"]]] = {}
        m_start, m_end = dt_time(7, 50), dt_time(8, 50)
        e_start, e_end = dt_time(17, 30), dt_time(19, 0)

        for act in activities:
            if act.activity_type != "Ride":
                continue

            # Lecture sécurisée de la date locale dans le payload stocké
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
        return pairs
