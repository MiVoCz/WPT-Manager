from pathlib import Path

from wpt_manager.models.icon import IconInfo
from wpt_manager.paths import ICONS_DIRECTORY


DEFAULT_ICON_DIRECTORY = ICONS_DIRECTORY


def load_icon_catalog(
    path: str | Path = DEFAULT_ICON_DIRECTORY,
) -> list[IconInfo]:
    icon_directory = Path(path)
    if not icon_directory.is_dir():
        return []

    catalog: list[IconInfo] = []
    group_directories = sorted(
        (
            entry
            for entry in icon_directory.iterdir()
            if entry.is_dir()
        ),
        key=lambda entry: (
            entry.name.casefold() != "favorities",
            entry.name.casefold(),
            entry.name,
        ),
    )

    for group_directory in group_directories:
        svg_files = sorted(
            (
                entry
                for entry in group_directory.iterdir()
                if entry.is_file() and entry.suffix.lower() == ".svg"
            ),
            key=lambda entry: (entry.name.casefold(), entry.name),
        )

        for svg_file in svg_files:
            icon_name = svg_file.stem
            if icon_name.startswith("mx_"):
                icon_name = icon_name.removeprefix("mx_")

            catalog.append(
                IconInfo(
                    group=group_directory.name,
                    icon_name=icon_name,
                    svg_path=svg_file,
                )
            )

    return catalog
