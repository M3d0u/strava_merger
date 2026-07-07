"""Application Service coordinating domain models and infrastructure clients."""

import time
from typing import Any

from utils.domain import StravaActivity
from utils.strava_client import StravaAPIClient


class StravaService:
    def __init__(self) -> None:
        self.client = StravaAPIClient()

    def get_recent_activities(self, limit: int = 12) -> list[StravaActivity]:
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

    def _format_error(self, response_dict: dict[str, Any] | None) -> str:
        if not response_dict:
            return "Aucune réponse de l'API Strava."

        if "error" in response_dict and response_dict["error"]:
            return str(response_dict["error"])

        message = str(response_dict.get("message", "Erreur inconnue"))
        errors = response_dict.get("errors")
        if errors and isinstance(errors, list):
            err_details = []
            for err in errors:
                if isinstance(err, dict):
                    field = err.get("field", "")
                    code = err.get("code", "")
                    resource = err.get("resource", "")
                    err_details.append(f"{resource} {field}: {code}")
                else:
                    err_details.append(str(err))
            return f"{message} ({', '.join(err_details)})"
        return message

    def merge_and_upload(self, activities: list[StravaActivity], target_name: str) -> tuple[bool, str | None]:
        """Coordinate loading missing streams, compiling GPX, and uploading."""
        for act in activities:
            if not act.streams:
                act.streams = self.client.fetch_streams(act.id)

        gpx_xml = StravaActivity.merge_to_gpx(activities)
        upload_res = self.client.upload_gpx(gpx_xml, target_name)

        if upload_res and "id" in upload_res:
            upload_id = upload_res["id"]
            max_attempts = 15
            delay_seconds = 2
            error_msg = None
            for _ in range(max_attempts):
                time.sleep(delay_seconds)
                status = self.client.check_upload_status(upload_id)
                if not status:
                    continue
                if status.get("error"):
                    error_msg = status.get("error")
                    break
                activity_id = status.get("activity_id")
                if activity_id:
                    self.client.mute_activity(activity_id)
                    return True, None

            if error_msg:
                return False, error_msg
            return False, "Le traitement de l'activité sur Strava a expiré sans confirmation."

        error_msg = self._format_error(upload_res)
        return False, f"La requête d'envoi a été rejetée par Strava : {error_msg}"
