from wpt_manager.map_sources import (
    MAP_SOURCES,
    MAPY_COPYRIGHT_URL,
    OPENSTREETMAP_SOURCE_ID,
    default_map_source_id,
    resolve_map_source,
)


def test_available_map_sources_are_in_ui_order():
    assert [source.label for source in MAP_SOURCES] == [
        "Mapy.com Outdoor",
        "Mapy.com Basic",
        "Mapy.com Aerial",
        "OpenStreetMap",
    ]


def test_mapy_source_without_key_falls_back_to_openstreetmap():
    source, fell_back = resolve_map_source("mapy-outdoor", None)

    assert fell_back
    assert source.id == OPENSTREETMAP_SOURCE_ID
    assert "api.mapy.com" not in source.tile_url
    assert default_map_source_id(None) == OPENSTREETMAP_SOURCE_ID


def test_mapy_source_with_key_uses_official_tiles_endpoint():
    source, fell_back = resolve_map_source("mapy-outdoor", "key with space")

    assert not fell_back
    assert source.id == "mapy-outdoor"
    assert source.tile_url == (
        "https://api.mapy.com/v1/maptiles/outdoor/256/{z}/{x}/{y}"
        "?apikey=key+with+space"
    )
    assert source.mapy_logo_url == "https://api.mapy.com/img/api/logo.svg"
    assert "Seznam.cz a.s. a další" in source.attribution
    assert f'data-external-url="{MAPY_COPYRIGHT_URL}"' in source.attribution
    assert default_map_source_id("configured") == "mapy-outdoor"
