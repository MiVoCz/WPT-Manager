import json
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)


MAPY_GEOCODE_URL = "https://api.mapy.com/v1/geocode"
MAPY_SHOW_URL = "https://mapy.com/fnc/v1/showmap"
SEARCH_RESULT_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("All", ()),
    (
        "Places",
        ("regional.municipality", "regional.municipality_part"),
    ),
    ("POI", ("poi",)),
    ("Addresses", ("regional.address",)),
)


@dataclass(frozen=True, slots=True)
class MapSearchResult:
    name: str
    label: str
    latitude: float
    longitude: float
    location: str | None = None
    entity_type: str | None = None
    distance_m: float | None = None


class MapSearchError(ValueError):
    """Raised when a Mapy.com search response cannot be used."""


def build_search_url(
    query: str,
    result_types: tuple[str, ...] = (),
    prefer_bbox: tuple[float, float, float, float] | None = None,
    prefer_near: tuple[float, float] | None = None,
    prefer_near_precision: int | None = None,
) -> QUrl:
    url = QUrl(MAPY_GEOCODE_URL)
    url_query = QUrlQuery()
    url_query.addQueryItem("query", query)
    url_query.addQueryItem("lang", "cs")
    url_query.addQueryItem("limit", "10")
    if result_types:
        url_query.addQueryItem("type", ",".join(result_types))
    if prefer_near is not None:
        longitude, latitude = prefer_near
        url_query.addQueryItem("preferNear", f"{longitude},{latitude}")
        if prefer_near_precision is not None:
            url_query.addQueryItem(
                "preferNearPrecision",
                str(prefer_near_precision),
            )
    elif prefer_bbox is not None:
        url_query.addQueryItem(
            "preferBBox",
            ",".join(str(value) for value in prefer_bbox),
        )
    url.setQuery(url_query)
    return url


def build_mapy_show_url(
    latitude: float,
    longitude: float,
    zoom: int = 16,
) -> QUrl:
    url = QUrl(MAPY_SHOW_URL)
    url_query = QUrlQuery()
    url_query.addQueryItem("center", f"{longitude},{latitude}")
    url_query.addQueryItem("zoom", str(zoom))
    url_query.addQueryItem("marker", "true")
    url.setQuery(url_query)
    return url


def normalize_search_response(payload: object) -> list[MapSearchResult]:
    if not isinstance(payload, dict):
        raise MapSearchError("The search service returned an invalid response.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise MapSearchError("The search service returned an invalid response.")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        position = item.get("position")
        if not isinstance(position, dict):
            continue
        try:
            latitude = float(position["lat"])
            longitude = float(position["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        name = item.get("name")
        label = item.get("label")
        if not isinstance(name, str) or not isinstance(label, str):
            continue
        location = item.get("location")
        entity_type = item.get("type")
        results.append(
            MapSearchResult(
                name=name,
                label=label,
                latitude=latitude,
                longitude=longitude,
                location=location if isinstance(location, str) else None,
                entity_type=(
                    entity_type if isinstance(entity_type, str) else None
                ),
            )
        )
    return results


class MapySearchClient(QObject):
    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(
        self,
        api_key: str | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._network = QNetworkAccessManager(self)

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def search(
        self,
        query: str,
        prefer_bbox: tuple[float, float, float, float] | None = None,
        result_types: tuple[str, ...] = (),
        prefer_near: tuple[float, float] | None = None,
        prefer_near_precision: int | None = None,
    ) -> None:
        if not self._api_key:
            self.error_occurred.emit(
                "Mapy.com search requires a configured API key."
            )
            return

        url = build_search_url(
            query,
            result_types=result_types,
            prefer_bbox=prefer_bbox,
            prefer_near=prefer_near,
            prefer_near_precision=prefer_near_precision,
        )
        request = QNetworkRequest(url)
        request.setRawHeader(
            b"X-MAPY-API-KEY",
            self._api_key.encode("utf-8"),
        )
        request.setTransferTimeout(10_000)
        reply = self._network.get(request)
        reply.finished.connect(lambda: self._finish_request(reply))

    def _finish_request(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.error_occurred.emit(
                    "Mapy.com search is currently unavailable."
                )
                return
            try:
                payload: Any = json.loads(bytes(reply.readAll()))
                results = normalize_search_response(payload)
            except (json.JSONDecodeError, UnicodeDecodeError, MapSearchError):
                self.error_occurred.emit(
                    "Mapy.com search returned an invalid response."
                )
                return
            self.results_ready.emit(results)
        finally:
            reply.deleteLater()
