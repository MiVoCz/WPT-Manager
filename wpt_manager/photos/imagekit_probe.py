"""Read-only diagnostics: python -m wpt_manager.photos.imagekit_probe."""

import argparse
import base64
import json
import os
import re
from typing import Any

from wpt_manager.photos.imagekit import ImageKitError, ImageKitPhotoSource, embedded_value


def redact_metadata(value: Any, private_key: str = "") -> Any:
    """Sanitize nested diagnostic values, including secrets echoed by a provider."""
    sensitive = re.compile(
        r"key|secret|token|auth|cookie|password|credential|session|signature", re.I
    )
    if isinstance(value, dict):
        return {
            str(redact_metadata(key, private_key)): (
                "[REDACTED]" if sensitive.search(str(key))
                else redact_metadata(child, private_key)
            ) for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_metadata(child, private_key) for child in value]
    if isinstance(value, str):
        if private_key:
            for secret in (private_key, base64.b64encode((private_key + ":").encode()).decode()):
                value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\b(?:Basic|Bearer)\s+\S+", "[REDACTED]", value)
        value = re.sub(
            r"(?i)(?:[\w-]*(?:key|secret|token|auth|cookie|password|credential|session|signature)[\w-]*)"
            r"\s*[:=]\s*[^\s,;]+", "[REDACTED]", value,
        )
        # Delivery URLs can contain signed query parameters or user information.
        value = re.sub(r"(https?://)[^/\s]*@", r"\1[REDACTED]@", value)
        value = re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1?[REDACTED]", value)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only ImageKit Media Library probe")
    parser.add_argument("--folder", help="Exact folder path; subfolders are not included")
    parser.add_argument("--debug-metadata", action="store_true")
    args = parser.parse_args(argv)
    key = os.environ.get("IMAGEKIT_PRIVATE_KEY", "")

    def output(label: str, value: Any) -> None:
        print(f"{label}: {redact_metadata(value, key)}")

    try:
        source = ImageKitPhotoSource(folder=args.folder)
        items = source.list_photos()
    except ImageKitError as exc:
        output("ImageKit connection", "FAILED")
        output("Folder", args.folder or "All folders")
        output("Assets found", "unavailable")
        output("Images found", "unavailable")
        output("Error", str(exc))
        return 1
    output("ImageKit connection", "OK")
    output("Folder", args.folder or "All folders")
    output("Assets found", source.assets_found)
    output("Images found", len(items))
    for index, item in enumerate(items[:5], 1):
        print(f"\nPhoto {index}:")
        raw = item.metadata
        embedded = raw.get("embeddedMetadata")
        custom = raw.get("customMetadata")
        fields = {
            "fileId": item.external_id, "name": item.name,
            "mime/type": raw.get("mimeType") or raw.get("mime") or embedded_value(embedded, "MIMEType") or raw.get("fileType"),
            "size": raw.get("size"), "width": raw.get("width"), "height": raw.get("height"),
            "url": item.source_url, "thumbnail": item.thumbnail_url,
            "taken_at": item.taken_at, "latitude": item.latitude,
            "longitude": item.longitude, "altitude": item.altitude,
            "camera make": embedded_value(embedded, "Make"),
            "camera model": embedded_value(embedded, "Model"),
            "lens": embedded_value(embedded, "LensModel"),
            "ISO": embedded_value(embedded, "ISOSpeedRatings", "ISO", "PhotographicSensitivity"),
            "aperture": embedded_value(embedded, "FNumber"),
            "aperture value": embedded_value(embedded, "ApertureValue"),
            "altitude reference": embedded_value(embedded, "GPSAltitudeRef"),
            "original time offset": embedded_value(embedded, "OffsetTimeOriginal"),
            "exposure": embedded_value(embedded, "ExposureTime"),
            "focal length": embedded_value(embedded, "FocalLength"),
            "embedded metadata keys": list(embedded) if isinstance(embedded, dict) else None,
            "custom metadata keys": list(custom) if isinstance(custom, dict) else None,
        }
        for label, value in fields.items():
            output("  " + label, value)
    if args.debug_metadata and source.first_asset is not None:
        for field in ("embeddedMetadata", "customMetadata"):
            safe = redact_metadata(source.first_asset.get(field), key)
            print(f"\n{field}: {json.dumps(safe, ensure_ascii=True, indent=2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
