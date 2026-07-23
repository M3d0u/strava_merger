"""Application Service coordinating domain models and infrastructure clients."""

import time
from typing import Any

from strava_utils.domain import StravaActivity
from strava_utils.strava_client import StravaAPIClient


class StravaService:
    def __init__(self) -> None:
        self.client = StravaAPIClient()

    def get_recent_activities(self, limit: int = 12) -> list[StravaActivity]:
        """Fetch and convert raw API entries into domain entities.

        Args:
            limit (int): The maximum number of activities to fetch.

        Returns:
            list[StravaActivity]: A list of StravaActivity instances.
        """
        raw_data = self.client.fetch_activities(limit=limit)
        if not raw_data:
            return []
        return [StravaActivity.from_api(a) for a in raw_data]

    def get_delete_url(self, activity: StravaActivity) -> str:
        """Get the direct link to delete an activity on Strava.

        Args:
            activity (StravaActivity): The StravaActivity instance to delete.

        Returns:
            str: The direct link to delete the activity.
        """
        return self.client.link_to_delete_activity(activity.id)

    def rename_activity(self, activity_id: int, new_name: str, description: str | None = None) -> None:
        """Rename an individual activity.

        Args:
            activity_id (int): The ID of the activity to rename.
            new_name (str): The new name for the activity.
            description (str, optional): An optional description for the activity.
        """
        self.client.rename_activity(activity_id, new_name, description=description)

    def _format_error(self, response_dict: dict[str, Any] | None) -> str:
        """Extract and format error messages from Strava API responses.

        Args:
            response_dict (dict[str, Any] | None): The response dictionary from the Strava API.

        Returns:
            str: A formatted error message.
        """
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

        Args:
            upload_id (int): The ID of the upload.

        Returns:
            tuple[bool, str | None, bool]: A tuple containing the success status, error message, and duplicate flag.
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
        """Coordinate loading missing streams, compiling GPX, and uploading.

        Args:
            activities (list[StravaActivity]): List of StravaActivity instances to merge.
            target_name (str): The name for the merged activity.

        Returns:
            tuple[bool, str | None]: A tuple containing the success status and error message.
        """
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
