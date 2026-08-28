import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QTextEdit,
)

from wpt_manager.database.database import Database
from wpt_manager.database.collection_merge import merge_collections
from wpt_manager.config import ApplicationConfig
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.gui.map_window import MapWindow, format_distance_m
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_reader import load_gpx
from wpt_manager.io.gpx_importer import import_gpx
from wpt_manager.models.collection import Collection
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.mapy_search import MapSearchResult


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


class FakeSearchClient(QObject):
    results_ready = Signal(list)
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self.calls = []

    @property
    def is_available(self):
        return True

    def search(self, query, **options):
        self.calls.append((query, options))


def test_main_window_defaults(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database, icon_catalog=[])

    assert window.windowTitle() == "WPT-Manager"
    assert window.size().width() == 1000
    assert window.size().height() == 700
    assert window.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.main_splitter.count() == 2
    assert window.map_window is None
    assert window.right_splitter.orientation() == Qt.Orientation.Vertical
    assert window.right_splitter.count() == 2

    assert isinstance(window.name_edit, QLineEdit)
    assert isinstance(window.icon_edit, QLineEdit)
    assert window.icon_preview.width() == 32
    assert window.icon_preview.height() == 32
    assert window.icon_button.text() == "Select..."
    assert isinstance(window.color_edit, QLineEdit)
    assert window.color_preview.width() == 24
    assert window.color_preview.height() == 24
    assert isinstance(window.background_combo, QComboBox)
    assert [
        window.background_combo.itemText(index)
        for index in range(window.background_combo.count())
    ] == ["circle", "square", "octagon"]
    assert window.background_combo.isEditable()
    assert isinstance(window.latitude_edit, QLineEdit)
    assert window.latitude_edit.isReadOnly()
    assert isinstance(window.longitude_edit, QLineEdit)
    assert window.longitude_edit.isReadOnly()
    assert isinstance(window.note_edit, QLineEdit)
    assert isinstance(window.comment_edit, QTextEdit)

    assert window.import_button.text() == "Import GPX"
    assert window.export_button.text() == "Export GPX"
    assert not window.export_button.isEnabled()
    assert window.delete_collection_button.text() == "Delete Collection"
    assert not window.delete_collection_button.isEnabled()
    assert window.merge_collections_button.text() == "Merge Collections..."
    assert not window.merge_collections_button.isEnabled()
    assert window.delete_waypoints_button.text() == "Delete Waypoint(s)"
    assert not window.delete_waypoints_button.isEnabled()
    assert window.color_button.text() == "Choose color"
    assert window.save_button.text() == "Save"
    assert not window.save_button.isEnabled()
    assert window.collection_list.count() == 0
    assert window.waypoint_list.selectionMode() == (
        QAbstractItemView.SelectionMode.ExtendedSelection
    )
    assert [
        window.waypoint_sort_combo.itemText(index)
        for index in range(window.waypoint_sort_combo.count())
    ] == ["Name", "Added"]
    assert window.waypoint_sort_combo.currentData() == "name"

    window.close()
    application.processEvents()


def test_open_map_creates_one_reusable_map_window(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database, icon_catalog=[])

    window.open_map_button.click()
    map_window = window.map_window

    assert isinstance(map_window, MapWindow)
    assert map_window.isVisible()

    window.open_map_button.click()

    assert window.map_window is map_window
    assert map_window.isVisible()

    map_window.close()
    window.close()
    application.processEvents()


def test_closed_map_window_can_be_opened_again(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    window.open_map()
    map_window = window.map_window
    assert map_window is not None

    map_window.close()
    application.processEvents()

    assert window.map_window is None
    assert window.load_collections()

    window.open_map()

    assert window.map_window is not None
    assert window.map_window is not map_window
    assert window.map_window.isVisible()

    window.map_window.close()
    window.close()
    application.processEvents()


def test_map_window_defaults_and_fallback_follow_api_key_configuration():
    application = QApplication.instance() or QApplication([])
    without_key = MapWindow(config=ApplicationConfig())
    with_key = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key")
    )

    assert without_key.map_source_combo.currentData() == "openstreetmap"
    assert "API key is not configured" in without_key.map_source_status.text()
    assert with_key.map_source_combo.currentData() == "mapy-outdoor"
    assert with_key.map_source_status.text() == ""
    assert not without_key.search_button.isEnabled()
    assert "requires a configured API key" in without_key.search_status.text()
    assert with_key.search_button.isEnabled()

    mapy_basic_index = without_key.map_source_combo.findData("mapy-basic")
    without_key.map_source_combo.setCurrentIndex(mapy_basic_index)

    assert without_key.map_source_combo.currentData() == "openstreetmap"
    assert without_key.waypoint_map._map_source_payload["id"] == (
        "openstreetmap"
    )

    without_key.close()
    with_key.close()
    application.processEvents()


def test_map_window_search_panel_is_regular_child_in_central_splitter():
    application = QApplication.instance() or QApplication([])
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key")
    )

    central_widget = window.centralWidget()
    splitters = central_widget.findChildren(
        QSplitter,
        options=Qt.FindChildOption.FindDirectChildrenOnly,
    )

    assert len(splitters) == 1
    splitter = splitters[0]
    assert splitter.count() == 2
    assert splitter.widget(0) is window.waypoint_map
    assert window.waypoint_map.parentWidget() is splitter
    assert splitter.widget(1).isAncestorOf(window.search_type_combo)
    assert splitter.widget(1).minimumWidth() == 280
    assert window.search_type_combo.window() is window
    assert window.findChildren(QDockWidget) == []
    assert window.waypoint_map.sizePolicy().horizontalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    assert window.waypoint_map.sizePolicy().verticalPolicy() == (
        QSizePolicy.Policy.Expanding
    )
    assert window.waypoint_map.minimumSize().width() == 300
    assert window.waypoint_map.minimumSize().height() == 300

    window.close()
    application.processEvents()


def test_map_window_shows_empty_search_results():
    application = QApplication.instance() or QApplication([])
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key")
    )

    window._show_search_results([])

    assert window.search_results.count() == 0
    assert window.search_status.text() == "No results"
    assert not window.add_search_result_button.isEnabled()

    window.close()
    application.processEvents()


def test_map_window_near_search_uses_selected_waypoint_and_radius():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    waypoint = Waypoint(name="Anchor", latitude=50.123, longitude=14.456)
    window.set_search_waypoint(waypoint)
    window.search_type_combo.setCurrentIndex(
        window.search_type_combo.findText("POI")
    )
    window.search_area_combo.setCurrentIndex(
        window.search_area_combo.findData("near-waypoint")
    )
    window.search_radius_combo.setCurrentIndex(
        window.search_radius_combo.findData(10_000)
    )
    window.search_edit.setText("restaurant")

    window._start_search()

    assert search_client.calls == [
        (
            "restaurant",
            {
                "result_types": ("poi",),
                "prefer_near": (14.456, 50.123),
                "prefer_near_precision": 10_000,
            },
        )
    ]
    assert "preference" in window.search_status.text()

    window.close()
    application.processEvents()


def test_search_results_are_sorted_by_distance_from_map_center():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    window._set_viewport_bbox(13.0, 49.0, 15.0, 51.0)
    window.search_edit.setText("places")
    window._start_search()

    window._show_search_results(
        [
            MapSearchResult("Far", "Place", 50.1, 14.0),
            MapSearchResult("Near", "Place", 50.01, 14.0),
        ]
    )

    assert [
        window.search_results.item(index).data(Qt.ItemDataRole.UserRole).name
        for index in range(window.search_results.count())
    ] == ["Near", "Far"]

    window.close()
    application.processEvents()


