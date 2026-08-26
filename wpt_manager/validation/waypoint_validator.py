from math import isfinite

from wpt_manager.models.waypoint import Waypoint


def validate_waypoint(waypoint: Waypoint) -> list[str]:
    errors = []

    if not waypoint.name.strip():
        errors.append("Waypoint name cannot be empty.")

    if not isfinite(waypoint.latitude):
        errors.append("Latitude must be a finite number.")
    elif not -90 <= waypoint.latitude <= 90:
        errors.append("Latitude must be between -90 and 90.")

    if not isfinite(waypoint.longitude):
        errors.append("Longitude must be a finite number.")
    elif not -180 <= waypoint.longitude <= 180:
        errors.append("Longitude must be between -180 and 180.")

    return errors
