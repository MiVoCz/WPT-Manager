"""Read-only ImageKit Media Library source (standard-library HTTP only)."""

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from wpt_manager.credential_store import CredentialStoreError, get_imagekit_private_key
from wpt_manager.photos.source import PhotoAuthenticationError, PhotoSourceError, PhotoSourceItem


class ImageKitError(PhotoSourceError):
    pass


def build_imagekit_preview_url(source_url: str, width: int = 600, height: int = 400) -> str:
    """Add a fit-inside delivery transformation, retaining existing parameters."""
    if width <= 0 or height <= 0:
        raise ValueError("Preview dimensions must be positive.")
    parts = urlsplit(source_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    transformations = [value for key, value in query if key == "tr" and value]
    transformations.append(f"w-{width},h-{height},c-at_max")
    query = [(key, value) for key, value in query if key != "tr"]
    query.append(("tr", ":".join(transformations)))
    return urlunsplit(parts._replace(query=urlencode(query)))


class ImageKitAuthenticationError(ImageKitError, PhotoAuthenticationError):
    pass


class ImageKitConnectionError(ImageKitError):
    pass


class ImageKitUnexpectedResponseError(ImageKitError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str,
        headers: Any, newurl: str,
    ) -> None:
        # Never forward the private key to a redirect target.
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, str) and "/" in value:
            numerator, denominator = value.split("/")
            result = float(numerator) / float(denominator)
        else:
            result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def dms_to_decimal(value: Any, reference: Any = None) -> float | None:
    """Parse decimal or three DMS components, including EXIF rational strings."""
    ref = str(reference).strip().upper() if reference is not None else ""
    if ref not in {"", "N", "S", "E", "W"}:
        return None
    result = _number(value)
    if result is None:
        parts = value
        if isinstance(value, str):
            parts = re.split(r"[\s,°º'\"′″]+", value.strip().replace("deg", "").strip())
            parts = [part for part in parts if part]
        if not isinstance(parts, (list, tuple)) or len(parts) != 3:
            return None
        degrees, minutes, seconds = [_number(part) for part in parts]
        if degrees is None or minutes is None or seconds is None:
            return None
        if not 0 <= minutes < 60 or not 0 <= seconds < 60:
            return None
        result = math.copysign(abs(degrees) + minutes / 60 + seconds / 3600, degrees)
    if ref in {"S", "W"} and result > 0:
        result = -result
    return result


