from wpt_manager.io.icon_catalog import load_icon_catalog
from wpt_manager.models.icon import IconInfo


def test_load_icon_catalog(tmp_path):
    icon_directory = tmp_path / "icons"
    favorites_directory = icon_directory / "Favorites"
    preferred_directory = icon_directory / "favorities"
    custom_directory = icon_directory / "Custom"
    nested_directory = favorites_directory / "Nested"
    favorites_directory.mkdir(parents=True)
    preferred_directory.mkdir()
    custom_directory.mkdir()
    nested_directory.mkdir()

    favorite_icon = favorites_directory / "mx_amenity_fuel.svg"
    favorite_icon.write_text("<svg/>", encoding="utf-8")
    later_favorite_icon = favorites_directory / "mx_tourism_castle.svg"
    later_favorite_icon.write_text("<svg/>", encoding="utf-8")
    custom_icon = custom_directory / "my_custom_icon.svg"
    custom_icon.write_text("<svg/>", encoding="utf-8")
    preferred_icon = preferred_directory / "mx_special_flag.svg"
    preferred_icon.write_text("<svg/>", encoding="utf-8")
    (favorites_directory / "ignored.txt").write_text(
        "ignored",
        encoding="utf-8",
    )
    (nested_directory / "nested.svg").write_text(
        "<svg/>",
        encoding="utf-8",
    )

    catalog = load_icon_catalog(icon_directory)

    assert catalog == [
        IconInfo(
            group="favorities",
            icon_name="special_flag",
            svg_path=preferred_icon,
        ),
        IconInfo(
            group="Custom",
            icon_name="my_custom_icon",
            svg_path=custom_icon,
        ),
        IconInfo(
            group="Favorites",
            icon_name="amenity_fuel",
            svg_path=favorite_icon,
        ),
        IconInfo(
            group="Favorites",
            icon_name="tourism_castle",
            svg_path=later_favorite_icon,
        ),
    ]


def test_load_icon_catalog_from_missing_directory(tmp_path):
    assert load_icon_catalog(tmp_path / "missing") == []
