from math import isfinite


def validate_coordinates(latitude: float, longitude: float) -> list[str]:
    """Validate finite geographic coordinates, including zero and boundaries."""
    errors: list[str] = []
    if not isfinite(latitude):
        errors.append("Latitude must be a finite number.")
    elif not -90 <= latitude <= 90:
        errors.append("Latitude must be between -90 and 90.")
    if not isfinite(longitude):
        errors.append("Longitude must be a finite number.")
    elif not -180 <= longitude <= 180:
        errors.append("Longitude must be between -180 and 180.")
    return errors
