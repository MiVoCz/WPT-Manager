import xml.etree.ElementTree as ET
from pathlib import Path

from wpt_manager.models.waypoint import Waypoint


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
OSMAND_NAMESPACE = "https://osmand.net"


ET.register_namespace("", GPX_NAMESPACE)
ET.register_namespace("osmand", OSMAND_NAMESPACE)


def save_gpx(
    waypoints: list[Waypoint],
    path: str | Path,
) -> None:
    root = ET.Element(
        f"{{{GPX_NAMESPACE}}}gpx",
        {
            "version": "1.1",
            "creator": "WPT-Manager",
        },
    )

    for waypoint in waypoints:
        wpt = ET.SubElement(
            root,
            f"{{{GPX_NAMESPACE}}}wpt",
            {
                "lat": f"{waypoint.latitude:.6f}",
                "lon": f"{waypoint.longitude:.6f}",
            },
        )

        name = ET.SubElement(
            wpt,
            f"{{{GPX_NAMESPACE}}}name",
        )
        name.text = waypoint.name

        if waypoint.note:
            desc = ET.SubElement(
                wpt,
                f"{{{GPX_NAMESPACE}}}desc",
            )
            desc.text = waypoint.note

        if waypoint.comment:
            cmt = ET.SubElement(
                wpt,
                f"{{{GPX_NAMESPACE}}}cmt",
            )
            cmt.text = waypoint.comment

        extensions = ET.SubElement(
            wpt,
            f"{{{GPX_NAMESPACE}}}extensions",
        )

        icon = ET.SubElement(
            extensions,
            f"{{{OSMAND_NAMESPACE}}}icon",
        )
        icon.text = waypoint.icon

        background = ET.SubElement(
            extensions,
            f"{{{OSMAND_NAMESPACE}}}background",
        )
        background.text = waypoint.background

        color = ET.SubElement(
            extensions,
            f"{{{OSMAND_NAMESPACE}}}color",
        )
        color.text = waypoint.color

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")

    tree.write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )
