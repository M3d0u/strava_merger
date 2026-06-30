"""Application Service coordinating domain models and infrastructure clients."""

from typing import List
from utils.domain import StravaActivity
from utils.strava_client import StravaAPIClient

class StravaService:
    def __init__(self) -> None:
        self.client = StravaAPIClient()

    def get_recent_activities(self, limit: int = 12) -> List[StravaActivity]:
        """Fetch and convert raw API entries into domain entities."""
        raw_data = self.client.fetch_activities(limit=limit)
        if not raw_data:
            return []
        return [StravaActivity.from_api(a) for a in raw_data]

    def get_delete_url(self, activity: StravaActivity) -> str:
        """Get the direct link to delete an activity on Strava."""
        return self.client.link_to_delete_activity(activity.id)

    def rename_activity(self, activity_id: int, new_name: str) -> None:
        """Rename an individual activity."""
        self.client.rename_activity(activity_id, new_name)

    def merge_and_upload(self, activities: List[StravaActivity], target_name: str) -> bool:
        """Coordinate loading missing streams, compiling GPX, and uploading."""
        for act in activities:
            if not act.streams:
                act.streams = self.client.fetch_streams(act.id)

        # Domain performs the pure processing work
        gpx_xml = StravaActivity.merge_to_gpx(activities)
        
        upload_res = self.client.upload_gpx(gpx_xml, target_name)
        return upload_res is not None and "id" in upload_res
