import argparse
import getpass
from urllib.parse import urlparse

from wpt_manager.photos.source import PhotoSourceError
from wpt_manager.photos.synology import (
    SynologyHttpDiagnostic, SynologyPhotoSource,
)


def print_http_diagnostic(item: SynologyHttpDiagnostic) -> None:
    print("\nREQUEST:")
    print(f"  operation: {item.operation}")
    print(f"  method: {item.method}")
    print(f"  URL: {item.request_url}")
    print("RESPONSE:")
    print(f"  status: {item.status}")
    print(f"  Content-Type: {item.content_type or 'unavailable'}")
    print(f"  final URL: {item.final_url}")
    print(f"  redirect count: {item.redirect_count}")
    print(f"  response type: {item.response_type}")
    if item.body_prefix is not None:
        print(f"  body prefix: {item.body_prefix}")
    if item.operation == "sharing-login":
        print("Sharing login:")
        print(f"  status: {item.status}")
        print(f"  JSON: {'yes' if item.response_type == 'JSON' else 'no'}")
    if item.operation == "list-shared-photos":
        print("List shared photos:")
        print(f"  status: {item.status}")


def print_resolution(source: SynologyPhotoSource) -> None:
    print(f"Connection type: {source.connection_type}")
    print(f"Share ID: {source.parse_share_id(source.original_share_url)}")
    print(f"NAS API base: {source.api_base_url}")
    print(f"Original host: {urlparse(source.original_share_url).hostname}")
    print(f"Sharing login success: {'yes' if source.sharing_login_success else 'no'}")
    print(f"Sharing session available: {'yes' if source.sharing_session_available else 'no'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a Synology Photos share")
    parser.add_argument("share_url", nargs="?")
    parser.add_argument("--nas-url")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--debug", action="store_true", help="print safe HTTP flow diagnostics"
    )
    arguments = parser.parse_args()
    share_url = arguments.share_url or input("Share URL: ").strip()
    nas_url = arguments.nas_url
    if nas_url is None:
        nas_url = input("NAS/DDNS address (optional for direct share URL): ").strip()
    password = getpass.getpass("Password (leave empty if none): ")
    try:
        source = SynologyPhotoSource(
            share_url, password, nas_api_base_url=nas_url or None,
            diagnostic_callback=print_http_diagnostic if arguments.debug else None,
        )
    except PhotoSourceError as exc:
        print("Connected: no")
        print(f"Error: {exc}")
        return 1
    print(f"Connection type: {source.connection_type}")
    print(f"Original host: {urlparse(source.original_share_url).hostname}")
    try:
        items = source.list_photos()
    except PhotoSourceError as exc:
        print_resolution(source)
        print("Connected: no")
        print(f"Error: {exc}")
        return 1
    print_resolution(source)
    print("Connected: yes")
    print(f"Items: {len(items)}")
    for number, item in enumerate(items[:max(arguments.limit, 0)], 1):
        additional = item.metadata.get("additional") or {}
        exif = additional.get("exif") or item.metadata.get("exif") or {}
        resolution = additional.get("resolution") or item.metadata.get("resolution")
        thumbnail = additional.get("thumbnail") or item.thumbnail_url
        print(f"\nPhoto {number}:")
        for label, value in (
            ("id", item.external_id), ("filename", item.name),
            ("taken_at", item.taken_at), ("latitude", item.latitude),
            ("longitude", item.longitude), ("altitude", item.altitude),
            ("resolution", resolution), ("camera", exif.get("camera")),
            ("lens", exif.get("lens")),
            ("thumbnail available", bool(thumbnail)),
        ):
            print(f"  {label}: {value if value is not None else 'unavailable'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
