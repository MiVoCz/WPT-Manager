import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import traceback
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from wpt_manager.database.database import Database
from wpt_manager.photos.imagekit import (
    ImageKitAuthenticationError, ImageKitConnectionError, ImageKitError,
    ImageKitPhotoSource, ImageKitUnexpectedResponseError, _NoRedirect,
    dms_to_decimal, map_imagekit_asset,
)
from wpt_manager.photos.imagekit_probe import main, redact_metadata
from wpt_manager.photos.import_service import import_source_items


KEY = "private_test_DO_NOT_PRINT"


@pytest.fixture(autouse=True)
def http(monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", KEY)
    opener = MagicMock()
    monkeypatch.setattr("wpt_manager.photos.imagekit.build_opener", lambda *args: opener)
    return opener.open


def response(assets=None, *, body=None, status=200):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status = status
    result.read.return_value = json.dumps(assets).encode() if body is None else body
    return result


def asset(**changes):
    return {
        "type": "file", "fileType": "image", "fileId": "file-1", "name": "photo.jpg",
        "url": "https://ik.imagekit.io/test/photo.jpg", "thumbnailUrl": "https://ik.imagekit.io/test/thumb.jpg",
        "size": 1234, "width": 800, "height": 600, **changes,
    }


def test_auth_folder_pagination_and_protocol(http):
    http.side_effect = [response([asset(), asset(fileId="file-2")]), response([asset(fileId="file-3")])]
    source = ImageKitPhotoSource(folder="/ITA 2026/", page_size=2)
    items = source.list_photos()
    assert len(items) == source.assets_found == 3
    for index, call in enumerate(http.call_args_list):
        request = call.args[0]
        assert request.method == "GET"
        assert request.full_url.startswith("https://api.imagekit.io/v1/files?")
        assert request.get_header("Authorization") == "Basic " + base64.b64encode((KEY + ":").encode()).decode()
        assert parse_qs(urlparse(request.full_url).query) == {
            "path": ["/ITA 2026/"], "skip": [str(index * 2)], "limit": ["2"],
            "type": ["file"], "sort": ["ASC_CREATED"],
        }
        assert call.kwargs["timeout"] == 15
    assert source.get_thumbnail(items[0]) == items[0].thumbnail_url
    assert source.get_original_reference(items[0]) == items[0].source_url
    assert source.get_photo_metadata("file-1") == asset()
    with pytest.raises(KeyError):
        source.get_photo_metadata("unknown")


@pytest.mark.parametrize("key", [None, "", " "])
def test_missing_key(monkeypatch, key):
    monkeypatch.delenv("IMAGEKIT_PRIVATE_KEY")
    with pytest.raises(ImageKitAuthenticationError):
        ImageKitPhotoSource(key)


def test_explicit_key_wins(http):
    http.return_value = response([])
    ImageKitPhotoSource("explicit").list_photos()
    assert http.call_args.args[0].get_header("Authorization") == "Basic ZXhwbGljaXQ6"


@pytest.mark.parametrize("status, error", [(401, ImageKitAuthenticationError), (403, ImageKitAuthenticationError), (400, ImageKitError), (500, ImageKitError), (302, ImageKitError)])
@pytest.mark.parametrize("raised", [False, True])
def test_http_errors_safe(http, caplog, status, error, raised):
    if raised:
        http.side_effect = HTTPError("https://example/" + KEY, status, KEY, {}, BytesIO(KEY.encode()))
    else:
        http.return_value = response(body=KEY.encode(), status=status)
    source = ImageKitPhotoSource()
    with pytest.raises(error) as caught:
        source.list_photos()
    assert KEY not in str(caught.value) + "".join(traceback.format_exception(caught.value)) + caplog.text + repr(source)


@pytest.mark.parametrize("error", [TimeoutError(KEY), URLError(KEY), ConnectionError(KEY)])
def test_connection_errors(http, error):
    http.side_effect = error
    with pytest.raises(ImageKitConnectionError) as caught:
        ImageKitPhotoSource().list_photos()
    assert KEY not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("body", [b"not json", b"\xff", b"{}", b"null", b"[1]"])
def test_bad_response(http, body):
    http.return_value = response(body=body)
    with pytest.raises(ImageKitUnexpectedResponseError):
        ImageKitPhotoSource().list_photos()


@pytest.mark.parametrize("count", [0, 1, 4])
def test_list_sizes(http, count):
    http.return_value = response([asset(fileId=str(i)) for i in range(count)])
    assert len(ImageKitPhotoSource().list_photos()) == count


def test_repeated_page_and_reset(http):
    http.return_value = response([asset()])
    source = ImageKitPhotoSource(page_size=1)
    with pytest.raises(ImageKitUnexpectedResponseError, match="pagination"):
        source.list_photos()
    http.return_value = response([])
    assert source.list_photos() == []
    assert source.first_asset is None and source.assets_found == 0


@pytest.mark.parametrize("changes", [{"type": "folder"}, {"fileType": "non-image"}, {"mimeType": "video/mp4"}, {"mimeType": "text/plain"}, {"fileType": None}])
def test_non_images(changes):
    assert map_imagekit_asset(asset(**changes)) is None


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"])
def test_mime(mime):
    assert map_imagekit_asset(asset(mimeType=mime)) is not None


def test_mapping_and_metadata():
    raw = asset(embeddedMetadata={
        "EXIF": {"Make": "Canon", "Model": "R5", "LensModel": "24mm", "ISO": 100,
                 "FNumber": 2.8, "ExposureTime": "1/100", "FocalLength": 24},
        "GPSLatitude": [50, 30, 0], "GPSLatitudeRef": "N",
        "GPSLongitude": [14, 15, 0], "GPSLongitudeRef": "E",
        "GPSAltitude": "123/2", "GPSAltitudeRef": 1,
    }, customMetadata={"trip": "Italy"})
    item = map_imagekit_asset(raw)
    assert (item.external_id, item.name, item.source_url, item.thumbnail_url) == (raw["fileId"], raw["name"], raw["url"], raw["thumbnailUrl"])
    assert (item.latitude, item.longitude, item.altitude) == (50.5, 14.25, -61.5)
    assert item.metadata == raw
    raw["customMetadata"]["trip"] = "changed"
    assert item.metadata["customMetadata"] == {"trip": "Italy"}


@pytest.mark.parametrize("value, expected", [
    ("2026:06:01 12:30:45", datetime(2026, 6, 1, 12, 30, 45)),
    ("2026-06-01T12:30:45Z", datetime(2026, 6, 1, 12, 30, 45, tzinfo=timezone.utc)),
    ("invalid", None), (123, None), (None, None),
])
def test_datetime(value, expected):
    assert map_imagekit_asset(asset(embeddedMetadata={"DateTimeOriginal": value}, createdAt="2026-01-01")).taken_at == expected


@pytest.mark.parametrize("value, ref, expected", [
    ([50, 30, 0], "N", 50.5), ([50, 30, 0], "S", -50.5),
    ("14/1 15/1 0/1", "E", 14.25), ("14° 15' 0\"", "W", -14.25),
    ("-14.25", None, -14.25), ("14.25", "W", -14.25),
    ([1, 60, 0], "N", None), ([1, 2], None, None),
    ("NaN", None, None), ("1/0", None, None), (True, None, None),
])
def test_dms(value, ref, expected):
    assert dms_to_decimal(value, ref) == expected


@pytest.mark.parametrize("embedded", [None, [], "bad", {}, {"GPSLatitude": "bad", "GPSAltitude": []}])
def test_missing_or_malformed_metadata(embedded):
    item = map_imagekit_asset(asset(embeddedMetadata=embedded))
    assert (item.taken_at, item.latitude, item.longitude, item.altitude) == (None, None, None, None)


def test_partial_and_invalid_gps():
    item = map_imagekit_asset(asset(embeddedMetadata={"GPSLatitude": "50.5"}))
    assert (item.latitude, item.longitude) == (50.5, None)
    item = map_imagekit_asset(asset(embeddedMetadata={"GPSLatitude": 91, "GPSLongitude": 181, "GPSAltitude": "nan"}))
    assert (item.latitude, item.longitude, item.altitude) == (None, None, None)


def test_redirect_blocked():
    assert _NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None


def test_database_import_duplicates(http, tmp_path):
    http.return_value = response([asset()])
    database = Database(tmp_path / "imagekit.db")
    database.initialize()
    source = ImageKitPhotoSource()
    photos = import_source_items(database, source)
    assert len(photos) == 1
    assert photos[0].source_type == "imagekit" and photos[0].track_uuid is None
    assert import_source_items(database, source) == []


def test_probe_output_and_security(http, capsys, caplog):
    raw = asset(name=KEY, embeddedMetadata={"Make": "Canon", "token": "secret-token", "nested": {"Authorization": "Basic secret-auth", "notes": KEY}}, customMetadata={"cookies": "cookie-data", "description": KEY})
    http.return_value = response([raw] + [asset(fileId=str(i)) for i in range(6)])
    assert main(["--folder", "/ITA_2026/", "--debug-metadata"]) == 0
    output = capsys.readouterr().out
    assert "ImageKit connection: OK" in output and "Assets found: 7" in output and "Images found: 7" in output
    assert "Photo 5:" in output and "Photo 6:" not in output
    assert "camera make: Canon" in output
    assert "taken_at: None" in output
    for secret in (KEY, "secret-token", "secret-auth", "cookie-data"):
        assert secret not in output + caplog.text


def test_probe_debug_first_non_image(http, capsys):
    http.return_value = response([asset(fileType="non-image", embeddedMetadata={"Make": "first"}), asset(embeddedMetadata={"Make": "second"})])
    assert main(["--debug-metadata"]) == 0
    assert '"Make": "first"' in capsys.readouterr().out


def test_probe_failed(http, capsys):
    http.return_value = response(status=401, body=KEY.encode())
    assert main([]) == 1
    output = capsys.readouterr().out
    assert "ImageKit connection: FAILED" in output and KEY not in output


def test_nested_redaction():
    value = {"nested": [{"api_key": "abc", "notes": "Bearer xyz", "url": "https://host/a?signature=xyz"}], "normal": KEY}
    original = deepcopy(value)
    safe = str(redact_metadata(value, KEY))
    assert "abc" not in safe and "xyz" not in safe and KEY not in safe
    assert value == original


@pytest.mark.parametrize("altitude, reference, expected", [
    (2101, None, 2101.0), (2101, "Above Sea Level", 2101.0),
    (2101, "Below Sea Level", -2101.0), (-2101, "Below Sea Level", -2101.0),
    (2101, 0, 2101.0), (2101, 1, -2101.0),
    ("2101", "0", 2101.0), ("2101", "1", -2101.0),
    (2101, " above sea level ", 2101.0),
    (2101, "unknown", None), (2101, 2, None), (2101, True, None),
    ("bad", "Above Sea Level", None), (float("inf"), 0, None),
])
def test_altitude_references(altitude, reference, expected):
    item = map_imagekit_asset(asset(embeddedMetadata={
        "GPSAltitude": altitude, "GPSAltitudeRef": reference,
    }))
    assert item.altitude == expected


@pytest.mark.parametrize("lat, lon, lat_ref, lon_ref, expected", [
    (50.5, 14.25, None, None, (50.5, 14.25)),
    (50.5, 14.25, "S", "W", (-50.5, -14.25)),
    (-50.5, -14.25, "S", "W", (-50.5, -14.25)),
    (-50.5, -14.25, "N", "E", (-50.5, -14.25)),
    (-50.5, -14.25, None, None, (-50.5, -14.25)),
    ([50, 30, 0], [14, 15, 0], "S", "W", (-50.5, -14.25)),
])
def test_decimal_coordinates_and_signs(lat, lon, lat_ref, lon_ref, expected):
    item = map_imagekit_asset(asset(embeddedMetadata={
        "GPSLatitude": lat, "GPSLongitude": lon,
        "GPSLatitudeRef": lat_ref, "GPSLongitudeRef": lon_ref,
    }))
    assert (item.latitude, item.longitude) == expected


@pytest.mark.parametrize("original, offset, expected_offset", [
    ("2026-09-04T15:46:15.000Z", "+02:00", timedelta(0)),
    ("2026:09:04 17:46:15", "+02:00", timedelta(hours=2)),
    ("2026-09-04T17:46:15", "-03:30", -timedelta(hours=3, minutes=30)),
    ("2026-09-04T17:46:15+01:00", "+02:00", timedelta(hours=1)),
    ("2026:09:04 17:46:15", "bad", None),
    ("2026:09:04 17:46:15", "+25:00", None),
    ("2026:09:04 17:46:15", "+02:60", None),
])
def test_original_datetime_offset(original, offset, expected_offset):
    item = map_imagekit_asset(asset(embeddedMetadata={
        "DateTimeOriginal": original, "OffsetTimeOriginal": offset,
        "DateCreated": "2000-01-01", "DateTimeCreated": "2001-01-01",
    }))
    assert item.taken_at.utcoffset() == expected_offset
    assert item.taken_at.date().isoformat() == "2026-09-04"
    if original.endswith("Z"):
        assert item.taken_at == datetime(2026, 9, 4, 15, 46, 15, tzinfo=timezone.utc)


def test_real_metadata_preserved_without_thumbnails():
    embedded = {
        "Make": "Canon", "Model": "R5", "ISO": 100, "FNumber": 8,
        "ApertureValue": 6, "GPSAltitude": 2101,
        "GPSAltitudeRef": "Above Sea Level", "OffsetTimeOriginal": "+02:00",
    }
    item = map_imagekit_asset(asset(embeddedMetadata=embedded, thumbnailUrl=None))
    assert item.thumbnail_url is None
    assert item.metadata["embeddedMetadata"] == embedded
    for field in ("ExposureTime", "LensModel", "FocalLength"):
        assert item.metadata["embeddedMetadata"].get(field) is None
    raw = asset()
    del raw["thumbnailUrl"]
    assert map_imagekit_asset(raw).thumbnail_url is None