def test_search_results_are_sorted_by_distance_from_selected_waypoint():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    window.set_search_waypoint(
        Waypoint(name="Anchor", latitude=49.0, longitude=13.0)
    )
    window.search_area_combo.setCurrentIndex(
        window.search_area_combo.findData("near-waypoint")
    )
    window.search_edit.setText("places")
    window._start_search()

    window._show_search_results(
        [
            MapSearchResult("Map center", "Place", 50.0, 14.0),
            MapSearchResult("Waypoint", "Place", 49.01, 13.0),
        ]
    )

    first_result = window.search_results.item(0).data(
        Qt.ItemDataRole.UserRole
    )
    assert first_result.name == "Waypoint"
    assert first_result.distance_m is not None

    window.close()
    application.processEvents()


@pytest.mark.parametrize(
    ("distance_m", "formatted"),
    [(320.4, "320 m"), (1_400.0, "1.4 km"), (12_700.0, "12.7 km")],
)
def test_search_result_distance_format(distance_m, formatted):
    assert format_distance_m(distance_m) == formatted


def test_equidistant_search_results_are_sorted_deterministically_by_name():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    window._set_viewport_bbox(13.0, 49.0, 15.0, 51.0)
    window.search_edit.setText("places")
    window._start_search()

    window._show_search_results(
        [
            MapSearchResult("Zulu", "Place", 50.01, 14.0),
            MapSearchResult("Alpha", "Place", 50.01, 14.0),
        ]
    )

    assert [
        window.search_results.item(index).data(Qt.ItemDataRole.UserRole).name
        for index in range(window.search_results.count())
    ] == ["Alpha", "Zulu"]

    window.close()
    application.processEvents()


def test_search_type_change_updates_immediately_and_is_used():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    places_index = window.search_type_combo.findText("Places")
    window.show()
    application.processEvents()
    initial_render = window.search_type_combo.grab().toImage()

    window.search_type_combo.setCurrentIndex(places_index)
    application.processEvents()

    assert window.search_type_combo.currentText() == "Places"
    assert window.search_type_combo.grab().toImage() != initial_render
    assert window._search_result_types == (
        "regional.municipality",
        "regional.municipality_part",
    )

    window.search_edit.setText("Hatě")
    window._start_search()

    assert search_client.calls[0][1]["result_types"] == (
        "regional.municipality",
        "regional.municipality_part",
    )

    window.close()
    application.processEvents()


def test_open_selected_search_result_uses_external_mapy_url(monkeypatch):
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )
    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    result = MapSearchResult(
        name="Petřínská rozhledna",
        label="Rozhledna",
        latitude=50.0835,
        longitude=14.3952,
        location="Praha, Česko",
        entity_type="poi",
    )
    window._show_search_results([result])
    assert not window.add_search_result_button.isEnabled()
    window.search_results.setCurrentRow(0)

    assert window.add_search_result_button.isEnabled()
    window.open_search_result_button.click()

    assert opened_urls == [
        "https://mapy.com/fnc/v1/showmap?"
        "center=14.3952,50.0835&zoom=16&marker=true"
    ]

    window.close()
    application.processEvents()


def test_add_search_result_saves_selects_and_updates_active_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    existing = Waypoint(name="Existing", latitude=49.0, longitude=13.0)
    database.save_waypoint(existing, collection.id)
    result = MapSearchResult(
        name="Petřínská rozhledna",
        label="Rozhledna",
        latitude=50.0835,
        longitude=14.3952,
        location="Praha, Česko",
    )
    created = Waypoint(
        name=result.name,
        latitude=result.latitude,
        longitude=result.longitude,
        note=result.label,
        comment=result.location or "",
    )

    class AcceptedWaypointDialog:
        def __init__(
            self,
            latitude,
            longitude,
            icon_catalog,
            collections,
            selected_collection_id,
            parent,
            **initial_values,
        ):
            assert latitude == result.latitude
            assert longitude == result.longitude
            assert selected_collection_id == collection.id
            assert collections == [(collection.id, "Places")]
            assert initial_values == {
                "name": result.name,
                "note": result.label,
                "comment": result.location,
            }
            assert parent.map_window is not None
            assert parent.map_window._selected_search_result is result
            assert parent._map_waypoints == [existing]
            self.waypoint = created
            self.collection_id = collection.id

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.NewWaypointDialog",
        AcceptedWaypointDialog,
    )
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()
    assert window.map_window is not None
    window.map_window._show_search_results([result])
    window.map_window.search_results.setCurrentRow(0)
    map_window = window.map_window
    sync_calls = []
    original_set_waypoints = map_window.set_waypoints
    original_set_selected = map_window.set_selected_waypoint_ids
    original_clear_search_marker = map_window.clear_search_result_marker
    monkeypatch.setattr(
        map_window,
        "set_waypoints",
        lambda waypoints, fit_viewport=True: (
            sync_calls.append(("dataset", [item.id for item in waypoints])),
            original_set_waypoints(waypoints, fit_viewport),
        )[-1],
    )
    monkeypatch.setattr(
        map_window,
        "set_selected_waypoint_ids",
        lambda waypoint_ids: (
            sync_calls.append(("selection", list(waypoint_ids))),
            original_set_selected(waypoint_ids),
        )[-1],
    )
    monkeypatch.setattr(
        map_window,
        "clear_search_result_marker",
        lambda: (
            sync_calls.append(("clear-search", None)),
            original_clear_search_marker(),
        )[-1],
    )

    window.map_window.add_search_result_button.click()

    stored = database.get_waypoint(created.id)
    assert stored == created
    assert stored.id == created.id
    assert stored.id != existing.id
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == collection.id
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == created.id
    assert {waypoint.id for waypoint in window._map_waypoints} == {
        existing.id,
        created.id,
    }
    assert window.map_window.selected_waypoint_ids == [created.id]
    assert window.map_window._selected_search_result is result
    assert window.map_window.waypoint_map._search_result_payload is None
    dataset_call = next(
        index
        for index, call in enumerate(sync_calls)
        if call[0] == "dataset"
        and set(call[1]) == {created.id, existing.id}
    )
    selection_call = next(
        index
        for index, call in enumerate(sync_calls)
        if call == ("selection", [created.id])
    )
    clear_call = sync_calls.index(("clear-search", None))
    assert dataset_call < selection_call < clear_call
    assert window.map_window is map_window

    window.map_window.close()
    window.close()
    application.processEvents()


def test_add_search_result_to_other_collection_keeps_active_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    active = Collection(name="Active")
    target = Collection(name="Target")
    database.save_collection(active)
    database.save_collection(target)
    existing = Waypoint(name="Existing", latitude=49.0, longitude=13.0)
    database.save_waypoint(existing, active.id)
    result = MapSearchResult("New", "Place", 50.0, 14.0)
    created = Waypoint(name="New", latitude=50.0, longitude=14.0)
    messages = []

    class AcceptedWaypointDialog:
        def __init__(self, *args, **kwargs):
            assert args[4] == active.id
            self.waypoint = created
            self.collection_id = target.id

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.NewWaypointDialog",
        AcceptedWaypointDialog,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )
    window = MainWindow(database, icon_catalog=[])
    for index in range(window.collection_list.count()):
        item = window.collection_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == active.id:
            window.collection_list.setCurrentItem(item)
            break
    window.open_map()
    assert window.map_window is not None
    map_payload_before = list(window.map_window.waypoint_map._waypoint_payload)
    window.map_window._show_search_results([result])
    window.map_window.search_results.setCurrentRow(0)
    search_marker_before = dict(
        window.map_window.waypoint_map._search_result_payload or {}
    )

    window.map_window.add_search_result_button.click()

    assert database.list_waypoints(active.id) == [existing]
    assert database.list_waypoints(target.id) == [created]
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == active.id
    assert window._map_waypoints == [existing]
    assert window.map_window.waypoint_map._waypoint_payload == map_payload_before
    assert window.map_window.waypoint_map._search_result_payload == (
        search_marker_before
    )
    assert messages == ['Waypoint was saved to collection "Target".']

    window.map_window.close()
    window.close()
    application.processEvents()


