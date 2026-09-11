import json
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from wpt_manager.photos.source import (
    InvalidShareUrlError, PhotoSourceItem, SynologyApiAddressRequiredError,
    SynologyAuthenticationError,
    SynologyConnectionError, SynologyMalformedResponseError,
    SynologyUnexpectedResponseError,
)


@dataclass(frozen=True)
class SynologyHttpResponse:
    status: int
    content_type: str
    final_url: str
    redirect_count: int
    body: bytes
    redirect_urls: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    cookie_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SynologyHttpDiagnostic:
    operation: str
    method: str
    request_url: str
    status: int
    content_type: str
    final_url: str
    redirect_count: int
    response_type: str
    body_prefix: str | None = None


class _RedirectCounter(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0
        self.urls: list[str] = []
        self.locations: list[str] = []

    def redirect_request(self, *args, **kwargs):
        self.count += 1
        request, _, _, _, headers, new_url = args
        self.urls.extend((request.full_url, new_url))
        location = headers.get("Location")
        if location:
            self.locations.append(location)
        return super().redirect_request(*args, **kwargs)


class SynologyHttpSession:
    """Cookie-preserving HTTP session for the complete share flow."""

    def __init__(self) -> None:
        self._redirects = _RedirectCounter()
        self._cookie_jar = CookieJar()
        self._opener = build_opener(
            HTTPCookieProcessor(self._cookie_jar), self._redirects
        )

    def request(
        self, method: str, url: str, data: dict[str, str] | None, timeout: float,
        headers: dict[str, str] | None = None,
    ) -> SynologyHttpResponse:
        encoded = urlencode(data).encode("utf-8") if data is not None else None
        request = Request(
            url, data=encoded, method=method,
            headers={"Accept": "application/json, text/html;q=0.9", **(headers or {})},
        )
        before = self._redirects.count
        before_urls = len(self._redirects.urls)
        before_locations = len(self._redirects.locations)
        try:
            with self._opener.open(request, timeout=timeout) as response:
                return SynologyHttpResponse(
                    response.status, response.headers.get("Content-Type", ""),
                    response.geturl(), self._redirects.count - before,
                    response.read(), tuple(self._redirects.urls[before_urls:]),
                    tuple(self._redirects.locations[before_locations:]),
                    tuple(cookie.name for cookie in self._cookie_jar),
                )
        except HTTPError as exc:
            if exc.code in {401, 403}:
                raise SynologyAuthenticationError(
                    "Synology share authentication failed."
                ) from exc
            raise SynologyConnectionError(
                f"Synology returned HTTP {exc.code}."
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise SynologyConnectionError("Synology connection timed out.") from exc
        except URLError as exc:
            raise SynologyConnectionError(
                f"Could not connect to Synology: {exc.reason}"
            ) from exc


Transport = Callable[
    [str, str, dict[str, str] | None, float, dict[str, str]],
    SynologyHttpResponse,
]


class SynologyPhotoSource:
    source_type = "synology"

    def __init__(
        self, share_url: str, password: str = "", *,
        nas_api_base_url: str | None = None, timeout: float = 15.0,
        transport: Transport | None = None,
        diagnostic_callback: Callable[[SynologyHttpDiagnostic], None] | None = None,
    ) -> None:
        parsed = urlparse(share_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidShareUrlError("Invalid Synology Photos share URL.")
        token = self.parse_share_id(share_url)
        if not token:
            raise InvalidShareUrlError("The URL does not contain a share token.")
        self.share_url = share_url
        self.original_share_url = share_url
        self._password = password
        self.timeout = timeout
        self._session = SynologyHttpSession()
        self._transport = transport or self._session.request
        self._diagnostic_callback = diagnostic_callback
        share_base = f"{parsed.scheme}://{parsed.netloc}"
        self.connection_type = (
            "QuickConnect" if self._is_quickconnect_host(parsed.hostname) else "Direct"
        )
        self.quickconnect_frontend_url = (
            share_base if self.connection_type == "QuickConnect" else None
        )
        if nas_api_base_url:
            nas = urlparse(nas_api_base_url)
            if nas.scheme not in {"http", "https"} or not nas.netloc:
                raise InvalidShareUrlError("Invalid NAS / DDNS address.")
            self.api_base_url = f"{nas.scheme}://{nas.netloc}"
            self.resolution_method = "explicit NAS address"
        elif self.connection_type == "Direct":
            self.api_base_url = share_base
            self.resolution_method = "direct"
        else:
            raise SynologyApiAddressRequiredError(
                "QuickConnect web address cannot be used directly for "
                "Synology Photos API. Please provide the NAS/DDNS address."
            )
        self._token = token
        self._sharing_sid: str | None = None
        self.sharing_session_available = False
        self.sharing_login_success = False
        self._items_by_id: dict[str, PhotoSourceItem] = {}

    @staticmethod
    def parse_share_id(share_url: str) -> str | None:
        parsed = urlparse(share_url)
        query = parse_qs(parsed.query)
        for key in ("token", "sharing_id", "id"):
            if query.get(key):
                return query[key][0]
        parts = [part for part in parsed.path.split("/") if part]
        if "sharing" in parts and parts.index("sharing") + 1 < len(parts):
            return parts[parts.index("sharing") + 1]
        return None

    @staticmethod
    def _is_quickconnect_host(hostname: str | None) -> bool:
        return bool(
            hostname and (
                hostname.casefold() == "quickconnect.to"
                or hostname.casefold().endswith(".quickconnect.to")
            )
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

    @staticmethod
    def _body_text(response: SynologyHttpResponse) -> str:
        return response.body.decode("utf-8", errors="replace")

    @classmethod
    def _response_type(cls, response: SynologyHttpResponse) -> str:
        content_type = response.content_type.casefold()
        stripped = response.body.lstrip()
        if "json" in content_type or stripped.startswith((b"{", b"[")):
            return "JSON"
        if "html" in content_type or stripped[:32].casefold().startswith(
            (b"<!doctype html", b"<html")
        ):
            return "HTML"
        return "OTHER"

    def _send(
        self, operation: str, method: str, url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> SynologyHttpResponse:
        try:
            response = self._transport(
                method, url, data, self.timeout, headers or {}
            )
        except TimeoutError as exc:
            raise SynologyConnectionError("Synology connection timed out.") from exc
        response_type = self._response_type(response)
        prefix = None if response_type == "JSON" else self._redact(
            self._body_text(response)[:300]
        )
        if self._diagnostic_callback is not None:
            self._diagnostic_callback(SynologyHttpDiagnostic(
                operation, method, self._safe_url(url), response.status,
                response.content_type, self._safe_url(response.final_url),
                response.redirect_count, response_type, prefix,
            ))
        if not 200 <= response.status < 300:
            if response.status in {401, 403}:
                raise SynologyAuthenticationError(
                    "Synology share authentication failed."
                )
            raise SynologyConnectionError(
                f"Synology returned HTTP {response.status}."
            )
        return response

    def _parse_json_response(
        self, response: SynologyHttpResponse, operation: str
    ) -> dict[str, Any]:
        response_type = self._response_type(response)
        if response_type != "JSON":
            raise SynologyUnexpectedResponseError(
                self._unexpected_message(response, operation, response_type)
            )
        try:
            value = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SynologyMalformedResponseError(
                self._unexpected_message(response, operation, "MALFORMED JSON")
            ) from exc
        if not isinstance(value, dict):
            raise SynologyUnexpectedResponseError(
                self._unexpected_message(response, operation, "UNSUPPORTED JSON")
            )
        return value

    def _unexpected_message(
        self, response: SynologyHttpResponse, operation: str, kind: str
    ) -> str:
        return (
            f"Synology response was not usable JSON\nOperation: {operation}\n"
            f"HTTP status: {response.status}\nContent-Type: "
            f"{response.content_type or 'unavailable'}\nFinal URL: "
            f"{self._safe_url(response.final_url)}\nResponse type: {kind}\n"
            f"Body prefix: {self._redact(self._body_text(response)[:300])}"
        )

    def _redact(self, text: str) -> str:
        redacted = text.replace(self._password, "***") if self._password else text
        for secret in (self._token, self._sharing_sid):
            if secret:
                redacted = redacted.replace(secret, "***")
        redacted = re.sub(
            r'(?i)(password|passphrase|sharing_sid|session(?:_id)?|token)'
            r'(\s*[=:]\s*["\']?)[^"\'\s&<>]+',
            r'\1\2***',
            redacted,
        )
        return redacted

    def _read_bootstrap_value(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"sharing_sid", "sharingSid"} and isinstance(child, str):
                    self._sharing_sid = child
                self._read_bootstrap_value(child)
        elif isinstance(value, list):
            for child in value:
                self._read_bootstrap_value(child)

    def _api_request(
        self, operation: str, endpoint: str, api: str, method: str,
        *, headers: dict[str, str] | None = None, **values: str,
    ) -> dict[str, Any]:
        data = {
            "api": api, "version": "1", "method": method,
            **values,
        }
        request_headers = dict(headers or {})
        if self.connection_type == "QuickConnect":
            request_headers["Referer"] = self.original_share_url
        response = self._send(
            operation, "POST", self.api_base_url + endpoint, data,
            request_headers,
        )
        value = self._parse_json_response(response, operation)
        if value.get("success") is False:
            code = (value.get("error") or {}).get("code")
            if code in {105, 106, 119, 401, 403}:
                raise SynologyAuthenticationError(
                    "Synology share authentication failed."
                )
            raise SynologyUnexpectedResponseError(
                f"Synology rejected {operation} (code {code})."
            )
        if operation == "sharing-login":
            self.sharing_login_success = True
            self._read_bootstrap_value(value.get("data"))
            self.sharing_session_available = bool(
                self._sharing_sid
                or any(name.casefold() == "sharing_sid" for name in response.cookie_names)
            )
        return value

    def list_photos(self) -> list[PhotoSourceItem]:
        login_values = {"sharing_id": self._token}
        if self._password:
            login_values["password"] = self._password
        self._api_request(
            "sharing-login", "/photo/webapi/entry.cgi",
            "SYNO.Core.Sharing.Login", "login", **login_values,
        )
        response = self._api_request(
            "list-shared-photos", "/photo/mo/sharing/webapi/entry.cgi",
            "SYNO.Foto.Browse.Item", "list",
            headers={"x-syno-sharing": self._token},
            offset="0", limit="1000", passphrase=self._token,
            additional=json.dumps([
                "thumbnail", "resolution", "orientation", "exif", "gps",
                "description",
            ]),
        )
        data = response.get("data", response)
        raw_items = data.get("list", data.get("items")) if isinstance(data, dict) else None
        if raw_items is None or not isinstance(raw_items, list):
            raise SynologyUnexpectedResponseError(
                "Synology photo list used an unsupported response format."
            )
        result = [self._parse_item(item) for item in raw_items]
        self._items_by_id = {
            item.external_id: item for item in result if item.external_id is not None
        }
        return result

    def _parse_item(self, raw: Any) -> PhotoSourceItem:
        if not isinstance(raw, dict):
            raise SynologyMalformedResponseError("Photo item must be an object.")
        external_id = raw.get("id", raw.get("item_id", raw.get("uuid")))
        name = raw.get("filename", raw.get("name", raw.get("title")))
        if name is None:
            raise SynologyMalformedResponseError("Photo item has no name.")
        additional = raw.get("additional") or {}
        exif = additional.get("exif") or raw.get("exif") or {}
        gps = additional.get("gps") or exif.get("gps") or raw.get("gps") or {}
        taken = raw.get("time", raw.get("taken_at", exif.get("date_time")))
        thumbnail = raw.get("thumbnail_url", raw.get("thumbnail"))
        if thumbnail is None:
            thumbnail = additional.get("thumbnail")
        if isinstance(thumbnail, dict):
            thumbnail = next((
                thumbnail.get(key) for key in ("url", "path", "cache_key", "id")
                if thumbnail.get(key) is not None
            ), None)
        return PhotoSourceItem(
            external_id=str(external_id) if external_id is not None else None,
            name=str(name), taken_at=self._parse_datetime(taken),
            latitude=self._number(gps.get("latitude", raw.get("latitude"))),
            longitude=self._number(gps.get("longitude", raw.get("longitude"))),
            altitude=self._number(gps.get("altitude", raw.get("altitude"))),
            source_url=raw.get("url", raw.get("source_url")),
            thumbnail_url=str(thumbnail) if thumbnail is not None else None,
            metadata=raw,
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, timezone.utc)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def get_photo_metadata(self, external_id: str) -> dict[str, Any]:
        item = self._items_by_id.get(external_id)
        if item is None:
            raise KeyError(external_id)
        return dict(item.metadata)

    def get_thumbnail(self, item: PhotoSourceItem) -> str | None:
        return item.thumbnail_url

    def get_original_reference(self, item: PhotoSourceItem) -> str | None:
        return item.source_url
