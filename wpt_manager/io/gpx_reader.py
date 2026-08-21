import xml.etree.ElementTree as ET
from pathlib import Path

from wpt_manager.models.waypoint import Waypoint

from .exceptions import GpxReaderError


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"


def load_gpx(path: str | Path) -> list[Waypoint]:
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise GpxReaderError(
            f"Unable to read GPX file: {path}"
        ) from exc

    root = tree.getroot()
    waypoints = []

    for element in root.findall(f"{{{GPX_NAMESPACE}}}wpt"):
        try:
            latitude = float(element.attrib["lat"])
            longitude = float(element.attrib["lon"])
        except (KeyError, ValueError) as exc:
            raise GpxReaderError(
                "Invalid waypoint coordinates."
            ) from exc

        name_element = element.find(f"{{{GPX_NAMESPACE}}}name")

        name = ""
        if name_element is not None and name_element.text:
            name = name_element.text

        waypoints.append(
            Waypoint(
                name=name,
                latitude=latitude,
                longitude=longitude,
            )
        )

    return waypoints