def test_map_window_near_search_requires_selected_waypoint():
    application = QApplication.instance() or QApplication([])
    search_client = FakeSearchClient()
    window = MapWindow(
        config=ApplicationConfig(mapy_api_key="configured-key"),
        search_client=search_client,
    )

    window.search_area_combo.setCurrentIndex(
        window.search_area_combo.findData("near-waypoint")
    )

    assert window.search_area_combo.currentData() == "current-map"
    assert "Select one waypoint" in window.search_status.text()
    assert search_client.calls == []

    window.close()
    application.processEvents()


def test_main_window_updates_open_map_dataset_and_selection(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(name="Place", latitude=50.0, longitude=14.0)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database, icon_catalog=[])
    window.open_map()
    map_window = window.map_window
    assert map_window is not None

    window.collection_list.setCurrentRow(0)

    assert map_window.waypoint_map._waypoint_payload == [
        {
            "id": str(waypoint.id),
            "name": "Place",
            "latitude": 50.0,
            "longitude": 14.0,
            "icon": "marker",
            "color": "#FF0000",
            "background": "circle",
            "iconSvgUrl": None,
        }
    ]

    window.waypoint_list.setCurrentRow(0)

    assert map_window.selected_waypoint_ids == [waypoint.id]

    map_window.close()
    window.close()
    application.processEvents()


def test_main_window_loads_collection_without_open_map(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(name="Place", latitude=50.0, longitude=14.0)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)

    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)

    assert window.map_window is None
    assert window._map_waypoints == [waypoint]
    assert window._selected_waypoint_ids == [waypoint.id]

    window.close()
    application.processEvents()


def test_selected_waypoint_updates_map_search_context(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    first = Waypoint(name="First", latitude=50.1, longitude=14.1)
    second = Waypoint(name="Second", latitude=50.2, longitude=14.2)
    database.save_waypoint(first, collection.id)
    database.save_waypoint(second, collection.id)
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()
    assert window.map_window is not None

    window.waypoint_list.setCurrentRow(0)
    first_item_id = window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    )
    expected_first = first if first.id == first_item_id else second
    assert window.map_window._search_waypoint_position == (
        expected_first.latitude,
        expected_first.longitude,
    )

    window.waypoint_list.setCurrentRow(1)
    second_item_id = window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    )
    expected_second = first if first.id == second_item_id else second
    assert expected_second.id != expected_first.id
    assert window.map_window._search_waypoint_position == (
        expected_second.latitude,
        expected_second.longitude,
    )

    window.map_window.close()
    window.close()
    application.processEvents()


def test_marker_context_actions_edit_search_and_open_waypoint(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Petřín",
        latitude=50.0835,
        longitude=14.3952,
    )
    database.save_waypoint(waypoint, collection.id)
    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()
    assert window.map_window is not None

    window.edit_waypoint_from_map(waypoint.id)

    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id
    assert window.name_edit.text() == "Petřín"
    assert window.map_window.selected_waypoint_ids == [waypoint.id]

    window.map_window.search_edit.setText("parking")
    window.search_near_waypoint_from_map(waypoint.id)

    assert window.map_window.search_area_combo.currentData() == (
        "near-waypoint"
    )
    assert window.map_window._search_waypoint_position == (
        waypoint.latitude,
        waypoint.longitude,
    )
    assert window.map_window.search_edit.text() == "parking"

    window.open_waypoint_in_mapy(waypoint.id)

    assert opened_urls == [
        "https://mapy.com/fnc/v1/showmap?"
        "center=14.3952,50.0835&zoom=16&marker=true"
    ]

    window.map_window.close()
    window.close()
    application.processEvents()


