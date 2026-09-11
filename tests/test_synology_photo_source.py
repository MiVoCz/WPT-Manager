import json
from datetime import datetime

import pytest

from wpt_manager.photos.source import (
    InvalidShareUrlError, SynologyAuthenticationError,
    SynologyConnectionError, SynologyMalformedResponseError,
    SynologyUnexpectedResponseError,
)
from wpt_manager.photos.synology import SynologyHttpResponse, SynologyPhotoSource


def _response(body, *, content_type="application/json", status=200,
              final_url="https://nas.example/photo/webapi/entry.cgi",
              cookie_names=()):
    encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
    return SynologyHttpResponse(
        status, content_type, final_url, 0, encoded, cookie_names=cookie_names
    )


def _source(items=(), *, share_url="https://nas.example/photo/mo/sharing/share-id",
            nas_url=None, password="", diagnostics=None):
    calls = []

    def transport(method, url, data, timeout, headers):
        calls.append((method, url, data, headers))
        if data["api"] == "SYNO.Core.Sharing.Login":
            return _response(
                {"success": True}, cookie_names=("sharing_sid",)
            )
        return _response({"success": True, "data": {"items": list(items)}})

    source = SynologyPhotoSource(
        share_url, password, nas_api_base_url=nas_url, transport=transport,
        diagnostic_callback=diagnostics.append if diagnostics is not None else None,
    )
    return source, calls


def test_parse_share_id_with_and_without_photo_prefix():
    assert SynologyPhotoSource.parse_share_id(
        "https://host/mo/sharing/EkPUCJLDI"
    ) == "EkPUCJLDI"
    assert SynologyPhotoSource.parse_share_id(
        "https://host/photo/mo/sharing/EkPUCJLDI/"
    ) == "EkPUCJLDI"
    assert SynologyPhotoSource.parse_share_id("https://host/photo") is None


def test_direct_nas_share_uses_package_specific_endpoints_without_referer():
    source, calls = _source()
    assert source.list_photos() == []
    assert source.api_base_url == "https://nas.example"
    assert calls[0][1] == "https://nas.example/photo/webapi/entry.cgi"
    assert calls[1][1] == "https://nas.example/photo/mo/sharing/webapi/entry.cgi"
    assert all("Referer" not in call[3] for call in calls)


def test_quickconnect_requires_explicit_nas_address():
    message = (
        "QuickConnect web address cannot be used directly for Synology Photos API. "
        "Please provide the NAS/DDNS address."
    )
    with pytest.raises(SynologyUnexpectedResponseError, match=message):
        SynologyPhotoSource(
            "https://device.quickconnect.to/mo/sharing/share-id"
        )


def test_quickconnect_with_nas_url_uses_nas_and_referer():
    share = "https://device.quickconnect.to/photo/mo/sharing/share-id"
    source, calls = _source(
        share_url=share, nas_url="https://photos.example.synology.me:5001"
    )
    source.list_photos()
    assert source.api_base_url == "https://photos.example.synology.me:5001"
    assert all(call[3]["Referer"] == share for call in calls)
    assert all("quickconnect.to/webapi" not in call[1] for call in calls)


def test_sharing_login_parameters_cookie_and_list_request():
    source, calls = _source(password="secret")
    source.list_photos()
    login = calls[0]
    assert login[2] == {
        "api": "SYNO.Core.Sharing.Login", "version": "1",
        "method": "login", "sharing_id": "share-id", "password": "secret",
    }
    assert source.sharing_login_success
    assert source.sharing_session_available
    listing = calls[1]
    assert listing[3]["x-syno-sharing"] == "share-id"
    assert listing[2]["passphrase"] == "share-id"
    assert set(json.loads(listing[2]["additional"])) >= {
        "thumbnail", "resolution", "orientation", "exif", "gps", "description"
    }


def test_failed_authentication_stops_before_list():
    calls = []

    def transport(method, url, data, timeout, headers):
        calls.append(data["api"])
        return _response({"success": False, "error": {"code": 105}})

    source = SynologyPhotoSource(
        "https://nas.example/photo/mo/sharing/id", "bad", transport=transport
    )
    with pytest.raises(SynologyAuthenticationError):
        source.list_photos()
    assert calls == ["SYNO.Core.Sharing.Login"]


def test_list_maps_available_metadata_and_handles_missing_exif_gps():
    raw = {
        "id": 12, "filename": "one.jpg", "time": "2026-01-02T03:04:05Z",
        "additional": {
            "resolution": {"width": 100, "height": 80}, "orientation": 1,
            "description": "View", "thumbnail": {"cache_key": "a"},
            "exif": {"camera": "Camera", "lens": "Lens", "gps": {
                "latitude": "50.1", "longitude": 14.2, "altitude": "250"
            }},
        },
    }
    source, _ = _source([raw, {"id": 13, "filename": "two.jpg"}])
    items = source.list_photos()
    assert len(items) == 2 and isinstance(items[0].taken_at, datetime)
    assert (items[0].latitude, items[0].longitude, items[0].altitude) == (
        50.1, 14.2, 250.0
    )
    assert items[0].metadata["additional"]["exif"]["camera"] == "Camera"
    assert items[1].latitude is None and items[1].taken_at is None


def test_malformed_html_timeout_and_secrets_are_safe():
    secret = "never-print-this"
    diagnostics = []

    def html(method, url, data, timeout, headers):
        return _response(
            f"<html>password={secret}; sharing_sid=session-secret</html>".encode(),
            content_type="text/html", final_url="https://nas/login?token=url-secret",
        )

    source = SynologyPhotoSource(
        "https://nas.example/photo/mo/sharing/share-id", secret,
        transport=html, diagnostic_callback=diagnostics.append,
    )
    with pytest.raises(SynologyUnexpectedResponseError) as raised:
        source.list_photos()
    combined = str(raised.value) + repr(diagnostics)
    assert secret not in combined
    assert "session-secret" not in combined
    assert "url-secret" not in combined

    def malformed(method, url, data, timeout, headers):
        return _response(b"{broken")
    with pytest.raises(SynologyMalformedResponseError):
        SynologyPhotoSource(
            "https://nas.example/mo/sharing/id", transport=malformed
        ).list_photos()

    def timeout(method, url, data, seconds, headers):
        raise TimeoutError
    with pytest.raises(SynologyConnectionError):
        SynologyPhotoSource(
            "https://nas.example/mo/sharing/id", transport=timeout
        ).list_photos()


def test_invalid_nas_address_is_rejected():
    with pytest.raises(InvalidShareUrlError):
        SynologyPhotoSource(
            "https://device.quickconnect.to/mo/sharing/id",
            nas_api_base_url="not-a-url",
        )
