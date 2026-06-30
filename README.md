# Features to do
- Detection d'activité à merger :white_check_mark:
- si merge :
  - fusion des activités,
  - lien direct vers les activités à supprimer,
  - puis upload du nouveau gpx avec nom donné en amont
- rename automatique pour les activités weightTraining

    # @staticmethod
    # def detect_WeightTraining(activities: List["StravaActivity"]) -> StravaActivity:
    #     """Analyse entity data to detect weight training to rename."""

    #     # Get all weightTraining and sort them from most recent. If most recent does not contains "Push" or "Pull", then rename it Push if most recent -1 is Pull else Pull
    #     weight_activities = [act for act in activities if act.activity_type == "WeightTraining"]
    #     if not weight_activities:
    #         return None
    #     sorted_activities = sorted(weight_activities, key=lambda x: str(x.raw.get("start_date", "")))
    #     most_recent_activity = sorted_activities[-1]

    #     if "Push" not in most_recent_activity.name or "Pull" not in most_recent_activity.name :
    #         print("renaming activity")
