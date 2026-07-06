"""Script to test merger functionality."""

from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree as mod_etree

import gpxpy
import gpxpy.gpx


def merge_to_gpx(activities: list[Any]) -> str:
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
        latlng: list[list[float]] = act.streams["latlng"]["data"]
        time_offsets: list[int] = act.streams["time"]["data"]
        altitudes: list[float | None] = act.streams.get("altitude", {}).get("data", [None] * len(latlng))
        hr: list[int | None] = act.streams.get("heartrate", {}).get("data", [None] * len(latlng))

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


class MockActivity:
    """Mocks the domain entity structure required by merge_to_gpx."""

    def __init__(self, start_date: str, latlng: list, time_offsets: list, altitude: list, heartrate: list):
        self.raw = {"start_date": start_date}
        self.streams = {"latlng": {"data": latlng}, "time": {"data": time_offsets}, "altitude": {"data": altitude}, "heartrate": {"data": heartrate}}


def load_gpx_as_mock_activity(file_path: str) -> MockActivity:
    """Parses an existing GPX file and extracts data streams for the mock object."""
    with open(file_path, "r") as f:
        gpx = gpxpy.parse(f)

    latlng, time_offsets, altitude, heartrate = [], [], [], []
    start_time = None

    # Gather all trackpoints across tracks and segments
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                # Establish global baseline start time for calculating relative offsets
                if start_time is None and point.time:
                    start_time = point.time

                latlng.append([point.latitude, point.longitude])
                altitude.append(point.elevation)

                # Calculate time offset in seconds from the start
                if point.time and start_time:
                    offset = int((point.time - start_time).total_seconds())
                    time_offsets.append(offset)
                else:
                    time_offsets.append(0)

                # Look for Garmin TrackPointExtension Heart Rate data
                hr_val = None
                if point.extensions:
                    for ext in point.extensions:
                        # Search for <hr> tags inside Garmin's XML namespace
                        hr_elements = ext.findall(".//{http://www.garmin.com/xmlschemas/TrackPointExtension/v1}hr")
                        if hr_elements:
                            try:
                                hr_val = int(hr_elements[0].text)
                            except (ValueError, TypeError):
                                pass
                            break
                heartrate.append(hr_val)

    # Fallback if the file had no timestamps at all
    if not start_time:
        start_time = datetime.now(timezone.utc)
        time_offsets = [0] * len(latlng)

    return MockActivity(start_date=start_time.isoformat(), latlng=latlng, time_offsets=time_offsets, altitude=altitude, heartrate=heartrate)


if __name__ == "__main__":
    gpx_file_1 = "testfiles/Afternoon_Ride.gpx"
    gpx_file_2 = "testfiles/Morning_Ride.gpx"
    output_gpx_file = "testfiles/merged_output.gpx"

    print("Parsing input GPX files into mock domain streams...")
    try:
        activity_1 = load_gpx_as_mock_activity(gpx_file_1)
        activity_2 = load_gpx_as_mock_activity(gpx_file_2)
        activities_list = [activity_1, activity_2]

        print("Running your `merge_to_gpx` pipeline...")
        merged_xml_string = merge_to_gpx(activities_list)

        print(f"Saving output to {output_gpx_file}...")
        with open(output_gpx_file, "w") as out_file:
            out_file.write(merged_xml_string)

        print("Success! GPX files merged efficiently.")

    except FileNotFoundError as e:
        print(f"Error: Could not find files. Please check paths. Detailed error: {e}")
