"""Schemas for strava activities."""

from pydantic import BaseModel
from typing import Any



class StravaActivity(BaseModel):
    """Defines a strava activity schema."""
    selection: bool = False
    id: int
    date: str
    name: str
    activity_type: str 
    distance_km: float 
    duration: str
    raw: dict[str, Any]
