import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QUrlQuery
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

from wpt_manager.mapy_search import (
    MapSearchResult,
    MapySearchClient,
    build_mapy_show_url,
    build_search_url,
    normalize_search_response,
)


@pytest.mark.parametrize(
    ("result_types", "expected"),
    [
        ((), None),
        (
            ("regional.municipality", "regional.municipality_part"),
            "regional.municipality,regional.municipality_part",
        ),
        (("poi",), "poi"),
        (("regional.address",), "regional.address"),
    ],
)
def test_search_result_type_query_parameter(result_types, expected):
    query = QUrlQuery(build_search_url("Hatě", result_types=result_types))

    assert query.queryItemValue("type") == (expected or "")
    assert query.hasQueryItem("type") is (expected is not None)


def test_search_near_uses_longitude_latitude_and_radius_in_meters():
    query = QUrlQuery(
        build_search_url(
            "restaurant",
            result_types=("poi",),
            prefer_bbox=(13.0, 49.0, 15.0, 51.0),
            prefer_near=(14.456, 50.123),
            prefer_near_precision=5_000,
        )
    )

    assert query.queryItemValue("preferNear") == "14.456,50.123"
    assert query.queryItemValue("preferNearPrecision") == "5000"
    assert not query.hasQueryItem("preferBBox")


def test_mapy_show_url_centers_result_and_displays_marker():
    url = build_mapy_show_url(50.0835, 14.3952)
    query = QUrlQuery(url)

    assert url.path() == "/fnc/v1/showmap"
    assert query.queryItemValue("center") == "14.3952,50.0835"
    assert query.queryItemValue("zoom") == "16"
    assert query.queryItemValue("marker") == "true"


def test_normalize_search_response():
    results = normalize_search_response(
        {
            "items": [
                {
                    "name": "Petřínská rozhledna",
                    "label": "Rozhledna",
                    "position": {"lat": 50.0835, "lon": 14.3952},
                    "location": "Praha, Česko",
                    "type": "poi",
                    "regionalStructure": [],
                }
            ]
        }
    )

    assert results == [
        MapSearchResult(
            name="Petřínská rozhledna",
            label="Rozhledna",
            latitude=50.0835,
            longitude=14.3952,
            location="Praha, Česko",
            entity_type="poi",
        )
    ]


def test_normalize_empty_search_response():
    assert normalize_search_response({"items": []}) == []


def test_search_without_api_key_does_not_make_request():
    application = QApplication.instance() or QApplication([])
    client = MapySearchClient(None)
    errors = []
    client.error_occurred.connect(errors.append)

    client.search("Prague")

    assert not client.is_available
    assert errors == ["Mapy.com search requires a configured API key."]
    application.processEvents()


class FakeReply:
    def __init__(self, error, content=b""):
        self._error = error
        self._content = content
        self.deleted = False

    def error(self):
        return self._error

    def readAll(self):
        return self._content

    def deleteLater(self):
        self.deleted = True


def test_search_network_error_is_reported_without_sensitive_details():
    application = QApplication.instance() or QApplication([])
    client = MapySearchClient("secret-api-key")
    errors = []
    client.error_occurred.connect(errors.append)
    reply = FakeReply(QNetworkReply.NetworkError.ConnectionRefusedError)

    client._finish_request(reply)

    assert errors == ["Mapy.com search is currently unavailable."]
    assert "secret-api-key" not in errors[0]
    assert reply.deleted
    application.processEvents()


def test_search_api_response_error_is_reported():
    application = QApplication.instance() or QApplication([])
    client = MapySearchClient("secret-api-key")
    errors = []
    client.error_occurred.connect(errors.append)
    reply = FakeReply(QNetworkReply.NetworkError.NoError, b"not json")

    client._finish_request(reply)

    assert errors == ["Mapy.com search returned an invalid response."]
    assert reply.deleted
    application.processEvents()
