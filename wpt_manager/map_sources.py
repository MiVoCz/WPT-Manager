from dataclasses import dataclass
from urllib.parse import urlencode


OPENSTREETMAP_SOURCE_ID = "openstreetmap"
MAPY_HOME_URL = "https://mapy.com/"
MAPY_COPYRIGHT_URL = "https://api.mapy.com/copyright"


def _mapy_attribution() -> str:
    return (
        f'<a href="{MAPY_COPYRIGHT_URL}" '
        f'data-external-url="{MAPY_COPYRIGHT_URL}">'
        "Seznam.cz a.s. a další</a>"
    )


@dataclass(frozen=True, slots=True)
class MapSource:
    id: str
    label: str
    tile_url: str
    max_zoom: int
    attribution: str
    requires_mapy_api_key: bool = False
    mapy_logo_url: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedMapSource:
    id: str
    label: str
    tile_url: str
    max_zoom: int
    attribution: str
    mapy_logo_url: str | None


MAP_SOURCES: tuple[MapSource, ...] = (
    MapSource(
        id="mapy-outdoor",
        label="Mapy.com Outdoor",
        tile_url="https://api.mapy.com/v1/maptiles/outdoor/256/{z}/{x}/{y}",
        max_zoom=19,
        attribution=_mapy_attribution(),
        requires_mapy_api_key=True,
        mapy_logo_url="https://api.mapy.com/img/api/logo.svg",
    ),
    MapSource(
        id="mapy-basic",
        label="Mapy.com Basic",
        tile_url="https://api.mapy.com/v1/maptiles/basic/256/{z}/{x}/{y}",
        max_zoom=19,
        attribution=_mapy_attribution(),
        requires_mapy_api_key=True,
        mapy_logo_url="https://api.mapy.com/img/api/logo.svg",
    ),
    MapSource(
        id="mapy-aerial",
        label="Mapy.com Aerial",
        tile_url="https://api.mapy.com/v1/maptiles/aerial/256/{z}/{x}/{y}",
        max_zoom=20,
        attribution=_mapy_attribution(),
        requires_mapy_api_key=True,
        mapy_logo_url="https://api.mapy.com/img/api/logo.svg",
    ),
    MapSource(
        id=OPENSTREETMAP_SOURCE_ID,
        label="OpenStreetMap",
        tile_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        max_zoom=19,
        attribution="&copy; OpenStreetMap contributors",
    ),
)


def get_map_source(source_id: str) -> MapSource:
    for source in MAP_SOURCES:
        if source.id == source_id:
            return source
    raise ValueError(f"Unknown map source: {source_id}")


def default_map_source_id(mapy_api_key: str | None) -> str:
    return "mapy-outdoor" if mapy_api_key else OPENSTREETMAP_SOURCE_ID


def resolve_map_source(
    source_id: str,
    mapy_api_key: str | None,
) -> tuple[ResolvedMapSource, bool]:
    source = get_map_source(source_id)
    fell_back = source.requires_mapy_api_key and not mapy_api_key
    if fell_back:
        source = get_map_source(OPENSTREETMAP_SOURCE_ID)

    tile_url = source.tile_url
    if source.requires_mapy_api_key:
        tile_url = f"{tile_url}?{urlencode({'apikey': mapy_api_key})}"
    return (
        ResolvedMapSource(
            id=source.id,
            label=source.label,
            tile_url=tile_url,
            max_zoom=source.max_zoom,
            attribution=source.attribution,
            mapy_logo_url=source.mapy_logo_url,
        ),
        fell_back,
    )
