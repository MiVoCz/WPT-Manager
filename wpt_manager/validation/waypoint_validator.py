from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.coordinates import validate_coordinates


def validate_waypoint(waypoint: Waypoint) -> list[str]:
    errors = []

    if not waypoint.name.strip():
        errors.append("Waypoint name cannot be empty.")

    errors.extend(validate_coordinates(waypoint.latitude, waypoint.longitude))

    return errors