def test_edit_waypoint_from_map_restores_and_activates_main_window(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(name="Place", latitude=50.0, longitude=14.0)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    calls = []
    monkeypatch.setattr(window, "isMinimized", lambda: True)
    monkeypatch.setattr(window, "showNormal", lambda: calls.append("normal"))
    monkeypatch.setattr(window, "raise_", lambda: calls.append("raise"))
    monkeypatch.setattr(
        window,
        "activateWindow",
        lambda: calls.append("activate"),
    )

    window.edit_waypoint_from_map(waypoint.id)

    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id
    assert calls == ["normal", "raise", "activate"]

    window.close()
    application.processEvents()


def test_move_waypoint_cancel_then_confirm_preserves_identity_and_data(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Mountain passes")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Passo Stelvio",
        latitude=46.5286,
        longitude=10.4531,
        icon="peak",
        color="#123456",
        background="octagon",
        note="Short note",
        comment="Detailed comment",
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()
    assert window.map_window is not None

    monkeypatch.setattr(window, "_confirm_waypoint_move", lambda *args: False)
    window.move_waypoint_from_map(waypoint.id, 46.5292, 10.4518)
    assert database.get_waypoint(waypoint.id) == waypoint

    datasets = []
    original_set_waypoints = window.map_window.set_waypoints
    monkeypatch.setattr(
        window.map_window,
        "set_waypoints",
        lambda waypoints, fit_viewport=True: (
            datasets.append((list(waypoints), fit_viewport)),
            original_set_waypoints(waypoints, fit_viewport),
        ),
    )
    monkeypatch.setattr(window, "_confirm_waypoint_move", lambda *args: True)
    window.move_waypoint_from_map(waypoint.id, 46.5292, 10.4518)

    moved = database.get_waypoint(waypoint.id)
    assert moved == Waypoint(
        name=waypoint.name,
        latitude=46.5292,
        longitude=10.4518,
        id=waypoint.id,
        icon=waypoint.icon,
        color=waypoint.color,
        background=waypoint.background,
        note=waypoint.note,
        comment=waypoint.comment,
    )
    assert datasets
    assert datasets[-1][1] is False
    assert datasets[-1][0] == [moved]
    assert window.map_window.selected_waypoint_ids == [waypoint.id]

    window.map_window.close()
    window.close()
    application.processEvents()


def test_delete_waypoint_from_marker_cancel_and_confirm(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(name="Delete me", latitude=50.0, longitude=14.0)
    database.save_waypoint(waypoint, collection.id)
    answers = iter(
        [
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        ]
    )
    prompts = []

    def answer_question(*args):
        prompts.append(args[2])
        return next(answers)

    monkeypatch.setattr(QMessageBox, "question", answer_question)
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()
    assert window.map_window is not None
    map_window = window.map_window

    window.delete_waypoint_from_map(waypoint.id)

    assert database.get_waypoint(waypoint.id) == waypoint
    assert map_window.waypoint_map._waypoint_payload[0]["id"] == str(
        waypoint.id
    )

    window.delete_waypoint_from_map(waypoint.id)

    assert database.get_waypoint(waypoint.id) is None
    assert window.waypoint_list.count() == 0
    assert map_window.waypoint_map._waypoint_payload == []
    assert not map_window.waypoint_map._pending_fit_viewport
    assert window.map_window is map_window
    assert prompts == [
        'Delete waypoint "Delete me"?',
        'Delete waypoint "Delete me"?',
    ]

    map_window.close()
    window.close()
    application.processEvents()


def test_add_waypoint_from_map_requires_available_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database, icon_catalog=[])
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )

    window.add_waypoint_from_map(50.123, 14.456)

    assert window.collection_list.count() == 0
    assert messages == ["Create a collection before adding a waypoint."]

    window.close()
    application.processEvents()


def test_add_waypoint_from_map_saves_selects_sorts_and_updates_map(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    existing = Waypoint(name="Zulu", latitude=49.0, longitude=13.0)
    database.save_waypoint(existing, collection.id)
    created = Waypoint(
        name="Alpha",
        latitude=50.123,
        longitude=14.456,
    )

    class AcceptedWaypointDialog:
        def __init__(
            self,
            latitude,
            longitude,
            icon_catalog,
            collections,
            selected_collection_id,
            parent,
        ):
            assert latitude == 50.123
            assert longitude == 14.456
            assert icon_catalog == []
            assert collections == [(collection.id, "Places")]
            assert selected_collection_id == collection.id
            self.waypoint = created
            self.collection_id = collection.id

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.NewWaypointDialog",
        AcceptedWaypointDialog,
    )
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.open_map()

    window.add_waypoint_from_map(50.123, 14.456)

    stored = database.get_waypoint(created.id)
    assert stored is not None
    assert stored.latitude == 50.123
    assert stored.longitude == 14.456
    assert database.list_waypoints(collection.id) == [created, existing]
    assert window.waypoint_sort_combo.currentData() == "name"
    assert [
        window.waypoint_list.item(index).text()
        for index in range(window.waypoint_list.count())
    ] == ["Alpha", "Zulu"]
    assert window.waypoint_list.currentItem() is not None
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == created.id
    assert window.name_edit.text() == "Alpha"
    assert window.map_window is not None
    assert {
        payload["id"]
        for payload in window.map_window.waypoint_map._waypoint_payload
    } == {str(created.id), str(existing.id)}
    assert window.map_window.selected_waypoint_ids == [created.id]
    assert window.map_window.waypoint_map._selected_waypoint_ids == [
        str(created.id)
    ]
    assert not window.map_window.waypoint_map._pending_fit_viewport

    window.map_window.close()
    window.close()
    application.processEvents()


def test_add_waypoint_from_map_saves_to_selected_duplicate_name_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    active_collection = Collection(name="Places")
    target_collection = Collection(name="Places")
    database.save_collection(active_collection)
    database.save_collection(target_collection)
    existing = Waypoint(name="Existing", latitude=49.0, longitude=13.0)
    database.save_waypoint(existing, active_collection.id)
    created = Waypoint(name="Elsewhere", latitude=50.123, longitude=14.456)
    messages = []

    class AcceptedWaypointDialog:
        def __init__(
            self,
            latitude,
            longitude,
            icon_catalog,
            collections,
            selected_collection_id,
            parent,
        ):
            assert {
                collection_id for collection_id, _ in collections
            } == {active_collection.id, target_collection.id}
            assert [name for _, name in collections] == ["Places", "Places"]
            assert selected_collection_id == active_collection.id
            self.waypoint = created
            self.collection_id = target_collection.id

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.NewWaypointDialog",
        AcceptedWaypointDialog,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args: messages.append(args[2]),
    )
    window = MainWindow(database, icon_catalog=[])
    for index in range(window.collection_list.count()):
        item = window.collection_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == active_collection.id:
            window.collection_list.setCurrentItem(item)
            break
    map_waypoints_before = list(window._map_waypoints)

    window.add_waypoint_from_map(50.123, 14.456)

    assert database.list_waypoints(active_collection.id) == [existing]
    assert database.list_waypoints(target_collection.id) == [created]
    assert window.collection_list.currentItem() is not None
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == active_collection.id
    assert window._map_waypoints == map_waypoints_before
    assert messages == ['Waypoint was saved to collection "Places".']

    window.close()
    application.processEvents()


def test_main_window_loads_collections_with_uuid(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first = Collection(name="Francie")
    second = Collection(name="Itálie")
    database.save_collection(first)
    database.save_collection(second)

    window = MainWindow(database)

    assert window.collection_list.count() == 2
    assert window.collection_list.item(0).text() == "Francie"
    assert window.collection_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == first.id
    assert window.collection_list.item(1).text() == "Itálie"
    assert window.collection_list.item(1).data(
        Qt.ItemDataRole.UserRole
    ) == second.id
    assert window.merge_collections_button.isEnabled()

    window.close()
    application.processEvents()


def test_successful_merge_reloads_and_selects_target_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    source = Collection(name="Alpha source")
    target = Collection(name="Bravo target")
    database.save_collection(source)
    database.save_collection(target)
    source_waypoint = Waypoint(name="Zulu", latitude=50.0, longitude=14.0)
    target_waypoint = Waypoint(name="Alpha", latitude=51.0, longitude=14.0)
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(1)
    window.waypoint_sort_combo.setCurrentIndex(1)

    class SuccessfulMergeDialog:
        def __init__(self, dialog_database, selected_target_id, parent):
            assert selected_target_id == target.id
            self.merged_target_id = target.id
            self.database = dialog_database

        def exec(self):
            merge_collections(self.database, source.id, target.id, {})
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.CollectionMergeDialog",
        SuccessfulMergeDialog,
    )

    window.merge_collections_button.click()

    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == target.id
    assert window.waypoint_sort_combo.currentData() == "created_at"
    assert window.waypoint_list.count() == 2
    assert {
        window.waypoint_list.item(index).text()
        for index in range(window.waypoint_list.count())
    } == {"Alpha", "Zulu"}

    window.close()
    application.processEvents()


def test_selecting_collection_loads_its_waypoints(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first_collection = Collection(name="Francie")
    second_collection = Collection(name="Itálie")
    empty_collection = Collection(name="Prázdná")
    database.save_collection(first_collection)
    database.save_collection(second_collection)
    database.save_collection(empty_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    second_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(first_waypoint, first_collection.id)
    database.save_waypoint(second_waypoint, second_collection.id)
    window = MainWindow(database, icon_catalog=[])

    assert window.waypoint_list.count() == 0

    window.collection_list.setCurrentRow(0)
    assert window.export_button.isEnabled()
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).text() == "Pont du Gard"
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == first_waypoint.id
    assert window._map_waypoints == [first_waypoint]
    window.open_map()
    assert window.map_window is not None
    assert window.map_window.waypoint_map._waypoint_payload == [
        {
            "id": str(first_waypoint.id),
            "name": "Pont du Gard",
            "latitude": 43.947070,
            "longitude": 4.535600,
            "icon": "marker",
            "color": "#FF0000",
            "background": "circle",
            "iconSvgUrl": None,
        }
    ]

    window.collection_list.setCurrentRow(1)
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).text() == "Koloseum"
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == second_waypoint.id
    assert window.map_window.waypoint_map._waypoint_payload == [
        {
            "id": str(second_waypoint.id),
            "name": "Koloseum",
            "latitude": 41.890210,
            "longitude": 12.492231,
            "icon": "marker",
            "color": "#FF0000",
            "background": "circle",
            "iconSvgUrl": None,
        }
    ]

    window.collection_list.setCurrentRow(2)
    assert window.waypoint_list.count() == 0
    assert window.map_window.waypoint_map._waypoint_payload == []

    window.collection_list.setCurrentRow(-1)
    assert window.waypoint_list.count() == 0
    assert window.map_window.waypoint_map._waypoint_payload == []
    assert not window.export_button.isEnabled()

    window.close()
    application.processEvents()


