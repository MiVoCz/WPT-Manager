# WPT-Manager

WPT-Manager is a desktop Python/PySide6 application for managing waypoints,
importing GPX files exported by Mapy.com, editing their contents, and exporting
GPX files compatible with OsmAnd. Waypoints can also be created and managed
directly from the map.

## Current features

### Collections

- Import a GPX file into a new Collection or merge it into an existing one.
- Create, rename, edit, delete, and alphabetically list Collections.
- Merge two Collections.
- Detect potential duplicates by geographic distance.
- Resolve merge conflicts with `KEEP_TARGET`, `USE_SOURCE`, or `KEEP_BOTH`.

### Waypoints

- Edit a single waypoint or select multiple waypoints.
- Bulk-edit icon, color, and background for a multi-selection.
- Delete one or multiple waypoints.
- Sort by name or date added.
- Store a short note and a detailed comment.
- Preserve UUID identity, icon, color, and background.
- Validate waypoint names, coordinates, and display values before saving.

### GPX

- Read and write GPX 1.1.
- Read and write OsmAnd `icon`, `color`, and `background` extensions.
- Map waypoint notes to GPX `desc` and comments to GPX `cmt`.
- Export a Collection as an OsmAnd-compatible GPX file.

### Icons

- Load a user-managed SVG catalog from `data/icons`.
- Group icons by directory, with `Favorites` shown first.
- Search and select icons with an SVG picker and preview.
- Preserve unknown icon names when editing and saving waypoints.

### Map

- Open a separate `MapWindow` on demand.
- Display the map with Leaflet.
- Choose Mapy.com Outdoor, Basic, or Aerial tiles, or OpenStreetMap.
- Load the Mapy.com API key from the local `data/config.json` file.
- Display the required Mapy.com or OpenStreetMap attribution.
- Render waypoint markers using their icon, color, and background.
- Synchronize waypoint selection between `MainWindow` and `MapWindow`.
- Create a waypoint by right-clicking the map and choose its target Collection.

### Mapy.com Search

- Search Mapy.com by text.
- Filter results by All, Places, POI, or Addresses.
- Search within the current map or near the selected waypoint.
- Use a configurable radius as the `preferNear` preference.
- Sort results by distance from the current map center or selected waypoint.
- Show a result marker, result details, and formatted distance.
- Open the selected result in Mapy.com.

Saving a Mapy.com search result directly as a waypoint is planned but is not
implemented yet.

## Installation and development

WPT-Manager requires Python 3.14 or newer. On Windows, create a virtual
environment and install the project in editable mode:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Run the application:

```powershell
.\.venv\Scripts\python.exe -m wpt_manager
```

Run the complete test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Configuration

Copy `data/config.example.json` to `data/config.json` and enter a Mapy.com REST
API key:

```json
{
  "mapy_api_key": "your-api-key"
}
```

Never commit a real API key. `data/config.json` is ignored by Git and must
remain local. Without a Mapy.com key, the application can still use
OpenStreetMap; Mapy.com map layers and search require the key.

## Icon catalog

The catalog uses this layout:

```text
data/icons/<group>/*.svg
```

The directory name becomes the group name, and `Favorites` is treated as the
preferred group. The icon name is derived from the SVG filename; an `mx_`
prefix is removed. Users maintain their own catalog—WPT-Manager does not
distribute icons. Not every SVG from OsmAnd resources is necessarily usable as
a waypoint icon in OsmAnd.

## Data

Application data is stored under `data/`. Collections and waypoints are stored
in the SQLite database `data/wpt_manager.db`. The database uses explicit schema
versioning and UUIDs as stable identifiers for Collections and waypoints.

## Known issues

- On Windows with multiple monitors, the first change of a closed Search Type
  combobox after moving `MapWindow` may not repaint its displayed text
  immediately. The selected value and search state are still updated.
- Qt/Windows may print a benign `QWindowsWindow::setGeometry: Unable to set
  geometry` warning while `MapWindow` remains correctly usable.

## Roadmap

- Add a Mapy.com search result as a waypoint.
- Move an existing waypoint from the map.
- Add reverse geocoding when creating a waypoint.
- Add more map context actions.
- Improve the search user experience.

## Project structure

- `wpt_manager/models/` — Collection, waypoint, duplicate, merge, and icon data
  models.
- `wpt_manager/io/` — GPX import/export and icon catalog loading.
- `wpt_manager/validation/` — waypoint validation and geographic duplicate
  detection.
- `wpt_manager/database/` — SQLite persistence, migrations, and Collection
  merge operations.
- `wpt_manager/gui/` — PySide6 windows, dialogs, editors, map, and search UI.
- `tests/` — pytest test suite and test data.
- `data/` — local database, configuration, and user-managed icon catalog.

## License and third-party content

This repository does not currently define its own license.

Mapy.com map content is subject to Mapy.com's terms. OpenStreetMap attribution
must be preserved. Users are responsible for the licensing and permitted use
of icons they place in `data/icons`.
