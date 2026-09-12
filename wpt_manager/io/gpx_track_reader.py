import math
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.validation.coordinates import validate_coordinates

from .exceptions import GpxReaderError
from .gpx_reader import GPX_NAMESPACE


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise GpxReaderError(f"Invalid track point time: {value}") from exc


def _distance_m(first: TrackPoint, second: TrackPoint) -> float:
    radius_m = 6_371_008.8
    lat1, lat2 = map(math.radians, (first.latitude, second.latitude))
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second.longitude - first.longitude)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius_m * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def load_gpx_tracks(path: str | Path) -> list[Track]:
    source_path = Path(path)
    try:
        root = ET.parse(source_path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise GpxReaderError(f"Unable to read GPX file: {path}") from exc
    namespace = f"{{{GPX_NAMESPACE}}}"
    if root.tag != f"{namespace}gpx":
        raise GpxReaderError("Unsupported GPX document: root element must be <gpx> in the GPX 1.1 namespace.")

    tracks: list[Track] = []
    for track_element in root.findall(f"{namespace}trk"):
        name_element = track_element.find(f"{namespace}name")
        name = (
            name_element.text.strip()
            if name_element is not None and name_element.text
            else source_path.stem
        )
        points: list[TrackPoint] = []
        for segment_index, segment in enumerate(
            track_element.findall(f"{namespace}trkseg")
        ):
            for element in segment.findall(f"{namespace}trkpt"):
                try:
                    latitude = float(element.attrib["lat"])
                    longitude = float(element.attrib["lon"])
                except (KeyError, ValueError) as exc:
                    raise GpxReaderError("Invalid track point coordinates.") from exc
                errors = validate_coordinates(latitude, longitude)
                if errors:
                    raise GpxReaderError("Invalid track point coordinates: " + " ".join(errors))
                elevation_element = element.find(f"{namespace}ele")
                time_element = element.find(f"{namespace}time")
                try:
                    elevation = (
                        float(elevation_element.text)
                        if elevation_element is not None
                        and elevation_element.text is not None
                        else None
                    )
                except ValueError as exc:
                    raise GpxReaderError("Invalid track point elevation.") from exc
                point_time = (
                    _parse_time(time_element.text)
                    if time_element is not None and time_element.text
                    else None
                )
                points.append(
                    TrackPoint(
                        latitude, longitude, len(points), elevation,
                        point_time, segment_index,
                    )
                )
        timed = [point.time for point in points if point.time is not None]
        distance = sum(
            _distance_m(first, second)
            for first, second in zip(points, points[1:])
            if first.segment_index == second.segment_index
        )
        tracks.append(
            Track(
                name=name,
                source_file=source_path.name,
                points=points,
                start_time=timed[0] if timed else None,
                end_time=timed[-1] if timed else None,
                distance_m=distance,
                point_count=len(points),
            )
        )
    return tracks