def test_waypoint_sort_combo_reloads_and_preserves_selection(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    zulu = Waypoint(name="Zulu", latitude=1.0, longitude=1.0)
    alpha = Waypoint(name="alpha", latitude=2.0, longitude=2.0)
    database.save_waypoint(zulu, collection.id)
    database.save_waypoint(alpha, collection.id)
    connection = sqlite3.connect(database.path)
    connection.execute(
        "UPDATE waypoints SET created_at = ? WHERE id = ?",
        ("2026-01-01 00:00:00", str(zulu.id)),
    )
    connection.execute(
        "UPDATE waypoints SET created_at = ? WHERE id = ?",
        ("2026-01-02 00:00:00", str(alpha.id)),
    )
    connection.commit()
    connection.close()
    window = MainWindow(database)
    window.show()
    window.collection_list.setCurrentRow(0)
    application.processEvents()

    assert [
        window.waypoint_list.item(index).text()
        for index in range(window.waypoint_list.count())
    ] == ["alpha", "Zulu"]
    for index in range(window.waypoint_list.count()):
        window.waypoint_list.item(index).setSelected(True)
    window.waypoint_list.setCurrentRow(1)
    current_id = window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    )

    window.waypoint_sort_combo.setCurrentIndex(1)
    application.processEvents()

    assert [
        window.waypoint_list.item(index).text()
        for index in range(window.waypoint_list.count())
    ] == ["Zulu", "alpha"]
    assert {
        item.data(Qt.ItemDataRole.UserRole)
        for item in window.waypoint_list.selectedItems()
    } == {zulu.id, alpha.id}
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == current_id
    assert [
        window.waypoint_list.model().index(index, 0).data()
        for index in range(window.waypoint_list.count())
    ] == ["Zulu", "alpha"]

    window.close()
    application.processEvents()


