from uuid import UUID

from wpt_manager.models.waypoint import Waypoint


def test_waypoint_defaults():
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )

    assert isinstance(waypoint.id, UUID)

    assert waypoint.name == "Pont du Gard"
    assert waypoint.latitude == 43.947070
    assert waypoint.longitude == 4.535600

    assert waypoint.icon == "marker"
    assert waypoint.color == "#FF0000"
    assert waypoint.background == "circle"

    assert waypoint.note == ""
    assert waypoint.comment == ""


def test_waypoint_custom_values():
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="bridge",
        color="#FF8000",
        background="circle",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )

    assert waypoint.icon == "bridge"
    assert waypoint.color == "#FF8000"
    assert waypoint.background == "circle"
    assert waypoint.note == "Zastavit na focení"
    assert waypoint.comment == "Velmi pěkné místo pro delší zastávku."