import xml.etree.ElementTree as ET

from wpt_manager.io.gpx_writer import save_gpx
from wpt_manager.models.waypoint import Waypoint


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
OSMAND_NAMESPACE = "https://osmand.net"


def test_save_gpx(tmp_path):
    waypoints = [
        Waypoint(
            name="Pont du Gard",
            latitude=43.947070,
            longitude=4.535600,
            icon="historic_archaeological_site",
            background="square",
            color="#FF8000",
            note="Zastavit na focení",
            comment="Velmi pěkné místo pro delší zastávku.",
        ),
        Waypoint(
            name="Gorges du Toulourenc",
            latitude=44.216738,
            longitude=5.224684,
        ),
    ]

    output_file = tmp_path / "output.gpx"

    save_gpx(waypoints, output_file)

    assert output_file.exists()

    tree = ET.parse(output_file)
    root = tree.getroot()

    elements = root.findall(
        f"{{{GPX_NAMESPACE}}}wpt"
    )

    assert len(elements) == 2

    assert elements[0].attrib["lat"] == "43.947070"
    assert elements[0].attrib["lon"] == "4.535600"

    name = elements[0].find(
        f"{{{GPX_NAMESPACE}}}name"
    )

    assert name is not None
    assert name.text == "Pont du Gard"

    desc = elements[0].find(
        f"{{{GPX_NAMESPACE}}}desc"
    )
    assert desc is not None
    assert desc.text == "Zastavit na focení"

    cmt = elements[0].find(
        f"{{{GPX_NAMESPACE}}}cmt"
    )
    assert cmt is not None
    assert cmt.text == "Velmi pěkné místo pro delší zastávku."

    extensions = elements[0].find(
        f"{{{GPX_NAMESPACE}}}extensions"
    )
    assert extensions is not None

    icon = extensions.find(
        f"{{{OSMAND_NAMESPACE}}}icon"
    )
    assert icon is not None
    assert icon.text == "historic_archaeological_site"

    background = extensions.find(
        f"{{{OSMAND_NAMESPACE}}}background"
    )
    assert background is not None
    assert background.text == "square"

    color = extensions.find(
        f"{{{OSMAND_NAMESPACE}}}color"
    )
    assert color is not None
    assert color.text == "#FF8000"