def test_native_arrow_navigation_moves_one_waypoint_at_a_time(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    for index in range(4):
        database.save_waypoint(
            Waypoint(
                name=f"Point {index}",
                latitude=float(index),
                longitude=14.0,
            ),
            collection.id,
        )
    window = MainWindow(database)
    window.show()
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(1)
    window.waypoint_list.setFocus()

    QTest.keyClick(window.waypoint_list, Qt.Key.Key_Down)
    assert window.waypoint_list.currentRow() == 2
    QTest.keyClick(window.waypoint_list, Qt.Key.Key_Down)
    assert window.waypoint_list.currentRow() == 3
    QTest.keyClick(window.waypoint_list, Qt.Key.Key_Up)
    assert window.waypoint_list.currentRow() == 2
    QTest.keyClick(window.waypoint_list, Qt.Key.Key_Up)
    assert window.waypoint_list.currentRow() == 1

    window.close()
    application.processEvents()


def test_load_collections_error_clears_views_and_can_recover(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    database.save_waypoint(
        Waypoint(name="Point", latitude=50.0, longitude=14.0),
        collection.id,
    )
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    original = database.list_collections
    errors = []
    monkeypatch.setattr(
        database,
        "list_collections",
        lambda: (_ for _ in ()).throw(sqlite3.OperationalError("broken")),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors.append(args[2]),
    )

    assert not window.load_collections()

    assert window.collection_list.count() == 0
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert errors == ["The Collections could not be loaded:\nbroken"]

    monkeypatch.setattr(database, "list_collections", original)
    assert window.load_collections()
    assert window.collection_list.count() == 1

    window.close()
    application.processEvents()


def test_edit_collection_updates_metadata_reorders_and_preserves_selection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    alpha = Collection(name="Alpha")
    edited = Collection(
        name="Middle",
        description="Old description",
        source="mapy.com",
        source_file="original.gpx",
    )
    database.save_collection(alpha)
    database.save_collection(edited)
    waypoint = Waypoint(name="Point", latitude=50.0, longitude=14.0)
    database.save_waypoint(waypoint, edited.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(1)
    assert window.edit_collection_button.isEnabled()

    class AcceptedEditDialog:
        collection_name = "Zulu"
        collection_description = "New\ndescription"

        def __init__(self, collection, parent):
            assert collection.id == edited.id
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.CollectionEditDialog",
        AcceptedEditDialog,
    )

    window.edit_collection_button.click()

    loaded = database.get_collection(edited.id)
    assert loaded is not None
    assert loaded.id == edited.id
    assert loaded.name == "Zulu"
    assert loaded.description == "New\ndescription"
    assert loaded.source == "mapy.com"
    assert loaded.source_file == "original.gpx"
    assert [
        window.collection_list.item(index).text()
        for index in range(window.collection_list.count())
    ] == ["Alpha", "Zulu"]
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == edited.id
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id

    window.close()
    application.processEvents()


def test_load_waypoints_error_clears_view_and_can_recover(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    waypoint = Waypoint(name="Point", latitude=50.0, longitude=14.0)
    database.save_collection(collection)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    collection_item = window.collection_list.currentItem()
    original = database.list_waypoints
    errors = []
    monkeypatch.setattr(
        database,
        "list_waypoints",
        lambda *args: (_ for _ in ()).throw(
            sqlite3.OperationalError("broken")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors.append(args[2]),
    )

    assert not window.load_waypoints(collection_item)

    assert window.collection_list.currentItem() is collection_item
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert errors == ["The Waypoints could not be loaded:\nbroken"]

    monkeypatch.setattr(database, "list_waypoints", original)
    assert window.load_waypoints(collection_item)
    assert window.waypoint_list.count() == 1

    window.close()
    application.processEvents()


def test_get_waypoint_error_clears_editor_and_can_recover(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    database.save_waypoint(
        Waypoint(name="First", latitude=50.0, longitude=14.0),
        collection.id,
    )
    database.save_waypoint(
        Waypoint(name="Second", latitude=51.0, longitude=14.0),
        collection.id,
    )
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    assert window.name_edit.text() == "First"
    original = database.get_waypoint
    errors = []
    monkeypatch.setattr(
        database,
        "get_waypoint",
        lambda *args: (_ for _ in ()).throw(
            sqlite3.OperationalError("broken")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors.append(args[2]),
    )

    window.waypoint_list.setCurrentRow(1)

    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()
    assert errors == ["The Waypoint could not be loaded:\nbroken"]

    monkeypatch.setattr(database, "get_waypoint", original)
    window.waypoint_list.setCurrentRow(0)
    assert window.name_edit.text() == "First"

    window.close()
    application.processEvents()


def test_selecting_waypoint_loads_and_clears_editor(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    empty_collection = Collection(name="Prázdná")
    database.save_collection(collection)
    database.save_collection(empty_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )
    second_waypoint = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
        icon="natural_water",
        color="invalid-color",
        background="circle",
        note="Druhá poznámka",
        comment="Druhý komentář",
    )
    database.save_waypoint(first_waypoint, collection.id)
    database.save_waypoint(second_waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)

    window.waypoint_list.setCurrentRow(1)

    assert window.save_button.isEnabled()
    assert window.name_edit.text() == first_waypoint.name
    assert window.icon_edit.text() == first_waypoint.icon
    assert window.color_edit.text() == first_waypoint.color
    assert window.color_preview.autoFillBackground()
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == first_waypoint.color
    assert window.background_combo.currentText() == first_waypoint.background
    assert window.latitude_edit.text() == str(first_waypoint.latitude)
    assert window.longitude_edit.text() == str(first_waypoint.longitude)
    assert window.note_edit.text() == first_waypoint.note
    assert window.comment_edit.toPlainText() == first_waypoint.comment

    window.waypoint_list.setCurrentRow(0)
    assert window.name_edit.text() == second_waypoint.name
    assert window.color_edit.text() == second_waypoint.color
    assert not window.color_preview.autoFillBackground()
    assert window.latitude_edit.text() == str(second_waypoint.latitude)
    assert window.comment_edit.toPlainText() == second_waypoint.comment

    window.collection_list.setCurrentRow(1)
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert window.icon_edit.text() == ""
    assert window.color_edit.text() == ""
    assert not window.color_preview.autoFillBackground()
    assert window.background_combo.currentText() == ""
    assert window.latitude_edit.text() == ""
    assert window.longitude_edit.text() == ""
    assert window.note_edit.text() == ""
    assert window.comment_edit.toPlainText() == ""
    assert not window.save_button.isEnabled()

    window.close()
    application.processEvents()


@pytest.mark.parametrize("background", ["circle", "custom-shape", ""])
def test_background_loads_and_saves_without_data_loss(
    tmp_path,
    monkeypatch,
    background,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Point",
        latitude=50.0,
        longitude=14.0,
        background=background,
    )
    database.save_waypoint(waypoint, collection.id)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)

    assert window.background_combo.currentText() == background
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded is not None
    assert loaded.background == background

    window.close()
    application.processEvents()


def test_unknown_background_can_be_changed_to_known_value(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Point",
        latitude=50.0,
        longitude=14.0,
        background="custom-shape",
    )
    database.save_waypoint(waypoint, collection.id)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)

    window.background_combo.setCurrentIndex(
        window.background_combo.findText("square")
    )
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded is not None
    assert loaded.background == "square"

    window.close()
    application.processEvents()


def test_multiple_waypoint_selection_enables_bulk_editor(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    other_collection = Collection(name="Prázdná")
    database.save_collection(collection)
    database.save_collection(other_collection)
    first = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    second = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
    )
    database.save_waypoint(first, collection.id)
    database.save_waypoint(second, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)

    items_by_id = {
        window.waypoint_list.item(index).data(Qt.ItemDataRole.UserRole):
            window.waypoint_list.item(index)
        for index in range(window.waypoint_list.count())
    }
    first_item = items_by_id[first.id]
    second_item = items_by_id[second.id]
    first_item.setSelected(True)
    second_item.setSelected(True)

    assert {
        item.data(Qt.ItemDataRole.UserRole)
        for item in window.waypoint_list.selectedItems()
    } == {first.id, second.id}
    assert window.editor_panel.isEnabled()
    assert window.save_button.isEnabled()
    assert not window.name_edit.isEnabled()
    assert window.icon_edit.isEnabled()
    assert window.color_edit.isEnabled()
    assert window.background_combo.isEnabled()
    assert not window.latitude_edit.isEnabled()
    assert not window.longitude_edit.isEnabled()
    assert not window.note_edit.isEnabled()
    assert not window.comment_edit.isEnabled()
    assert not window.waypoint_selection_label.isHidden()
    assert window.waypoint_selection_label.text() == "Selected waypoints: 2"

    second_item.setSelected(False)

    assert window.editor_panel.isEnabled()
    assert window.save_button.isEnabled()
    assert window.name_edit.text() == first.name
    assert window.waypoint_selection_label.isHidden()

    window.waypoint_list.clearSelection()

    assert window.editor_panel.isEnabled()
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()

    first_item.setSelected(True)
    second_item.setSelected(True)
    window.collection_list.setCurrentRow(1)

    assert window.waypoint_list.count() == 0
    assert window.editor_panel.isEnabled()
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()

    window.close()
    application.processEvents()


def test_bulk_edit_updates_only_explicit_fields(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    first = Waypoint(
        name="First",
        latitude=1.0,
        longitude=2.0,
        icon="first-icon",
        color="#FF0000",
        background="circle",
        note="First note",
        comment="First comment",
    )
    second = Waypoint(
        name="Second",
        latitude=3.0,
        longitude=4.0,
        icon="second-icon",
        color="#00FF00",
        background="square",
        note="Second note",
        comment="Second comment",
    )
    unselected = Waypoint(
        name="Unselected",
        latitude=5.0,
        longitude=6.0,
        icon="unchanged-icon",
        color="#0000FF",
        background="octagon",
        note="Unselected note",
        comment="Unselected comment",
    )
    for waypoint in (first, second, unselected):
        database.save_waypoint(waypoint, collection.id)

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.item(0).setSelected(True)
    window.waypoint_list.item(1).setSelected(True)

    assert window.icon_edit.text() == ""
    assert window.color_edit.text() == ""
    assert window.background_combo.currentIndex() == -1
    assert window.bulk_changed_fields == set()

    window.icon_edit.setText("shared-icon")
    window.mark_bulk_field_changed("icon")
    window.save_button.click()

    loaded_first = database.get_waypoint(first.id)
    loaded_second = database.get_waypoint(second.id)
    assert loaded_first is not None
    assert loaded_second is not None
    assert loaded_first.icon == loaded_second.icon == "shared-icon"
    assert loaded_first.color == first.color
    assert loaded_second.color == second.color
    assert loaded_first.background == first.background
    assert loaded_second.background == second.background

    window.color_edit.setText("#123456")
    window.mark_bulk_field_changed("color")
    window.save_button.click()
    window.background_combo.setCurrentText("octagon")
    window.save_button.click()

    loaded_first = database.get_waypoint(first.id)
    loaded_second = database.get_waypoint(second.id)
    loaded_unselected = database.get_waypoint(unselected.id)
    assert loaded_first is not None
    assert loaded_second is not None
    assert loaded_unselected == unselected
    assert loaded_first.color == loaded_second.color == "#123456"
    assert loaded_first.background == loaded_second.background == "octagon"
    assert loaded_first.name == first.name
    assert loaded_second.name == second.name
    assert loaded_first.latitude == first.latitude
    assert loaded_second.longitude == second.longitude
    assert loaded_first.note == first.note
    assert loaded_second.note == second.note
    assert loaded_first.comment == first.comment
    assert loaded_second.comment == second.comment
    assert {
        item.data(Qt.ItemDataRole.UserRole)
        for item in window.waypoint_list.selectedItems()
    } == {first.id, second.id}
    assert messages == [
        "Updated 2 waypoints.",
        "Updated 2 waypoints.",
        "Updated 2 waypoints.",
    ]

    window.close()
    application.processEvents()


def test_save_button_updates_selected_waypoint(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Původní název",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    svg_path = tmp_path / "historic_archaeological_site.svg"
    svg_path.write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'/>",
        encoding="utf-8",
    )
    window = MainWindow(
        database,
        icon_catalog=[
            IconInfo(
                group="Test",
                icon_name="historic_archaeological_site",
                svg_path=svg_path,
            )
        ],
    )
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    window.open_map()
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.name_edit.setText("Pont du Gard")
    window.icon_edit.setText("historic_archaeological_site")
    window.color_edit.setText("#ff8000")
    window.background_combo.setCurrentText("square")
    window.note_edit.setText("Zastavit na focení")
    window.comment_edit.setPlainText(
        "Velmi pěkné místo pro delší zastávku."
    )
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded is not None
    assert loaded.id == waypoint.id
    assert loaded.name == "Pont du Gard"
    assert loaded.latitude == waypoint.latitude
    assert loaded.longitude == waypoint.longitude
    assert loaded.icon == "historic_archaeological_site"
    assert loaded.color == "#FF8000"
    assert loaded.background == "square"
    assert loaded.note == "Zastavit na focení"
    assert loaded.comment == "Velmi pěkné místo pro delší zastávku."
    assert window.waypoint_list.currentItem() is not None
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id
    assert window.waypoint_list.currentItem().text() == "Pont du Gard"
    assert window.name_edit.text() == "Pont du Gard"
    assert window.color_preview.autoFillBackground()
    assert window.map_window is not None
    marker_payload = window.map_window.waypoint_map._waypoint_payload[0]
    assert marker_payload["icon"] == "historic_archaeological_site"
    assert marker_payload["color"] == "#FF8000"
    assert marker_payload["background"] == "square"
    assert marker_payload["iconSvgUrl"].startswith(
        "data:image/svg+xml;base64,"
    )
    assert not window.map_window.waypoint_map._pending_fit_viewport
    assert messages == ['Waypoint "Pont du Gard" was saved.']

    window.map_window.close()
    window.close()
    application.processEvents()


def test_color_button_updates_color_and_handles_cancel(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    initial_colors = []

    def select_color(initial_color, *args, **kwargs):
        initial_colors.append(initial_color.name().upper())
        return QColor("#123456")

    window.color_edit.setText("#FF8000")
    monkeypatch.setattr(QColorDialog, "getColor", select_color)

    window.color_button.click()

    assert initial_colors == ["#FF8000"]
    assert window.color_edit.text() == "#123456"
    assert window.color_preview.autoFillBackground()
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == "#123456"

    monkeypatch.setattr(
        QColorDialog,
        "getColor",
        lambda *args, **kwargs: QColor(),
    )
    window.color_button.click()

    assert window.color_edit.text() == "#123456"
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == "#123456"

    window.close()
    application.processEvents()


def test_icon_button_updates_icon_and_handles_cancel(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.load_icon_catalog",
        lambda: [],
    )
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)

    class AcceptedIconDialog:
        selected_icon_name = "amenity_fuel"

        def __init__(self, catalog, parent):
            assert catalog == []
            assert parent is window.waypoint_editor

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.waypoint_editor.IconPickerDialog",
        AcceptedIconDialog,
    )

    window.icon_edit.setText("unknown_existing_icon")
    window.icon_button.click()
    assert window.icon_edit.text() == "amenity_fuel"

    class RejectedIconDialog(AcceptedIconDialog):
        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "wpt_manager.gui.waypoint_editor.IconPickerDialog",
        RejectedIconDialog,
    )

    window.icon_edit.setText("unknown_existing_icon")
    window.icon_button.click()
    assert window.icon_edit.text() == "unknown_existing_icon"

    window.close()
    application.processEvents()


def test_icon_preview_uses_cached_catalog_and_updates_live(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first_svg = tmp_path / "first.svg"
    duplicate_svg = tmp_path / "duplicate.svg"
    other_svg = tmp_path / "other.svg"
    first_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="32" height="16"><rect width="32" height="16" '
        'fill="#ff0000"/></svg>',
        encoding="utf-8",
    )
    duplicate_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="16" height="32"><rect width="16" height="32" '
        'fill="#0000ff"/></svg>',
        encoding="utf-8",
    )
    other_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="24" height="24"><circle cx="12" cy="12" r="12" '
        'fill="#00ff00"/></svg>',
        encoding="utf-8",
    )
    catalog = [
        IconInfo("Alpha", "shared", first_svg),
        IconInfo("Beta", "shared", duplicate_svg),
        IconInfo("Beta", "other", other_svg),
    ]
    window = MainWindow(database, icon_catalog=catalog)

    assert window.icon_paths_by_name["shared"] == first_svg

    window.icon_edit.setText("shared")
    assert not window.icon_preview.pixmap().isNull()

    window.icon_edit.setText("unknown_icon")
    assert window.icon_edit.text() == "unknown_icon"
    assert window.icon_preview.pixmap().isNull()

    window.icon_edit.setText("other")
    assert not window.icon_preview.pixmap().isNull()

    class AcceptedIconDialog:
        selected_icon_name = "shared"

        def __init__(self, received_catalog, parent):
            assert received_catalog is catalog
            assert parent is window.waypoint_editor

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.waypoint_editor.IconPickerDialog",
        AcceptedIconDialog,
    )
    window.icon_button.click()

    assert window.icon_edit.text() == "shared"
    assert not window.icon_preview.pixmap().isNull()

    window.clear_waypoint_editor()
    assert window.icon_preview.pixmap().isNull()

    window.close()
    application.processEvents()


