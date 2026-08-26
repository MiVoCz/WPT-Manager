import xml.etree.ElementTree as ET
from pathlib import Path

from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_validator import validate_waypoint

from .exceptions import GpxReaderError


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
OSMAND_NAMESPACE = "https://osmand.net"


def load_gpx(path: str | Path) -> list[Waypoint]:
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        raise GpxReaderError(
            f"Unable to read GPX file: {path}"
        ) from exc

    root = tree.getroot()
    expected_root_tag = f"{{{GPX_NAMESPACE}}}gpx"
    if root.tag != expected_root_tag:
        raise GpxReaderError(
            "Unsupported GPX document: root element must be <gpx> "
            f"in the GPX 1.1 namespace ({GPX_NAMESPACE})."
        )

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

        waypoint = Waypoint(
            name=name,
            latitude=latitude,
            longitude=longitude,
        )

        desc_element = element.find(f"{{{GPX_NAMESPACE}}}desc")
        if desc_element is not None and desc_element.text is not None:
            waypoint.note = desc_element.text

        cmt_element = element.find(f"{{{GPX_NAMESPACE}}}cmt")
        if cmt_element is not None and cmt_element.text is not None:
            waypoint.comment = cmt_element.text

        extensions_element = element.find(
            f"{{{GPX_NAMESPACE}}}extensions"
        )
        if extensions_element is not None:
            icon_element = extensions_element.find(
                f"{{{OSMAND_NAMESPACE}}}icon"
            )
            if icon_element is not None and icon_element.text is not None:
                waypoint.icon = icon_element.text

            background_element = extensions_element.find(
                f"{{{OSMAND_NAMESPACE}}}background"
            )
            if (
                background_element is not None
                and background_element.text is not None
            ):
                waypoint.background = background_element.text

            color_element = extensions_element.find(
                f"{{{OSMAND_NAMESPACE}}}color"
            )
            if color_element is not None and color_element.text is not None:
                waypoint.color = color_element.text

        validation_errors = validate_waypoint(waypoint)
        if validation_errors:
            waypoint_label = (
                f'waypoint "{waypoint.name}"'
                if waypoint.name
                else "unnamed waypoint"
            )
            raise GpxReaderError(
                f"Invalid {waypoint_label}: "
                + " ".join(validation_errors)
            )

        waypoints.append(waypoint)

    return waypoints
