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

- Load a user-managed SVG catalog from `icons/` in the user data folder.
- Group icons by directory, with `Favorites` shown first.
- Search and select icons with an SVG picker and preview.
- Preserve unknown icon names when editing and saving waypoints.

### Map

- Open a separate `MapWindow` on demand.
- Display the map with Leaflet.
- Choose Mapy.com Outdoor, Basic, or Aerial tiles, or OpenStreetMap.
- Configure Mapy.com credentials in Settings, using the OS credential store.
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

- Save a Mapy.com search result directly as a waypoint.

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

## Building Windows distribution

The internal Windows build requires Python 3.14 and the test and build extras:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test,build]"
```

Activate that environment and build the windowed `onedir` distribution:

```powershell
.\.venv\Scripts\Activate.ps1
.\packaging\build_windows.ps1
```

Package the existing audited onedir build as an internal test ZIP:

```powershell
.\packaging\package_windows.ps1
```

The audited artifact is created in `dist/WPT-Manager/`. Copy the complete
directory to the target Windows PC. It does not require a separately installed
Python interpreter. The package command creates
`dist/WPT-Manager-0.1.0-win64.zip`. These are internal `onedir` artifacts, not
a public v0.1 release or installer.

## User data folder and configuration

On the first start, WPT-Manager asks where its user data should be stored. The
default is `WPT-Manager` in the user's Documents folder. The selected location
is remembered in platform settings; only the folder path is stored there.

The folder contains:

```text
wpt_manager.db
config.json
icons/
```

The location can later be changed with **Settings > User data folder...**.
When changing it, choose either to use data already present in the selected
folder or to copy the current database, configuration, and icon catalog there.
Existing target data is never replaced without confirmation, and the original
folder is never moved or deleted. The change takes full effect after restarting
WPT-Manager.

Configure the Mapy.com REST API key in **Settings ? Mapy.com... ? API key**.
The shared ImageKit/Mapy.com credential dialog masks input and shows only a fixed
`Saved credential` placeholder for existing keys. Save without editing preserves
the credential. **Remove saved key** deletes it immediately; Cancel does not undo
removal. Windows uses Windows Credential Manager via the existing keyring layer,
service `WPT-Manager`, identifier `mapy_api_key`. No keys go into QSettings.

For development, `MAPY_API_KEY` overrides the stored credential. The complete
priority is nonblank environment value, OS credential store, legacy config, then
not configured. Values are trimmed. A failing OS store does not prevent the env
or legacy fallback from working. Without either fallback, an unavailable store is
reported safely and OpenStreetMap remains usable.

**Test connection** validates newly entered input, otherwise the effective key,
with one asynchronous geocoding request (`query=Praha`, `limit=1`) through the
existing Qt search client. It does not save anything. Results distinguish
Connected, Invalid API key (401/403), Network error and Unexpected API error.
Geocoding success does not guarantee tile permissions: Mapy.com keys can have
[service-specific restrictions](https://developer.mapy.com/new-api-key-security-by-service/).

Legacy `config.json` in the selected user data folder (development default:
`data/config.json`) remains a temporary compatibility fallback. Settings offers
**Import legacy key** only when neither env nor saved key overrides it. Import
saves to the OS store first. A config containing only that key is cleared to `{}`;
a mixed config is left untouched to preserve other values. A visible reminder
explains that you must manually remove its obsolete `mapy_api_key` field. Until
removed, that field remains a fallback even after deleting the saved credential.
A failed credential write leaves the legacy file intact. Missing, malformed or
unreadable legacy files are treated as unconfigured. New configs and the packaged
example contain `{}`; never put new keys in config files or commit real keys.

Map tiles and search use the same resolver and user data path, including frozen
apps. Settings changes refresh an already open map/search window. Selecting
Mapy.com without a key leaves the current provider active and displays guidance
to Settings. Removing the active Mapy.com credential falls back to OSM unless an
env/legacy key remains. Invalid tile credentials show the existing tile failure
indicator; use Test connection for authentication diagnostics. Authenticated tile
URLs remain in WebEngine memory and are excluded from application diagnostics;
generated HTML is not written to disk. No new dependency or PyInstaller change is
required. A release build and live API/OS-store round trip require manual testing.

## Icon catalog

The catalog uses this layout:

```text
<user data folder>/icons/<group>/*.svg
```

The directory name becomes the group name, and `Favorites` is treated as the
preferred group. The icon name is derived from the SVG filename; an `mx_`
prefix is removed. Users maintain their own catalog—WPT-Manager does not
distribute icons. Not every SVG from OsmAnd resources is necessarily usable as
a waypoint icon in OsmAnd.

## Data

Collections, waypoints, Tracks, Adventures, and Photo records are stored in
`wpt_manager.db` in the selected user data folder. The database uses explicit
schema versioning and UUIDs as stable identifiers.

### Photos development notes

A Photo is a metadata record referencing a local or remote image. A Standalone
Photo has no assigned Track (`track_uuid` is null). Photos never store a direct
Adventure relationship: Adventure names are derived through the assigned Track
and the existing many-to-many `adventure_tracks` relationship. Deleting a Track
therefore keeps its Photos and makes them Standalone.

Remote providers implement the `PhotoSource` protocol and return neutral
`PhotoSourceItem` values. The GUI, database model, and import service do not
depend on provider response objects. ImageKit is the supported external import
in the Photos GUI. Synology import controls and dialogs have been removed;
existing Synology Photos remain readable, editable and eligible for previews.
The retained developer-only `SynologyPhotoSource` supports
password-protected shared links through an isolated HTTP transport and response
parser; no password, token, or cookie is persisted.

To inspect a specific NAS response without modifying the database, run:

```powershell
python -m wpt_manager.photos.synology_probe --debug --nas-url "https://nas.example:5001" "https://quickconnect-id.quickconnect.to/mo/sharing/token"
```

The password is requested with `getpass` and is not printed. A direct NAS share
URL supplies its API host automatically. A QuickConnect-only web address is not
used as a DSM API endpoint; its share ID must be paired with an explicit NAS or
DDNS address. Synology Photos API details can vary by DSM/Photos release, so the
provider transport and parser remain separate for adaptation to real responses.

## ImageKit setup (read-only developer integration)

Use a restricted **read-only private API key** with permission to list Media
Library files. Set it in the current PowerShell session; never commit the key
or put it in `config.json`:

```powershell
$env:IMAGEKIT_PRIVATE_KEY="private_xxx"
python -m wpt_manager.photos.imagekit_probe --folder "/ITA_2026/"
python -m wpt_manager.photos.imagekit_probe --folder "/ITA_2026/" --debug-metadata
```

The probe only reads remote data and never opens or changes the local database.
It prints asset/image counts and up to five photos. Debug mode prints sanitized
`embeddedMetadata` and `customMetadata` from the first asset, even if it is not
an image. Review diagnostics before sharing: camera, GPS and other descriptive
metadata are intentionally visible; credentials, token fields and URL queries
are redacted.

`wpt_manager.photos.imagekit.ImageKitPhotoSource` uses Basic authentication
(private key as username, empty password) against `GET https://api.imagekit.io/v1/files`.
`IMAGEKIT_URL_ENDPOINT` is not required. An explicit constructor `private_key`
takes precedence over the resolver; `None` uses the environment then OS credential store, and an empty
key raises `ImageKitAuthenticationError`. HTTP redirects are rejected.

Folder filtering uses the official `path` parameter (exact folder, no recursive
subfolders). Omit `folder` to list all folders. `page_size` (1–1000, default 1000)
controls API `limit`; `skip` advances until the final page. `timeout` defaults to
15 seconds per request. Assets found counts returned files before image filtering;
images found counts unique mapped images. Folders, videos and unidentified files
are skipped. HEIC/HEIF are accepted when provider image type/MIME identifies them;
no image decoding is performed.

Mapping preserves `fileId`, name, delivery URLs and raw metadata, including size,
dimensions, camera EXIF and custom metadata. `DateTimeOriginal` accepts EXIF and
ISO datetime formats. A timezone-free original time uses `OffsetTimeOriginal`
when valid; the resulting offset is preserved, matching Photo persistence.
ISO timestamps with `Z` stay UTC. Without a valid offset the time stays naive;
no upload timestamp is substituted. GPS supports decimal values and three DMS
components (numeric or rational strings). S/W references supply a missing minus
sign without reversing an already negative coordinate. Altitude references accept
numeric/string 0/1 and `Above Sea Level` / `Below Sea Level` (case-insensitive).
Missing or invalid values remain `None`. Flat and grouped EXIF dictionaries are
supported. The official [list API](https://imagekit.io/docs/api-reference/digital-asset-management-dam/list-and-search-assets)
and [DAM examples](https://imagekit.io/docs/dam/overview) document the response;
actual GPS/EXIF contents depend on the asset. A user-run probe verified a live
collection of 55 assets/images, including decimal GPS coordinates, numeric
altitude, textual altitude references and original time offsets. Automated tests
use mocked HTTP; use the debug probe to inspect other collections.

The existing `import_source_items(database, source, selected_items)` service can
save selected items locally with `source_type="imagekit"`, `external_id=fileId`
and `track_uuid=None`. The existing database uniqueness constraint prevents
duplicates. Provider metadata stays in `PhotoSourceItem`; the existing `Photo`
database model has no raw-metadata field. No schema change is needed.

In **Photos → Import from ImageKit...**, enter a folder (default `/`), click
**Load**, select one or more images and click **Import**. The result reports
`Imported: N` and `Skipped duplicates: N`. The dialog uses the environment key;
it does not store credentials in the database or display provider error details.
Changing the folder clears the previous selection. A missing `thumbnailUrl`
stays `None` in the database.

The Photo editor loads previews asynchronously with `QNetworkAccessManager`.
It prefers `thumbnail_url`, otherwise `source_url`. For ImageKit without a
thumbnail, `build_imagekit_preview_url` adds a delivery query transformation
`tr=w-600,h-400,c-at_max`, preserving other query parameters and chaining any
existing query transformation. ImageKit's
[max-size transformation](https://imagekit.io/docs/image-resize-and-crop)
preserves aspect ratio without cropping. No transformed file is stored.
Local file URLs/absolute paths and legacy Synology URLs are also supported.

Selection changes abort pending requests and ignore stale replies. Each editor
keeps up to 32 downscaled previews in memory; resizing only rescales the cached
pixmap. Downloads have a 15-second timeout and a 10 MiB size limit. Failures show
a generic status without exposing URLs or credentials. There is no disk cache.
Signed URLs may reject added transformations if their signatures cover the
transformation; the application does not re-sign URLs or fall back to downloading
ImageKit originals. Preview format support depends on the installed Qt codecs.

Uploads, remote edits/deletes, video, disk thumbnail cache, track
matching and background synchronization are not implemented. Listing is
synchronous, keeps mapped metadata in memory, and has no automatic retry or
snapshot guarantee if the library changes during offset pagination.

## Bulk manual Photo assignment

The Photos table supports Ctrl/Shift selection and Ctrl+A for all visible rows.
One selected Photo uses the full editor. With multiple Photos selected, only
Track assignment is enabled; metadata is cleared and the preview request is
cancelled. No selection clears and disables the editor.

The Track combo shows the common assignment, or **Multiple values** for mixed
assignments. Mixed values require choosing Standalone or a Track before
**Apply to Selected** is enabled. Changing the combo alone never saves changes.
Apply changes only `track_uuid` for selected Photo UUIDs in one database
transaction, including explicitly replacing existing assignments. Standalone
stores NULL. A status-bar message reports the affected count.

After refreshing the model and filters, selection is restored only for UUIDs
still visible. Photos excluded by the new Track/Adventure/Standalone filter
are deselected. Bulk name, description and other metadata editing is not supported.

## Match Photos to Tracks

In Photos, **Match Photos to Tracks** evaluates all locally stored Photos against
all Tracks (independent of table filters and Track visibility). A summary shows
scanned, matched, ambiguous, no-match, already-assigned and no-timestamp counts.
**Cancel** writes nothing; **Apply** saves only unambiguous matches, then refreshes
the Photos table and its derived Track/Adventure labels once. Existing assignments
are skipped, including assignments made after the preview was computed.

`wpt_manager/photos/photo_track_matcher.py` contains the pure matcher. It indexes
actual timed Track points once, derives ranges from them, and uses `bisect` for
nearest timestamp lookup. Track header dates alone are not sufficient. Primary
ranking is absolute time difference from Photo `taken_at` (ImageKit
`DateTimeOriginal`), followed by GPS distance when available and Track UUID.
The existing geographic distance helper supplies haversine distances.

Default limits are named constants: Track time margin **300 seconds**, nearest
point delta **300 seconds**, GPS distance **2000 meters**. When another candidate
is within **10 seconds** of the best time delta and, when GPS is available,
within **100 meters** of its distance, the result is ambiguous and stays unchanged.
An exact UUID tie-break never overrides this ambiguity safeguard. GPS only
validates the nearest timed point(s); it cannot select a more distant timestamp.

Comparisons normalize timezone-aware values to UTC without changing persisted
timestamps. Missing, malformed or naive photo times yield `No timestamp`; unsafe
Track point times are ignored. Missing Photo GPS permits time-only matching;
partial/invalid Photo GPS is conservatively rejected. With valid Photo GPS,
a candidate needs valid GPS on a nearest timed point. No coordinates are inferred
or interpolated. Uncertain Standalone Photos remain Standalone.

The `photos/auto_assign.py` helpers separate preview from persistence, use the
existing Database API, and default to `overwrite_existing=False`. Explicit helper
callers can enable replacement; the GUI does not. Matching uses local metadata
only and makes no network calls. Manual assignment remains available.

Limitations: fixed thresholds, no camera-clock correction, no interpolation, and
no assignment provenance beyond whether a Track is already assigned. Indexing and
matching run synchronously; nearest lookup is O(log N) per candidate Track, while
range filtering visits each Track. Applying uses individual existing database
updates, so a database failure can leave earlier successful assignments saved;
the GUI reports the error and refreshes the table for review.

## Known issues

- On Windows with multiple monitors, the first change of a closed Search Type
  combobox after moving `MapWindow` may not repaint its displayed text
  immediately. The selected value and search state are still updated.
- Qt/Windows may print a benign `QWindowsWindow::setGeometry: Unable to set
  geometry` warning while `MapWindow` remains correctly usable.

### Main window activation from MapWindow on Windows

When **Edit waypoint** is selected from a marker context menu, the correct
waypoint is selected in `MainWindow` and its editor is updated. If `MainWindow`
is covered by a maximized `MapWindow`, however, Windows may not bring
`MainWindow` to the foreground automatically. The user must switch to
`MainWindow` manually in that case.

This is a known Windows limitation affecting only activation and stacking of
the top-level windows. Waypoint selection and editing are not affected.

## Roadmap

- Add reverse geocoding when creating a waypoint.
- Add more map context actions.
- Improve the search user experience.

## Project structure

- `wpt_manager/models/` — Collection, waypoint, Track, Adventure, Photo,
  duplicate, merge, and icon data models.
- `wpt_manager/photos/` — provider-neutral PhotoSource API, source-item import,
  Synology shared-link and ImageKit read-only providers, and diagnostic probes.
- `wpt_manager/io/` — GPX import/export and icon catalog loading.
- `wpt_manager/validation/` — waypoint validation and geographic duplicate
  detection.
- `wpt_manager/database/` — SQLite persistence, migrations, and Collection
  merge operations.
- `wpt_manager/gui/` — PySide6 windows, dialogs, editors, map, and search UI.
- `tests/` — pytest test suite and test data.
- `data/` — local database, configuration, and user-managed icon catalog.

## License and third-party content

WPT-Manager is licensed under the [MIT License](LICENSE).

Mapy.com map content is subject to Mapy.com's terms. OpenStreetMap attribution
must be preserved. Users are responsible for the licensing and permitted use
of icons they place in the `icons/` directory of their user data folder.


## ImageKit credentials

Open **Settings ? ImageKit... ? Private API key**. The input is masked;
existing credentials appear only as a fixed `Saved credential` placeholder.
Save stores a new, trimmed key in the OS credential store (Windows Credential
Manager on Windows), under service `WPT-Manager`, username `imagekit_private_key`.
Saving without editing preserves the saved key; **Remove saved key** deletes it
immediately (Cancel does not undo removal). Secrets are never stored in config.json
or QSettings.

**Test connection** tests a newly entered key, otherwise the effective credential,
using one authorized list-files request (limit 1) in a worker thread. It does not
save the key. Results distinguish Connected, Invalid API key, Network error and
Unexpected API error. An unavailable OS store is reported without backend details.

Development and the CLI probe can still use `IMAGEKIT_PRIVATE_KEY`.
A nonblank environment variable overrides the stored credential; whitespace-only
values are ignored. The dialog indicates this override without displaying the value.
Both ImageKit import and `python -m wpt_manager.photos.imagekit_probe` use this
same resolver. No database migration is needed.


The project's PyInstaller keyring hook collects backend modules and keyring
metadata. The native Windows backend is also explicitly imported by the credential
store; no additional spec customization is needed. A frozen build and a real
Credential Manager round trip still require manual verification.