@pytest.mark.parametrize(
    ("name", "color", "expected_error"),
    [
        ("", "#FF0000", "Waypoint name cannot be empty."),
        (
            "Pont du Gard",
            "invalid-color",
            "Waypoint color must be a valid Qt color or HEX value.",
        ),
    ],
)
def test_save_button_rejects_invalid_values(
    tmp_path,
    monkeypatch,
    name,
    color,
    expected_error,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Původní název",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.name_edit.setText(name)
    window.color_edit.setText(color)
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded == waypoint
    assert messages == [expected_error]

    window.close()
    application.processEvents()


def test_save_button_handles_database_error(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        database,
        "update_waypoint",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("Database is locked")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.save_button.click()

    assert messages == [
        "The waypoint could not be saved:\nDatabase is locked"
    ]

    window.close()
    application.processEvents()


def test_import_button_imports_gpx_and_reloads_collections(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(TEST_DATA), "GPX files (*.gpx)"),
    )

    class SuccessfulImportDialog:
        merged_target_id = None

        def __init__(self, dialog_database, path, target_id, parent):
            assert target_id is None
            self.database = dialog_database
            self.path = path
            self.created_collection_id = None

        def exec(self):
            collection = import_gpx(
                self.database,
                self.path,
                "mapy_export",
            )
            self.created_collection_id = collection.id
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.GpxImportDialog",
        SuccessfulImportDialog,
    )

    window.import_button.click()

    collections = database.list_collections()
    assert len(collections) == 1
    assert collections[0].name == "mapy_export"
    assert window.collection_list.count() == 1
    assert window.collection_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == collections[0].id
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == collections[0].id

    window.close()
    application.processEvents()


def test_import_button_shows_error_message(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    messages = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(TEST_DATA), "GPX files (*.gpx)"),
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.GpxImportDialog",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            GpxReaderError("Invalid GPX")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.import_button.click()

    assert database.list_collections() == []
    assert window.collection_list.count() == 0
    assert messages == [
        "The GPX file could not be imported:\nInvalid GPX"
    ]

    window.close()
    application.processEvents()