def _datetime(value: Any, offset: Any = None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.strptime(value.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        try:
            result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None and isinstance(offset, str):
        match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", offset.strip())
        if match:
            sign, hours, minutes = match.groups()
            if int(hours) < 24 and int(minutes) < 60:
                delta = timedelta(hours=int(hours), minutes=int(minutes))
                result = result.replace(tzinfo=timezone(delta if sign == "+" else -delta))
    # Retain the supplied UTC offset for Photo persistence.
    return result


def embedded_value(metadata: Any, *names: str) -> Any:
    """Find a field in flat or grouped EXIF/GPS metadata, ignoring group prefixes."""
    if not isinstance(metadata, dict):
        return None
    for name in names:
        for key, value in metadata.items():
            if str(key).split(":")[-1].casefold() == name.casefold():
                return value
    for value in metadata.values():
        if isinstance(value, dict):
            found = embedded_value(value, *names)
            if found is not None:
                return found
    return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def map_imagekit_asset(asset: dict[str, Any]) -> PhotoSourceItem | None:
    """Map an image asset; unsupported files and folders are ignored."""
    if asset.get("type", "file") != "file":
        return None
    embedded = asset.get("embeddedMetadata")
    mime = asset.get("mimeType") or asset.get("mime") or embedded_value(embedded, "MIMEType")
    file_type = asset.get("fileType")
    if file_type is not None and file_type != "image":
        return None
    if mime is not None:
        if not isinstance(mime, str) or not mime.lower().startswith("image/"):
            return None
    elif file_type != "image":
        return None
    external_id, name = _text(asset.get("fileId")), _text(asset.get("name"))
    if external_id is None or name is None:
        raise ImageKitUnexpectedResponseError("ImageKit image has no fileId or name.")
    coordinates: list[float | None] = []
    for axis, bound, refs in (("Latitude", 90, {"N", "S"}), ("Longitude", 180, {"E", "W"})):
        reference = embedded_value(embedded, "GPS" + axis + "Ref")
        value = dms_to_decimal(embedded_value(embedded, "GPS" + axis, axis), reference)
        if reference is not None and str(reference).strip().upper() not in refs:
            value = None
        coordinates.append(value if value is not None and abs(value) <= bound else None)
    altitude = _number(embedded_value(embedded, "GPSAltitude", "Altitude"))
    altitude_ref = embedded_value(embedded, "GPSAltitudeRef")
    if altitude is not None and altitude_ref is not None:
        text_ref = altitude_ref.strip().casefold() if isinstance(altitude_ref, str) else None
        ref = {"above sea level": 0, "below sea level": 1}.get(text_ref)
        if ref is None:
            ref = _number(altitude_ref)
        altitude = abs(altitude) * (-1 if ref == 1 else 1) if ref in {0, 1} else None
    return PhotoSourceItem(
        external_id=external_id, name=name,
        taken_at=_datetime(
            embedded_value(embedded, "DateTimeOriginal"),
            embedded_value(embedded, "OffsetTimeOriginal"),
        ),
        latitude=coordinates[0], longitude=coordinates[1], altitude=altitude,
        source_url=_text(asset.get("url")), thumbnail_url=_text(asset.get("thumbnailUrl")),
        metadata=deepcopy(asset),
    )


class ImageKitPhotoSource:
    source_type = "imagekit"
    api_base_url = "https://api.imagekit.io"

    def __init__(
        self, private_key: str | None = None, *, folder: str | None = None,
        page_size: int = 1000, timeout: float = 15.0,
    ) -> None:
        """An explicit key takes precedence; otherwise use the credential resolver."""
        try:
            key = private_key if private_key is not None else get_imagekit_private_key()
        except CredentialStoreError:
            raise ImageKitError("Credential store unavailable") from None
        if not isinstance(key, str) or not key.strip():
            raise ImageKitAuthenticationError("ImageKit private API key is not configured.")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 1000:
            raise ValueError("ImageKit page_size must be between 1 and 1000.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("ImageKit timeout must be positive and finite.")
        self._private_key = key.strip()
        self.folder = folder
        self.page_size = page_size
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())
        self._items_by_id: dict[str, PhotoSourceItem] = {}
        self.assets_found = 0
        self.first_asset: dict[str, Any] | None = None

    def _page(self, skip: int) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "type": "file", "skip": skip, "limit": self.page_size, "sort": "ASC_CREATED",
        }
        if self.folder:
            params["path"] = self.folder
        authorization = base64.b64encode((self._private_key + ":").encode()).decode("ascii")
        request = Request(
            self.api_base_url + "/v1/files?" + urlencode(params), method="GET",
            headers={"Authorization": "Basic " + authorization, "Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                status = response.status
                body = response.read()
        except HTTPError as exc:
            status = exc.code
            exc.close()
            body = b""
        except (OSError, URLError):
            raise ImageKitConnectionError("Could not connect to ImageKit (connection error or timeout).") from None
        if status in {401, 403}:
            raise ImageKitAuthenticationError("ImageKit authentication or permission denied.")
        if not 200 <= status < 300:
            raise ImageKitError(f"ImageKit returned HTTP {status}.")
        try:
            assets = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            raise ImageKitUnexpectedResponseError("ImageKit returned malformed JSON.") from None
        if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
            raise ImageKitUnexpectedResponseError("ImageKit asset list must be an array of objects.")
        return assets

    def test_connection(self) -> None:
        """Request just one file without pagination or photo metadata mapping."""
        previous_size = self.page_size
        try:
            self.page_size = 1
            self._page(0)
        finally:
            self.page_size = previous_size

    def list_photos(self) -> list[PhotoSourceItem]:
        self._items_by_id = {}
        self.assets_found = 0
        self.first_asset = None
        items: dict[str, PhotoSourceItem] = {}
        skip = 0
        previous_page: list[dict[str, Any]] | None = None
        while True:
            assets = self._page(skip)
            if assets and assets == previous_page:
                raise ImageKitUnexpectedResponseError("ImageKit pagination did not advance.")
            if self.first_asset is None and assets:
                self.first_asset = deepcopy(assets[0])
            self.assets_found += len(assets)
            for asset in assets:
                item = map_imagekit_asset(asset)
                if item is not None and item.external_id is not None:
                    items[item.external_id] = item
            if len(assets) < self.page_size:
                break
            skip += len(assets)
            previous_page = assets
        self._items_by_id = items
        return list(items.values())

    def get_photo_metadata(self, external_id: str) -> dict[str, Any]:
        return deepcopy(self._items_by_id[external_id].metadata)

    def get_thumbnail(self, item: PhotoSourceItem) -> str | None:
        return item.thumbnail_url

    def get_original_reference(self, item: PhotoSourceItem) -> str | None:
        return item.source_url
