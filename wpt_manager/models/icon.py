from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IconInfo:
    group: str
    icon_name: str
    svg_path: Path