def test_merge_import_reloads_target_and_preserves_waypoint_sort(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    target = Collection(name="France 2026")
    database.save_collection(target)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_sort_combo.setCurrentIndex(1)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(TEST_DATA), "GPX files (*.gpx)"),
    )

    class SuccessfulMergeImportDialog:
        created_collection_id = None

        def __init__(self, dialog_database, path, target_id, parent):
            assert target_id == target.id
            self.database = dialog_database
            self.path = path
            self.merged_target_id = target.id

        def exec(self):
            from wpt_manager.database.collection_merge import (
                merge_waypoints_into_collection,
            )

            merge_waypoints_into_collection(
                self.database,
                load_gpx(self.path),
                target.id,
                {},
            )
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.GpxImportDialog",
        SuccessfulMergeImportDialog,
    )

    window.import_button.click()

    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == target.id
    assert window.waypoint_sort_combo.currentData() == "created_at"
    assert window.waypoint_list.count() == 3

    window.close()
    application.processEvents()


def test_delete_selected_waypoints_requires_confirmation(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    selected = [
        Waypoint(name="Alpha", latitude=1.0, longitude=1.0),
        Waypoint(name="Bravo", latitude=2.0, longitude=2.0),
    ]
    unselected = Waypoint(name="Charlie", latitude=3.0, longitude=3.0)
    for waypoint in [*selected, unselected]:
        database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.item(0).setSelected(True)
    window.waypoint_list.item(1).setSelected(True)
    questions = []
    answers = [
        QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Yes,
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: (
            questions.append(args[2]) or answers.pop(0)
        ),
    )

    assert window.delete_waypoints_button.isEnabled()
    window.delete_waypoints_button.click()
    assert all(database.get_waypoint(waypoint.id) for waypoint in selected)

    window.delete_waypoints_button.click()

    assert questions == [
        "Delete 2 selected waypoint(s)?",
        "Delete 2 selected waypoint(s)?",
    ]
    assert all(
        database.get_waypoint(waypoint.id) is None
        for waypoint in selected
    )
    assert database.get_waypoint(unselected.id) == unselected
    assert window.waypoint_list.count() == 1
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()
    assert not window.delete_waypoints_button.isEnabled()

    window.close()
    application.processEvents()


def test_delete_collection_requires_confirmation_and_cascades(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoints = [
        Waypoint(name="Alpha", latitude=1.0, longitude=1.0),
        Waypoint(name="Bravo", latitude=2.0, longitude=2.0),
    ]
    for waypoint in waypoints:
        database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    questions = []
    answers = [
        QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Yes,
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: (
            questions.append(args[2]) or answers.pop(0)
        ),
    )

    assert window.delete_collection_button.isEnabled()
    window.delete_collection_button.click()
    assert database.get_collection(collection.id) == collection

    window.delete_collection_button.click()

    assert questions == [
        'Delete collection "Places" and its 2 waypoint(s)?',
        'Delete collection "Places" and its 2 waypoint(s)?',
    ]
    assert database.get_collection(collection.id) is None
    assert all(
        database.get_waypoint(waypoint.id) is None
        for waypoint in waypoints
    )
    assert window.collection_list.count() == 0
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert not window.delete_collection_button.isEnabled()

    window.close()
    application.processEvents()


def test_delete_collection_in_middle_selects_collection_at_same_index(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collections = [
        Collection(name="Alpha"),
        Collection(name="Bravo"),
        Collection(name="Charlie"),
    ]
    for collection in collections:
        database.save_collection(collection)
    waypoint = Waypoint(name="Charlie waypoint", latitude=1.0, longitude=1.0)
    database.save_waypoint(waypoint, collections[2].id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(1)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_collection_button.click()

    assert [
        window.collection_list.item(index).text()
        for index in range(window.collection_list.count())
    ] == ["Alpha", "Charlie"]
    assert window.collection_list.currentRow() == 1
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == collections[2].id
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id
    assert window.delete_collection_button.isEnabled()
    assert window.export_button.isEnabled()

    window.close()
    application.processEvents()


def test_delete_last_collection_selects_new_last_collection(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first = Collection(name="Alpha")
    last = Collection(name="Bravo")
    database.save_collection(first)
    database.save_collection(last)
    waypoint = Waypoint(name="Alpha waypoint", latitude=1.0, longitude=1.0)
    database.save_waypoint(waypoint, first.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(1)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_collection_button.click()

    assert window.collection_list.count() == 1
    assert window.collection_list.currentRow() == 0
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == first.id
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id

    window.close()
    application.processEvents()


def test_delete_only_collection_clears_selection_waypoints_and_editor(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Only")
    database.save_collection(collection)
    waypoint = Waypoint(name="Only waypoint", latitude=1.0, longitude=1.0)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    assert window.name_edit.text() == waypoint.name
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window.delete_collection_button.click()

    assert window.collection_list.count() == 0
    assert window.collection_list.currentItem() is None
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()
    assert not window.delete_collection_button.isEnabled()
    assert not window.export_button.isEnabled()

    window.close()
    application.processEvents()


def test_delete_actions_handle_database_errors(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Places")
    database.save_collection(collection)
    waypoint = Waypoint(name="Alpha", latitude=1.0, longitude=1.0)
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    errors = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: errors.append(args[2]),
    )
    monkeypatch.setattr(
        database,
        "delete_waypoints",
        lambda waypoint_ids: (_ for _ in ()).throw(
            sqlite3.OperationalError("Database is locked")
        ),
    )

    window.delete_waypoints_button.click()

    assert database.get_waypoint(waypoint.id) == waypoint
    assert errors == [
        "The waypoint(s) could not be deleted:\nDatabase is locked"
    ]

    monkeypatch.setattr(
        database,
        "delete_collection",
        lambda collection_id: (_ for _ in ()).throw(
            sqlite3.OperationalError("Database is locked")
        ),
    )
    window.delete_collection_button.click()

    assert database.get_collection(collection.id) == collection
    assert errors[-1] == (
        "The collection could not be deleted:\nDatabase is locked"
    )

    window.close()
    application.processEvents()


def test_export_button_exports_selected_collection(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    other_collection = Collection(name="Itálie")
    database.save_collection(collection)
    database.save_collection(other_collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )
    other_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(waypoint, collection.id)
    database.save_waypoint(other_waypoint, other_collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    output_without_suffix = tmp_path / "export"
    dialog_arguments = []
    messages = []

    def select_output_file(*args, **kwargs):
        dialog_arguments.append(args)
        return str(output_without_suffix), "GPX files (*.gpx)"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        select_output_file,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.export_button.click()

    output_file = tmp_path / "export.gpx"
    assert output_file.exists()
    assert dialog_arguments[0][2] == "Francie.gpx"
    assert dialog_arguments[0][3] == "GPX files (*.gpx)"
    exported_waypoints = load_gpx(output_file)
    assert len(exported_waypoints) == 1
    exported = exported_waypoints[0]
    assert exported.name == waypoint.name
    assert exported.latitude == waypoint.latitude
    assert exported.longitude == waypoint.longitude
    assert exported.note == waypoint.note
    assert exported.comment == waypoint.comment
    assert exported.icon == waypoint.icon
    assert exported.background == waypoint.background
    assert exported.color == waypoint.color
    assert messages == ['Collection "Francie" was exported.']

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )
    window.export_button.click()
    assert messages == ['Collection "Francie" was exported.']

    window.close()
    application.processEvents()


def test_export_button_handles_error(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (
            str(tmp_path / "francie.gpx"),
            "GPX files (*.gpx)",
        ),
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.export_collection_gpx",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("Access denied")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.export_button.click()

    assert messages == [
        "The collection could not be exported:\nAccess denied"
    ]

    window.close()
    application.processEvents()
