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
        """Extract and format error messages from Strava API responses."""
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

    def _poll_upload_status(self, upload_id: int) -> tuple[bool, str | None, bool]:
        """
        Polls Strava until processing is complete or fails.
        Returns: (is_success, error_message, should_retry_due_to_duplicate)
        """
        max_polling_attempts = 10
        polling_delay = 2

        for _ in range(max_polling_attempts):
            time.sleep(polling_delay)
            status = self.client.check_upload_status(upload_id)

            if not status:
                continue

            if status.get("error"):
                error_msg = str(status.get("error"))
                is_duplicate = "duplicate of" in error_msg.lower()
                return False, f"Erreur de traitement Strava : {error_msg}", is_duplicate

            activity_id = status.get("activity_id")
            if activity_id:
                self.client.mute_activity(activity_id)
                return True, None, False

        return False, "Le traitement de l'activité sur Strava a expiré sans confirmation.", False

    def merge_and_upload(self, activities: list[StravaActivity], target_name: str) -> tuple[bool, str | None]:
        """Coordinate loading missing streams, compiling GPX, and uploading."""
        for act in activities:
            if not act.streams:
                act.streams = self.client.fetch_streams(act.id)

        try:
            gpx_xml = StravaActivity.merge_to_gpx(activities)
        except ValueError as e:
            return False, str(e)

        max_upload_attempts = 3
        base_retry_delay = 5

        for attempt in range(max_upload_attempts):
            upload_res = self.client.upload_gpx(gpx_xml, target_name)

            # Scenario A: Immediate failure on POST
            if not upload_res or "id" not in upload_res:
                error_msg = self._format_error(upload_res)
                if "duplicate of" in error_msg.lower() and attempt < max_upload_attempts - 1:
                    time.sleep(base_retry_delay)
                    continue
                return False, f"La requête d'envoi a été rejetée par Strava : {error_msg}"

            # Scenario B: Async polling via helper
            success, error_msg, is_duplicate = self._poll_upload_status(upload_res["id"])

            if success:
                return True, None

            if is_duplicate and attempt < max_upload_attempts - 1:
                time.sleep(base_retry_delay)
                continue

            return False, error_msg

        return False, "Échec suite à des duplications répétées sur Strava."
