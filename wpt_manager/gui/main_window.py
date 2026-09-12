import sqlite3
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import (
    QCoreApplication,
    QItemSelectionModel,
    QProcess,
    QSettings,
    QSignalBlocker,
    Qt,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.database import Database
from wpt_manager.gui.collection_edit_dialog import CollectionEditDialog
from wpt_manager.gui.collection_create_dialog import CollectionCreateDialog
from wpt_manager.gui.collection_merge_dialog import CollectionMergeDialog
from wpt_manager.gui.gpx_import_dialog import GpxImportDialog
from wpt_manager.gui.map_window import MapWindow
from wpt_manager.gui.move_waypoints_dialog import MoveWaypointsDialog
from wpt_manager.gui.new_waypoint_dialog import NewWaypointDialog
from wpt_manager.gui.user_data_folder_dialog import UserDataFolderDialog
from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.gui.waypoint_editor import WaypointEditor
from wpt_manager.gui.track_editor import TrackEditor
from wpt_manager.gui.adventure_editor import AdventureEditor
from wpt_manager.gui.adventure_selection_dialog import AdventureSelectionDialog
from wpt_manager.gui.add_tracks_dialog import AddTracksDialog
from wpt_manager.gui.track_table import (
    TRACK_ID_ROLE, TrackFilterProxyModel, TrackTableModel,
)
from wpt_manager.gui.visibility_header import VisibilityHeaderCheckBox
from wpt_manager.gui.photo_editor import PhotoEditor
from wpt_manager.gui.photo_table import (
    PHOTO_ID_ROLE, PhotoFilterProxyModel, PhotoTableModel,
)

from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_exporter import export_collection_gpx
from wpt_manager.io.gpx_track_importer import (
    import_gpx_tracks, import_gpx_files, import_gpx_files_to_adventure,
)
from wpt_manager.io.icon_catalog import load_icon_catalog
from wpt_manager.io.user_data import (
    copy_user_data,
    existing_user_data_items,
    initialize_user_data_directory,
    verify_directory_writable,
)
from wpt_manager.mapy_search import MapSearchResult, build_mapy_show_url
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.models.adventure import Adventure
from wpt_manager.gui.imagekit_import_dialog import ImageKitImportDialog
from wpt_manager.gui.imagekit_settings_dialog import ImageKitSettingsDialog
from wpt_manager.photos.auto_assign import apply_photo_matches, match_summary, preview_photo_matches
from wpt_manager.photos.photo_track_matcher import PhotoTrackMatcher
from wpt_manager.paths import create_application_settings, store_user_data_directory
from wpt_manager.validation.waypoint_validator import validate_waypoint


def application_restart_command() -> tuple[str, list[str]]:
    """Return the current application entry point for a detached restart."""
    if getattr(sys, "frozen", False):
        return sys.executable, []
    return sys.executable, ["-m", "wpt_manager"]


class MainWindow(QMainWindow):
    def open_imagekit_settings(self) -> None:
        ImageKitSettingsDialog(self).exec()

    def open_mapy_settings(self) -> None:
        ImageKitSettingsDialog(
            self, provider="mapy", legacy_path=self.user_data_directory / "config.json",
        ).exec()
        if self.map_window is not None:
            self.map_window.refresh_credentials()

    def __init__(
        self,
        database: Database,
        icon_catalog: list[IconInfo] | None = None,
        user_data_directory: Path | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        install_native_title_bar_theming()
        self.database = database
        self.user_data_directory = (
            user_data_directory or self.database.path.parent
        ).resolve()
        self.settings = settings or create_application_settings()
        self.icon_catalog = (
            load_icon_catalog(self.user_data_directory / "icons")
            if icon_catalog is None
            else icon_catalog
        )
        self.setWindowTitle("WPT-Manager")
        settings_menu = self.menuBar().addMenu("Settings")
        self.imagekit_settings_action = QAction("ImageKit...", self)
        settings_menu.addAction(self.imagekit_settings_action)
        self.imagekit_settings_action.triggered.connect(self.open_imagekit_settings)
        self.mapy_settings_action = QAction("Mapy.com...", self)
        settings_menu.addAction(self.mapy_settings_action)
        self.mapy_settings_action.triggered.connect(self.open_mapy_settings)
        self.user_data_folder_action = QAction(
            "User data folder...",
            self,
        )
        settings_menu.addAction(self.user_data_folder_action)
        self.user_data_folder_action.triggered.connect(
            self.change_user_data_folder
        )
        self.resize(1000, 700)

        self.collection_list = QListWidget()
        self.new_collection_button = QPushButton("New Collection")
        self.import_button = QPushButton("Import GPX")
        self.export_button = QPushButton("Export GPX")
        self.export_button.setEnabled(False)
        self.delete_collection_button = QPushButton("Delete Collection")
        self.delete_collection_button.setEnabled(False)
        self.edit_collection_button = QPushButton("Edit Collection...")
        self.edit_collection_button.setEnabled(False)
        self.merge_collections_button = QPushButton("Merge Collections...")
        self.merge_collections_button.setEnabled(False)
        self.open_map_button = QPushButton("Open Map")

        collection_panel = QGroupBox("Waypoints")
        collection_layout = QVBoxLayout(collection_panel)
        self.collection_visibility_header = VisibilityHeaderCheckBox()
        collection_layout.addWidget(self.collection_visibility_header)
        collection_layout.addWidget(self.collection_list)

        collection_buttons = QHBoxLayout()
        collection_buttons.addWidget(self.new_collection_button)
        collection_buttons.addWidget(self.import_button)
        collection_buttons.addWidget(self.export_button)
        collection_buttons.addWidget(self.edit_collection_button)
        collection_buttons.addWidget(self.delete_collection_button)
        collection_layout.addLayout(collection_buttons)
        collection_layout.addWidget(self.merge_collections_button)
        collection_layout.addWidget(self.open_map_button)

        self.track_table = QTableView()
        self.track_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.track_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.track_model = TrackTableModel()
        self.track_proxy = TrackFilterProxyModel()
        self.track_proxy.setSourceModel(self.track_model)
        self.track_table.setModel(self.track_proxy)
        self.track_table.setSortingEnabled(True)
        self.track_search_edit = QLineEdit()
        self.track_search_edit.setPlaceholderText("Search tracks")
        self.track_adventure_filter = QComboBox()
        self.adventure_list = QListWidget()
        self.new_adventure_button = QPushButton("New Adventure")
        self.delete_adventure_button = QPushButton("Delete Adventure")
        self.delete_adventure_button.setEnabled(False)
        adventure_panel = QGroupBox("Adventures")
        adventure_layout = QVBoxLayout(adventure_panel)
        self.adventure_visibility_header = VisibilityHeaderCheckBox()
        adventure_layout.addWidget(self.adventure_visibility_header)
        adventure_layout.addWidget(self.adventure_list)
        adventure_buttons = QHBoxLayout()
        for button in (
            self.new_adventure_button, self.delete_adventure_button,
        ):
            adventure_buttons.addWidget(button)
        adventure_layout.addLayout(adventure_buttons)
        self.import_track_button = QPushButton("Import Track GPX...")
        self.delete_track_button = QPushButton("Delete Track")
        self.delete_track_button.setEnabled(False)
        self.zoom_track_button = QPushButton("Zoom to Track")
        self.zoom_track_button.setEnabled(False)
        self.open_track_map_button = QPushButton("Open Map")
        self.add_selected_to_adventure_button = QPushButton(
            "Add Selected to Adventure..."
        )
        track_panel = QGroupBox("Tracks")
        track_layout = QVBoxLayout(track_panel)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("Search:"))
        filters.addWidget(self.track_search_edit)
        filters.addWidget(QLabel("Adventure:"))
        filters.addWidget(self.track_adventure_filter)
        track_layout.addLayout(filters)
        self.track_visibility_header = VisibilityHeaderCheckBox()
        track_layout.addWidget(self.track_visibility_header)
        track_layout.addWidget(self.track_table)
        track_buttons = QHBoxLayout()
        track_buttons.addWidget(self.import_track_button)
        track_buttons.addWidget(self.delete_track_button)
        track_buttons.addWidget(self.zoom_track_button)
        track_buttons.addWidget(self.add_selected_to_adventure_button)
        track_layout.addLayout(track_buttons)
        track_layout.addWidget(self.open_track_map_button)
        self.open_adventure_map_button = QPushButton("Open Map")
        adventure_layout.addWidget(self.open_adventure_map_button)

        self.photo_table = QTableView()
        self.photo_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.photo_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.photo_model = PhotoTableModel()
        self.photo_proxy = PhotoFilterProxyModel()
        self.photo_proxy.setSourceModel(self.photo_model)
        self.photo_table.setModel(self.photo_proxy)
        self.photo_table.setSortingEnabled(True)
        self.photo_search_edit = QLineEdit()
        self.photo_search_edit.setPlaceholderText("Search photos")
        self.photo_track_filter = QComboBox()
        self.photo_adventure_filter = QComboBox()
        self.import_imagekit_button = QPushButton("Import from ImageKit...")
        self.match_photos_button = QPushButton("Match Photos to Tracks")
        photo_panel = QGroupBox("Photos")
        photo_layout = QVBoxLayout(photo_panel)
        photo_filters = QHBoxLayout()
        photo_filters.addWidget(QLabel("Search:"))
        photo_filters.addWidget(self.photo_search_edit)
        photo_filters.addWidget(QLabel("Track:"))
        photo_filters.addWidget(self.photo_track_filter)
        photo_filters.addWidget(QLabel("Adventure:"))
        photo_filters.addWidget(self.photo_adventure_filter)
        photo_layout.addLayout(photo_filters)
        photo_layout.addWidget(self.photo_table)
        photo_layout.addWidget(self.import_imagekit_button)
        photo_layout.addWidget(self.match_photos_button)

        self.data_tabs = QTabWidget()
        self.data_tabs.addTab(collection_panel, "Waypoints")
        self.data_tabs.addTab(track_panel, "Tracks")
        self.data_tabs.addTab(adventure_panel, "Adventures")
        self.data_tabs.addTab(photo_panel, "Photos")

        self.waypoint_list = QListWidget()
        self.waypoint_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.waypoint_sort_combo = QComboBox()
        self.waypoint_sort_combo.addItem("Name", "name")
        self.waypoint_sort_combo.addItem("Added", "created_at")
        self.delete_waypoints_button = QPushButton("Delete Waypoint(s)")
        self.delete_waypoints_button.setEnabled(False)
        self.move_waypoints_button = QPushButton("Move to Collection...")
        self.move_waypoints_button.setEnabled(False)

        waypoint_panel = QGroupBox("Waypoints")
        self.waypoint_panel = waypoint_panel
        waypoint_layout = QVBoxLayout(waypoint_panel)
        waypoint_layout.addWidget(self.waypoint_sort_combo)
        waypoint_layout.addWidget(self.waypoint_list)
        waypoint_layout.addWidget(self.move_waypoints_button)
        waypoint_layout.addWidget(self.delete_waypoints_button)

        self.waypoint_editor = WaypointEditor(self.icon_catalog)
        self.track_editor = TrackEditor()
        self.adventure_editor = AdventureEditor()
        self.photo_editor = PhotoEditor()
        self.map_window: MapWindow | None = None
        self._map_waypoints: list[Waypoint] = []
        self._selected_waypoint_ids: list[UUID] = []
        self._visible_track_ids: set[UUID] = set()
        self._shown_track_ids: set[UUID] = set()
        self._visible_collection_ids: set[UUID] = set()
        self._shown_collection_ids: set[UUID] = set()
        self.editor_panel = self.waypoint_editor
        self.icon_paths_by_name = self.waypoint_editor.icon_paths_by_name
        self.name_edit = self.waypoint_editor.name_edit
        self.icon_edit = self.waypoint_editor.icon_edit
        self.icon_preview = self.waypoint_editor.icon_preview
        self.icon_button = self.waypoint_editor.icon_button
        self.color_edit = self.waypoint_editor.color_edit
        self.color_preview = self.waypoint_editor.color_preview
        self.color_button = self.waypoint_editor.color_button
        self.background_combo = self.waypoint_editor.background_combo
        self.latitude_edit = self.waypoint_editor.latitude_edit
        self.longitude_edit = self.waypoint_editor.longitude_edit
        self.note_edit = self.waypoint_editor.note_edit
        self.comment_edit = self.waypoint_editor.comment_edit
        self.save_button = self.waypoint_editor.save_button
        self.waypoint_selection_label = self.waypoint_editor.selection_label
        self.bulk_changed_fields = self.waypoint_editor.bulk_changed_fields

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(waypoint_panel)
        self.right_splitter.addWidget(self.editor_panel)
        self.right_splitter.setStretchFactor(0, 2)
        self.right_splitter.setStretchFactor(1, 3)

        self.right_panel_stack = QStackedWidget()
        self.right_panel_stack.addWidget(self.right_splitter)
        self.right_panel_stack.addWidget(self.track_editor)
        self.right_panel_stack.addWidget(self.adventure_editor)
        self.right_panel_stack.addWidget(self.photo_editor)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.data_tabs)
        self.main_splitter.addWidget(self.right_panel_stack)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([250, 750])

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(self.main_splitter)
        self.setCentralWidget(central_widget)

        self.new_collection_button.clicked.connect(self.create_collection)
        self.import_button.clicked.connect(self.import_gpx_file)
        self.delete_collection_button.clicked.connect(
            self.delete_collection
        )
        self.edit_collection_button.clicked.connect(self.edit_collection)
        self.merge_collections_button.clicked.connect(
            self.open_merge_dialog
        )
        self.open_map_button.clicked.connect(self.open_map)
        self.collection_list.currentItemChanged.connect(
            self.load_waypoints
        )
        self.waypoint_list.itemSelectionChanged.connect(
            self.update_waypoint_selection
        )
        self.delete_waypoints_button.clicked.connect(
            self.delete_selected_waypoints
        )
        self.move_waypoints_button.clicked.connect(
            self.move_selected_waypoints
        )
        self.waypoint_sort_combo.currentIndexChanged.connect(
            self.reload_sorted_waypoints
        )
        self.waypoint_editor.save_requested.connect(self.save_waypoint)
        self.export_button.clicked.connect(self.export_gpx_file)
        self.import_track_button.clicked.connect(self.import_track_gpx_file)
        self.delete_track_button.clicked.connect(self.delete_selected_track)
        self.zoom_track_button.clicked.connect(self.zoom_to_selected_track)
        self.open_track_map_button.clicked.connect(self.open_map)
        self.track_table.selectionModel().currentRowChanged.connect(
            self.update_track_selection
        )
        self.track_model.visibility_changed.connect(
            self.update_track_visibility
        )
        self.track_search_edit.textChanged.connect(
            self.update_track_search
        )
        self.track_adventure_filter.currentIndexChanged.connect(
            self.update_track_adventure_filter
        )
        self.track_editor.save_requested.connect(self.save_track)
        self.adventure_editor.save_requested.connect(self.save_adventure)
        self.adventure_editor.add_existing_requested.connect(
            self.add_existing_tracks_to_adventure
        )
        self.adventure_editor.import_requested.connect(
            self.import_tracks_into_selected_adventure
        )
        self.adventure_editor.remove_requested.connect(
            self.remove_editor_track_from_adventure
        )
        self.adventure_editor.move_up_requested.connect(
            lambda: self.move_adventure_track(-1)
        )
        self.adventure_editor.move_down_requested.connect(
            lambda: self.move_adventure_track(1)
        )
        self.adventure_editor.track_visibility_requested.connect(
            self.set_track_visibility
        )
        self.adventure_editor.tracks_visibility_requested.connect(
            self.set_tracks_visibility
        )
        self.new_adventure_button.clicked.connect(self.create_adventure)
        self.delete_adventure_button.clicked.connect(self.delete_adventure)
        self.add_selected_to_adventure_button.clicked.connect(
            self.add_selected_tracks_to_adventure_dialog
        )
        self.adventure_list.currentItemChanged.connect(
            self.update_adventure_selection
        )
        self.adventure_list.itemChanged.connect(
            self.update_adventure_visibility
        )
        self.open_adventure_map_button.clicked.connect(self.open_map)
        self.collection_list.itemChanged.connect(
            self.update_collection_visibility
        )
        self.collection_visibility_header.stateChanged.connect(
            self.set_all_collections_visible
        )
        self.track_visibility_header.stateChanged.connect(
            self.set_all_filtered_tracks_visible
        )
        self.adventure_visibility_header.stateChanged.connect(
            self.set_all_adventures_visible
        )
        self.data_tabs.currentChanged.connect(self.switch_editor)
        self.photo_table.selectionModel().selectionChanged.connect(
            self.update_photo_selection
        )
        self.photo_search_edit.textChanged.connect(self.update_photo_filters)
        self.photo_track_filter.currentIndexChanged.connect(
            self.update_photo_filters
        )
        self.photo_adventure_filter.currentIndexChanged.connect(
            self.update_photo_filters
        )
        self.photo_editor.save_requested.connect(self.save_photo)
        self.photo_editor.bulk_assignment_requested.connect(self.assign_selected_photos_track)
        self.import_imagekit_button.clicked.connect(self.import_photos_from_imagekit)
        self.match_photos_button.clicked.connect(self.match_photos_to_tracks)
        self.load_collections()
        self.load_tracks()
        self.load_adventures()
        self.load_photos()

    def switch_editor(self, index: int) -> None:
        self.right_panel_stack.setCurrentIndex(index)

    def load_photos(self, selected_id: UUID | None = None) -> None:
        selected = [selected_id] if selected_id is not None else self._selected_photo_ids()
        tracks = self.database.list_tracks()
        selection = self.photo_table.selectionModel()
        with QSignalBlocker(selection):
            self.photo_model.set_photos(
                self.database.list_photos(),
                {track.id: track for track in tracks},
                self.database.list_track_adventure_memberships(),
            )
            self.photo_table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
            self.reload_photo_filters(tracks)
            selection.clearSelection()
            for row in range(self.photo_proxy.rowCount()):
                index = self.photo_proxy.index(row, 0)
                if index.data(PHOTO_ID_ROLE) in selected:
                    selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            visible = selection.selectedRows(0)
            if visible:
                selection.setCurrentIndex(visible[0], QItemSelectionModel.SelectionFlag.NoUpdate)
        self.update_photo_selection()

    def reload_photo_filters(self, tracks: list[Track] | None = None) -> None:
        tracks = tracks if tracks is not None else self.database.list_tracks()
        track_value = self.photo_track_filter.currentData()
        adventure_value = self.photo_adventure_filter.currentData()
        with QSignalBlocker(self.photo_track_filter):
            self.photo_track_filter.clear()
            self.photo_track_filter.addItem("All", None)
            self.photo_track_filter.addItem("Standalone", "standalone")
            for track in tracks:
                self.photo_track_filter.addItem(track.name, str(track.id))
            self.photo_track_filter.setCurrentIndex(
                max(self.photo_track_filter.findData(track_value), 0)
            )
        with QSignalBlocker(self.photo_adventure_filter):
            self.photo_adventure_filter.clear()
            self.photo_adventure_filter.addItem("All", None)
            self.photo_adventure_filter.addItem("Standalone", "standalone")
            for adventure in self.database.list_adventures():
                self.photo_adventure_filter.addItem(
                    adventure.name, str(adventure.uuid)
                )
            self.photo_adventure_filter.setCurrentIndex(
                max(self.photo_adventure_filter.findData(adventure_value), 0)
            )
        self.update_photo_filters()

    def update_photo_filters(self, *unused) -> None:
        del unused
        self.photo_proxy.set_filters(
            search=self.photo_search_edit.text(),
            track=self.photo_track_filter.currentData(),
            adventure=self.photo_adventure_filter.currentData(),
        )

    def _selected_photo_ids(self) -> list[UUID]:
        return [index.data(PHOTO_ID_ROLE)
                for index in self.photo_table.selectionModel().selectedRows(0)]

    def _current_photo_id(self) -> UUID | None:
        selected = self._selected_photo_ids()
        return selected[0] if len(selected) == 1 else None

    def _select_photo(self, photo_id: UUID) -> None:
        for row in range(self.photo_model.rowCount()):
            if self.photo_model.item(row, 0).data(PHOTO_ID_ROLE) == photo_id:
                index = self.photo_proxy.mapFromSource(
                    self.photo_model.index(row, 0)
                )
                if index.isValid():
                    self.photo_table.setCurrentIndex(index)
                return

    def update_photo_selection(self, *unused) -> None:
        tracks = self.database.list_tracks()
        photos = [photo for photo_id in self._selected_photo_ids()
                  if (photo := self.database.get_photo(photo_id)) is not None]
        if not photos:
            self.photo_editor.clear(tracks)
        elif len(photos) == 1:
            self.photo_editor.show_photo(photos[0], tracks)
        else:
            self.photo_editor.show_photos(photos, tracks)
        if self.data_tabs.currentIndex() == 3:
            self.right_panel_stack.setCurrentIndex(3)

    def assign_selected_photos_track(self) -> None:
        selected = self._selected_photo_ids()
        if len(selected) < 2 or self.photo_editor.track_combo.currentIndex() < 0:
            return
        track_id = self.photo_editor.selected_track_uuid
        track_name = self.photo_editor.track_combo.currentText()
        try:
            count = self.database.set_photos_track(selected, track_id)
        except sqlite3.Error:
            QMessageBox.critical(self, "Photo assignment", "Photos could not be assigned.")
            return
        self.load_photos()
        message = (f"Set {count} photos as Standalone." if track_id is None
                   else f"Assigned {count} photos to track '{track_name}'.")
        self.statusBar().showMessage(message, 5000)

    def save_photo(self) -> None:
        photo_id = self._current_photo_id()
        photo = self.database.get_photo(photo_id) if photo_id else None
        name = self.photo_editor.name_edit.text().strip()
        if photo is None or not name:
            return
        photo.name = name
        photo.description = self.photo_editor.description_edit.toPlainText()
        photo.track_uuid = self.photo_editor.selected_track_uuid
        try:
            self.database.update_photo(photo)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self, "Save Photo failed", f"The Photo could not be saved:\n{exc}"
            )
            return
        self.load_photos(photo.id)

    def match_photos_to_tracks(self) -> None:
        try:
            photos = self.database.list_photos()
            tracks = self.database.list_tracks()
            for track in tracks:
                track.points = self.database.list_track_points(track.id)
            results = preview_photo_matches(photos, PhotoTrackMatcher(tracks))
        except sqlite3.Error:
            QMessageBox.critical(self, "Photo Track Matching", "Photo and Track data could not be loaded.")
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Photo Track Matching")
        dialog.setText(match_summary(results))
        dialog.setStandardButtons(QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec() != QMessageBox.StandardButton.Apply:
            return
        try:
            applied = apply_photo_matches(self.database, results)
        except sqlite3.Error:
            self.load_photos()
            QMessageBox.critical(self, "Photo Track Matching", "Assignments could not all be saved. Review the Photos table.")
            return
        self.load_photos()
        QMessageBox.information(self, "Photo Track Matching", f"Matched {applied} photos to tracks.")

    def import_photos_from_imagekit(self) -> None:
        dialog = ImageKitImportDialog(self.database, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load_photos(dialog.imported[0].id if dialog.imported else None)

    def load_tracks(self) -> None:
        self.track_model.set_tracks(
            self.database.list_tracks(),
            self.database.list_track_adventure_memberships(),
            self._visible_track_ids,
        )
        self.track_table.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self.reload_track_adventure_filter()
        self.update_track_visibility_header()

    def reload_track_adventure_filter(self) -> None:
        current = self.track_adventure_filter.currentData()
        with QSignalBlocker(self.track_adventure_filter):
            self.track_adventure_filter.clear()
            self.track_adventure_filter.addItem("All", None)
            self.track_adventure_filter.addItem("Standalone", "standalone")
            for adventure in self.database.list_adventures():
                self.track_adventure_filter.addItem(
                    adventure.name, str(adventure.uuid)
                )
            index = self.track_adventure_filter.findData(current)
            self.track_adventure_filter.setCurrentIndex(max(index, 0))
        self.update_track_adventure_filter()

    def update_track_adventure_filter(self) -> None:
        self.track_proxy.set_adventure_filter(
            self.track_adventure_filter.currentData()
        )
        self.update_track_visibility_header()

    def update_track_search(self, text: str) -> None:
        self.track_proxy.set_search_text(text)
        self.update_track_visibility_header()

    def _current_track_id(self) -> UUID | None:
        index = self.track_table.currentIndex()
        if not index.isValid():
            return None
        source = self.track_proxy.mapToSource(index)
        return self.track_model.item(source.row(), 0).data(TRACK_ID_ROLE)

    def _selected_track_ids(self) -> list[UUID]:
        return [
            self.track_model.item(
                self.track_proxy.mapToSource(index).row(), 0
            ).data(TRACK_ID_ROLE)
            for index in self.track_table.selectionModel().selectedRows(1)
        ]

    def _select_track(self, track_id: UUID) -> None:
        for row in range(self.track_model.rowCount()):
            if self.track_model.item(row, 0).data(TRACK_ID_ROLE) == track_id:
                index = self.track_proxy.mapFromSource(
                    self.track_model.index(row, 1)
                )
                if not index.isValid():
                    return
                self.track_table.setCurrentIndex(index)
                self.track_table.selectionModel().setCurrentIndex(
                    index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
                return

    @staticmethod
    def _header_state(values: list[bool]) -> Qt.CheckState:
        if not values or not any(values):
            return Qt.CheckState.Unchecked
        if all(values):
            return Qt.CheckState.Checked
        return Qt.CheckState.PartiallyChecked

    @staticmethod
    def _set_header_state(
        header: VisibilityHeaderCheckBox, values: list[bool]
    ) -> None:
        with QSignalBlocker(header):
            header.setEnabled(bool(values))
            header.setCheckState(MainWindow._header_state(values))

    def update_collection_visibility_header(self) -> None:
        self._set_header_state(
            self.collection_visibility_header,
            [
                self.collection_list.item(row).checkState()
                == Qt.CheckState.Checked
                for row in range(self.collection_list.count())
            ],
        )

    def update_adventure_visibility_header(self) -> None:
        values = []
        for row in range(self.adventure_list.count()):
            item = self.adventure_list.item(row)
            if self.database.list_adventure_tracks(
                item.data(Qt.ItemDataRole.UserRole)
            ):
                values.append(item.checkState() == Qt.CheckState.Checked)
        self._set_header_state(
            self.adventure_visibility_header,
            values,
        )

    def _proxy_visible_track_ids(self) -> list[UUID]:
        return [
            self.track_model.item(
                self.track_proxy.mapToSource(
                    self.track_proxy.index(row, 0)
                ).row(), 0
            ).data(TRACK_ID_ROLE)
            for row in range(self.track_proxy.rowCount())
        ]

    def update_track_visibility_header(self) -> None:
        ids = self._proxy_visible_track_ids()
        self._set_header_state(
            self.track_visibility_header,
            [track_id in self._visible_track_ids for track_id in ids],
        )

    def set_all_collections_visible(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        with QSignalBlocker(self.collection_list):
            for row in range(self.collection_list.count()):
                item = self.collection_list.item(row)
                item.setCheckState(
                    Qt.CheckState.Checked if checked
                    else Qt.CheckState.Unchecked
                )
                collection_id = item.data(Qt.ItemDataRole.UserRole)
                if checked:
                    self._visible_collection_ids.add(collection_id)
                else:
                    self._visible_collection_ids.discard(collection_id)
        self.update_collection_visibility_header()
        self.refresh_map_visibility()

    def set_all_adventures_visible(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        track_ids = {
            track.id
            for row in range(self.adventure_list.count())
            for track in self.database.list_adventure_tracks(
                self.adventure_list.item(row).data(Qt.ItemDataRole.UserRole)
            )
        }
        self.set_tracks_visibility(list(track_ids), checked)

    def set_all_filtered_tracks_visible(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        track_ids = self._proxy_visible_track_ids()
        self.set_tracks_visibility(track_ids, checked)

    def load_adventures(self) -> None:
        with QSignalBlocker(self.adventure_list):
            self.adventure_list.clear()
            for adventure in self.database.list_adventures():
                tracks = self.database.list_adventure_tracks(adventure.uuid)
                item = QListWidgetItem(adventure.name)
                item.setData(Qt.ItemDataRole.UserRole, adventure.uuid)
                if tracks:
                    item.setFlags(
                        item.flags() | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsUserTristate
                    )
                item.setCheckState(self._header_state([
                    track.id in self._visible_track_ids for track in tracks
                ]))
                self.adventure_list.addItem(item)
        self.update_adventure_visibility_header()

    def reload_and_select_adventure(self, adventure_uuid: UUID) -> None:
        self.load_adventures()
        for index in range(self.adventure_list.count()):
            item = self.adventure_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == adventure_uuid:
                self.adventure_list.setCurrentItem(item)
                return
        self.adventure_editor.clear()

    def create_adventure(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "New Adventure", "Name:"
        )
        if not accepted or not name.strip():
            return
        adventure = Adventure(name.strip())
        self.database.save_adventure(adventure)
        self.load_adventures()
        for index in range(self.adventure_list.count()):
            item = self.adventure_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == adventure.uuid:
                self.adventure_list.setCurrentItem(item)
                break

    def update_adventure_selection(
        self, current: QListWidgetItem | None,
        previous: QListWidgetItem | None = None,
    ) -> None:
        del previous
        selected = current is not None
        self.delete_adventure_button.setEnabled(selected)
        self.adventure_editor.clear()
        if current is None:
            return
        adventure_uuid = current.data(Qt.ItemDataRole.UserRole)
        adventure = self.database.get_adventure(adventure_uuid)
        if adventure is not None:
            self.adventure_editor.show_adventure(
                adventure, self.database.list_adventure_tracks(adventure_uuid),
                self._visible_track_ids,
            )
            if self.data_tabs.currentIndex() == 2:
                self.right_panel_stack.setCurrentIndex(2)

    def update_adventure_visibility(self, item: QListWidgetItem) -> None:
        adventure_uuid = item.data(Qt.ItemDataRole.UserRole)
        track_ids = [
            track.id
            for track in self.database.list_adventure_tracks(adventure_uuid)
        ]
        self.set_tracks_visibility(
            track_ids, item.checkState() != Qt.CheckState.Unchecked
        )

    def _effective_visible_track_ids(self) -> set[UUID]:
        return set(self._visible_track_ids)

    def _sync_effective_track_visibility(self) -> None:
        effective = self._effective_visible_track_ids()
        if self.map_window is not None:
            for track_id in effective - self._shown_track_ids:
                self._show_track_on_map(track_id)
            for track_id in self._shown_track_ids - effective:
                self.map_window.hide_track(track_id)
        self._shown_track_ids = effective if self.map_window is not None else set()

    def refresh_map_visibility(self) -> None:
        self._sync_effective_track_visibility()
        self._sync_collection_visibility()

    def _sync_collection_visibility(self) -> None:
        if self.map_window is not None:
            for collection_id in (
                self._visible_collection_ids - self._shown_collection_ids
            ):
                self._show_collection_on_map(collection_id)
            for collection_id in (
                self._shown_collection_ids - self._visible_collection_ids
            ):
                self.map_window.hide_collection(collection_id)
        self._shown_collection_ids = (
            set(self._visible_collection_ids)
            if self.map_window is not None else set()
        )

    def save_adventure(self) -> None:
        item = self.adventure_list.currentItem()
        if item is None:
            return
        adventure = self.database.get_adventure(
            item.data(Qt.ItemDataRole.UserRole)
        )
        name = self.adventure_editor.name_edit.text().strip()
        if adventure is None or not name:
            return
        adventure.name = name
        adventure.description = (
            self.adventure_editor.description_edit.toPlainText()
        )
        self.database.update_adventure(adventure)
        self.load_tracks()
        self.load_adventures()
        self.load_photos()
        for index in range(self.adventure_list.count()):
            candidate = self.adventure_list.item(index)
            if candidate.data(Qt.ItemDataRole.UserRole) == adventure.uuid:
                self.adventure_list.setCurrentItem(candidate)
                break

    def edit_adventure(self) -> None:
        if self.adventure_list.currentItem() is not None:
            self.right_panel_stack.setCurrentIndex(2)
            self.adventure_editor.name_edit.setFocus()

    def delete_adventure(self) -> None:
        item = self.adventure_list.currentItem()
        if item is None:
            return
        if QMessageBox.question(
            self, "Delete Adventure", f'Delete Adventure "{item.text()}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Yes:
            return
        adventure_uuid = item.data(Qt.ItemDataRole.UserRole)
        self.database.delete_adventure(adventure_uuid)
        self.load_adventures()
        self.adventure_editor.clear()
        self.delete_adventure_button.setEnabled(False)
        self.load_tracks()
        self.refresh_track_visibility_views()
        self.load_photos()

    def add_selected_tracks_to_adventure(self) -> None:
        adventure_item = self.adventure_list.currentItem()
        if adventure_item is None:
            return
        adventure_uuid = adventure_item.data(Qt.ItemDataRole.UserRole)
        existing = {
            track.id for track in self.database.list_adventure_tracks(adventure_uuid)
        }
        for track_id in self._selected_track_ids():
            if track_id not in existing:
                self.database.add_track_to_adventure(adventure_uuid, track_id)
        self.update_adventure_selection(adventure_item)
        self.load_tracks()
        self.refresh_track_visibility_views()

    def add_selected_tracks_to_adventure_dialog(self) -> None:
        track_ids = self._selected_track_ids()
        adventures = self.database.list_adventures()
        if not track_ids or not adventures:
            return
        dialog = AdventureSelectionDialog(adventures, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        adventure_id = dialog.selected_destination
        if not isinstance(adventure_id, UUID):
            return
        self.database.add_tracks_to_adventure(adventure_id, track_ids)
        self.load_tracks()
        self.load_adventures()
        self.refresh_track_visibility_views()
        self.load_photos()

    def remove_selected_tracks_from_adventure(self) -> None:
        adventure_item = self.adventure_list.currentItem()
        if adventure_item is None:
            return
        adventure_uuid = adventure_item.data(Qt.ItemDataRole.UserRole)
        for track_id in self._selected_track_ids():
            self.database.remove_track_from_adventure(
                adventure_uuid, track_id
            )
        self.update_adventure_selection(adventure_item)
        self.load_tracks()
        self.refresh_track_visibility_views()
        self.load_photos()

    def add_existing_tracks_to_adventure(self) -> None:
        adventure_item = self.adventure_list.currentItem()
        if adventure_item is None:
            return
        adventure_uuid = adventure_item.data(Qt.ItemDataRole.UserRole)
        existing = {
            track.id for track in self.database.list_adventure_tracks(adventure_uuid)
        }
        dialog = AddTracksDialog(
            [track for track in self.database.list_tracks() if track.id not in existing],
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.database.add_tracks_to_adventure(
            adventure_uuid, dialog.selected_track_ids
        )
        self.load_tracks()
        self.update_adventure_selection(adventure_item)
        self.refresh_track_visibility_views()
        self.load_photos()

    def remove_editor_track_from_adventure(self) -> None:
        adventure_item = self.adventure_list.currentItem()
        track_ids = self.adventure_editor.selected_track_ids()
        if adventure_item is None or not track_ids:
            return
        adventure_id = adventure_item.data(Qt.ItemDataRole.UserRole)
        for track_id in track_ids:
            self.database.remove_track_from_adventure(adventure_id, track_id)
        self.load_tracks()
        self.update_adventure_selection(adventure_item)
        self.refresh_track_visibility_views()
        self.load_photos()

    def move_adventure_track(self, offset: int) -> None:
        adventure_item = self.adventure_list.currentItem()
        current_row = self.adventure_editor.current_track_row()
        if adventure_item is None or current_row < 0:
            return
        adventure_uuid = adventure_item.data(Qt.ItemDataRole.UserRole)
        tracks = self.database.list_adventure_tracks(adventure_uuid)
        target_row = current_row + offset
        if not 0 <= target_row < len(tracks):
            return
        tracks[current_row], tracks[target_row] = tracks[target_row], tracks[current_row]
        selected_id = tracks[target_row].id
        self.database.set_adventure_track_order(
            adventure_uuid, [track.id for track in tracks]
        )
        self.update_adventure_selection(adventure_item)
        self.adventure_editor.select_track(selected_id)

    def import_tracks_into_selected_adventure(self) -> None:
        item = self.adventure_list.currentItem()
        if item is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Tracks into Adventure", "", "GPX files (*.gpx)"
        )
        if not paths:
            return
        adventure_uuid = item.data(Qt.ItemDataRole.UserRole)
        try:
            tracks = import_gpx_files_to_adventure(
                self.database, paths, adventure_uuid
            )
        except (GpxReaderError, sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self, "Import Tracks failed", f"Tracks could not be imported:\n{exc}"
            )
            return
        self.load_tracks()
        self.update_adventure_selection(item)
        self.refresh_track_visibility_views()
        adventure = self.database.get_adventure(adventure_uuid)
        QMessageBox.information(
            self, "Import Tracks",
            f'Imported:\n- {len(paths)} GPX files\n- {len(tracks)} Tracks\n'
            f'- added to Adventure "{adventure.name}"',
        )

    def update_track_selection(
        self,
        current_item,
        previous_item=None,
    ) -> None:
        del previous_item
        selected = current_item.isValid()
        self.delete_track_button.setEnabled(selected)
        self.zoom_track_button.setEnabled(selected)
        self.track_editor.clear()
        if not selected:
            return
        source = self.track_proxy.mapToSource(current_item)
        track_id = self.track_model.item(source.row(), 0).data(TRACK_ID_ROLE)
        track = self.database.get_track(track_id)
        if track is not None:
            self.track_editor.show_track(
                track, self.database.list_track_points(track_id)
            )

    def update_track_visibility(self, track_id: UUID, visible: bool) -> None:
        self.set_track_visibility(track_id, visible)

    def get_track_visibility(self, track_id: UUID) -> bool:
        return track_id in self._visible_track_ids

    def set_track_visibility(self, track_id: UUID, visible: bool) -> None:
        self.set_tracks_visibility([track_id], visible)

    def set_tracks_visibility(
        self, track_ids: list[UUID], visible: bool
    ) -> None:
        for track_id in track_ids:
            if visible:
                self._visible_track_ids.add(track_id)
            else:
                self._visible_track_ids.discard(track_id)
        self.refresh_track_visibility_views()
        self.refresh_map_visibility()

    def refresh_track_visibility_views(self) -> None:
        self.track_model._loading = True
        try:
            for row in range(self.track_model.rowCount()):
                item = self.track_model.item(row, 0)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if item.data(TRACK_ID_ROLE) in self._visible_track_ids
                    else Qt.CheckState.Unchecked
                )
        finally:
            self.track_model._loading = False
        for track_id in {
            self.adventure_editor.track_model.item(row, 0).data(TRACK_ID_ROLE)
            for row in range(self.adventure_editor.track_model.rowCount())
        }:
            self.adventure_editor.set_track_visibility(
                track_id, track_id in self._visible_track_ids
            )
        self._refresh_adventure_check_states()
        self.update_track_visibility_header()

    def _refresh_adventure_check_states(self) -> None:
        with QSignalBlocker(self.adventure_list):
            for row in range(self.adventure_list.count()):
                item = self.adventure_list.item(row)
                tracks = self.database.list_adventure_tracks(
                    item.data(Qt.ItemDataRole.UserRole)
                )
                item.setCheckState(self._header_state([
                    track.id in self._visible_track_ids for track in tracks
                ]))
        self.update_adventure_visibility_header()

    def _show_track_on_map(self, track_id: UUID) -> None:
        if self.map_window is None:
            return
        track = self.database.get_track(track_id)
        if track is not None:
            self.map_window.show_track(
                track, self.database.list_track_points(track_id)
            )

    def import_track_gpx_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Track GPX", "", "GPX files (*.gpx)"
        )
        if not paths:
            return
        adventures = self.database.list_adventures()
        dialog = AdventureSelectionDialog(adventures, self, for_import=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dialog.selected_destination
        try:
            if choice == "standalone":
                tracks = import_gpx_files(self.database, paths)
            elif choice == "new":
                name, named = QInputDialog.getText(
                    self, "New Adventure", "Name:"
                )
                if not named or not name.strip():
                    return
                description, described = QInputDialog.getMultiLineText(
                    self, "New Adventure", "Description (optional):"
                )
                if not described:
                    return
                adventure = Adventure(name.strip(), description=description)
                tracks = import_gpx_files_to_adventure(
                    self.database, paths, adventure.uuid,
                    new_adventure=adventure,
                )
                self.load_adventures()
            elif isinstance(choice, UUID):
                tracks = import_gpx_files_to_adventure(
                    self.database, paths, choice
                )
            else:
                return
        except (GpxReaderError, sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self, "Import Track failed", f"The Track could not be imported:\n{exc}"
            )
            return
        self.load_tracks()
        if tracks:
            self.set_tracks_visibility([track.id for track in tracks], True)
            self._select_track(tracks[0].id)

    def delete_selected_track(self) -> None:
        track_id = self._current_track_id()
        if track_id is None:
            return
        answer = QMessageBox.question(
            self, "Delete Track", "Delete selected Track?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        adventure_item = self.adventure_list.currentItem()
        selected_adventure_uuid = (
            adventure_item.data(Qt.ItemDataRole.UserRole)
            if adventure_item is not None else None
        )
        self.database.delete_track(track_id)
        self._visible_track_ids.discard(track_id)
        if self.map_window is not None:
            self.map_window.hide_track(track_id)
        self._shown_track_ids.discard(track_id)
        self.load_tracks()
        if selected_adventure_uuid is not None:
            self.reload_and_select_adventure(selected_adventure_uuid)
        else:
            self.load_adventures()
        self.load_photos()
        self._sync_effective_track_visibility()

    def save_track(self) -> None:
        track_id = self._current_track_id()
        if track_id is None:
            return
        track = self.database.get_track(track_id)
        if track is None:
            return
        name = self.track_editor.name_edit.text().strip()
        color = QColor(self.track_editor.color_edit.text())
        if not name or not color.isValid():
            QMessageBox.warning(
                self, "Invalid Track", "Track name and color must be valid."
            )
            return
        track.name = name
        track.color = color.name(QColor.NameFormat.HexRgb).upper()
        self.database.update_track(track)
        if track_id in self._effective_visible_track_ids():
            self._show_track_on_map(track_id)
        self.load_tracks()
        self.load_photos()
        self._select_track(track_id)

    def zoom_to_selected_track(self) -> None:
        track_id = self._current_track_id()
        if track_id is None:
            return
        if track_id not in self._visible_track_ids:
            self.set_track_visibility(track_id, True)
        if self.map_window is not None:
            self.map_window.zoom_to_track(track_id)

    def create_collection(self) -> None:
        dialog = CollectionCreateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.collection_name
        if not name:
            QMessageBox.warning(
                self,
                "New Collection",
                "Collection name cannot be empty.",
            )
            return
        collection = Collection(name=name)
        try:
            self.database.save_collection(collection)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "New Collection failed",
                f"The Collection could not be created:\n{exc}",
            )
            return
        self._visible_collection_ids.add(collection.id)
        self.reload_and_select_collection(collection.id)

    def change_user_data_folder(self) -> None:
        dialog = UserDataFolderDialog(self.user_data_directory, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target = dialog.selected_directory.resolve()
        if target == self.user_data_directory:
            return
        try:
            verify_directory_writable(target)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "User data folder",
                f"The selected folder cannot be used:\n{exc}",
            )
            return

        choice = self._choose_user_data_folder_action(target)
        if choice is None:
            return
        try:
            if choice == "copy":
                collisions = existing_user_data_items(target)
                if collisions and not self._confirm_user_data_overwrite(
                    target,
                    collisions,
                ):
                    return
                copy_user_data(
                    self.user_data_directory,
                    target,
                    overwrite=bool(collisions),
                )
            else:
                initialize_user_data_directory(target)
        except (OSError, shutil.Error) as exc:
            QMessageBox.critical(
                self,
                "User data folder",
                f"The data folder could not be changed:\n{exc}",
            )
            return

        try:
            store_user_data_directory(self.settings, target)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "User data folder",
                f"The data folder setting could not be saved:\n{exc}",
            )
            return
        self._prompt_restart_after_data_folder_change()

    def _choose_user_data_folder_action(self, target: Path) -> str | None:
        existing = existing_user_data_items(target)
        contents = ", ".join(existing) if existing else "none"
        message = QMessageBox(self)
        message.setWindowTitle("Change user data folder")
        message.setText("How should WPT-Manager use the selected folder?")
        message.setInformativeText(
            f"Existing managed data in the selected folder: {contents}"
        )
        use_button = message.addButton(
            "Use existing data in selected folder",
            QMessageBox.ButtonRole.AcceptRole,
        )
        copy_button = message.addButton(
            "Copy current data to selected folder",
            QMessageBox.ButtonRole.ActionRole,
        )
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        if message.clickedButton() is use_button:
            return "existing"
        if message.clickedButton() is copy_button:
            return "copy"
        return None

    def _confirm_user_data_overwrite(
        self,
        target: Path,
        collisions: list[str],
    ) -> bool:
        answer = QMessageBox.warning(
            self,
            "Replace existing data?",
            f"The following items already exist in {target}:\n"
            + "\n".join(collisions)
            + "\n\nReplace them with the current data?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _prompt_restart_after_data_folder_change(self) -> None:
        if self._ask_restart_now():
            self._restart_application()

    def _ask_restart_now(self) -> bool:
        message = QMessageBox(self)
        message.setWindowTitle("Restart required")
        message.setText(
            "The data folder has been changed. WPT-Manager must restart."
        )
        restart_button = message.addButton(
            "Restart now",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message.addButton(
            "Restart later",
            QMessageBox.ButtonRole.RejectRole,
        )
        message.exec()
        return message.clickedButton() is restart_button

    def _restart_application(self) -> None:
        program, arguments = application_restart_command()
        started = QProcess.startDetached(
            program,
            arguments,
            str(Path.cwd()),
        )
        succeeded = started[0] if isinstance(started, tuple) else started
        if succeeded:
            if self.map_window is not None:
                self.map_window.close()
            self.close()
            QCoreApplication.quit()

    def load_collections(self) -> bool:
        try:
            collections = self.database.list_collections()
        except (sqlite3.Error, ValueError) as exc:
            self.collection_list.clear()
            self.waypoint_list.clear()
            self._set_map_waypoints([])
            self.clear_waypoint_editor()
            self.export_button.setEnabled(False)
            self.delete_collection_button.setEnabled(False)
            self.edit_collection_button.setEnabled(False)
            self.merge_collections_button.setEnabled(False)
            self.move_waypoints_button.setEnabled(False)
            QMessageBox.critical(
                self,
                "Load Collections failed",
                f"The Collections could not be loaded:\n{exc}",
            )
            return False

        if not self._visible_collection_ids and self.collection_list.count() == 0:
            self._visible_collection_ids.update(item.id for item in collections)
        with QSignalBlocker(self.collection_list):
            self.collection_list.clear()
            for collection in collections:
                item = QListWidgetItem(collection.name)
                item.setData(Qt.ItemDataRole.UserRole, collection.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked
                    if collection.id in self._visible_collection_ids
                    else Qt.CheckState.Unchecked
                )
                self.collection_list.addItem(item)
        self.merge_collections_button.setEnabled(
            self.collection_list.count() >= 2
        )
        self._update_move_waypoints_button()
        self.update_collection_visibility_header()
        return True

    def update_collection_visibility(self, item: QListWidgetItem) -> None:
        collection_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            self._visible_collection_ids.add(collection_id)
        else:
            self._visible_collection_ids.discard(collection_id)
        self.update_collection_visibility_header()
        self.refresh_map_visibility()

    def _refresh_map_collections(self, collection_ids: set[UUID]) -> None:
        """Refresh changed content using visibility state, never editor selection."""
        if self.map_window is None:
            return
        for collection_id in collection_ids:
            if collection_id in self._visible_collection_ids:
                self._show_collection_on_map(collection_id)
                self._shown_collection_ids.add(collection_id)
            else:
                self.map_window.hide_collection(collection_id)
                self._shown_collection_ids.discard(collection_id)

    def _show_collection_on_map(self, collection_id: UUID) -> None:
        if self.map_window is not None:
            self.map_window.show_collection(
                collection_id, self.database.list_waypoints(collection_id)
            )

    def open_merge_dialog(self) -> None:
        current_item = self.collection_list.currentItem()
        selected_target_id = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else None
        )
        dialog = CollectionMergeDialog(
            self.database,
            selected_target_id,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.merged_target_id is None:
            return

        target_id = dialog.merged_target_id
        self.reload_and_select_collection(target_id)

    def reload_and_select_collection(self, collection_id: UUID) -> None:
        if not self.load_collections():
            return
        for index in range(self.collection_list.count()):
            item = self.collection_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == collection_id:
                self.collection_list.setCurrentRow(index)
                break

    def load_waypoints(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
        *,
        fit_map_viewport: bool = True,
    ) -> bool:
        del previous_item
        self.waypoint_list.clear()
        self._set_map_waypoints([])
        self.clear_waypoint_editor()
        self.export_button.setEnabled(current_item is not None)
        self.delete_collection_button.setEnabled(current_item is not None)
        self.edit_collection_button.setEnabled(current_item is not None)
        if current_item is None:
            return True

        collection_id = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            waypoints = self.database.list_waypoints(
                collection_id,
                self.waypoint_sort_combo.currentData(),
            )
        except (sqlite3.Error, ValueError) as exc:
            self.waypoint_list.clear()
            self.clear_waypoint_editor()
            QMessageBox.critical(
                self,
                "Load Waypoints failed",
                f"The Waypoints could not be loaded:\n{exc}",
            )
            return False

        for waypoint in waypoints:
            item = QListWidgetItem(waypoint.name)
            item.setData(Qt.ItemDataRole.UserRole, waypoint.id)
            self.waypoint_list.addItem(item)
        self._set_map_waypoints(
            waypoints,
            fit_viewport=fit_map_viewport,
        )
        self.waypoint_list.viewport().update()
        return True

    def open_map(self) -> None:
        if self.map_window is None:
            self.map_window = MapWindow(
                self,
                legacy_config_path=self.user_data_directory / "config.json",
                icon_catalog=self.icon_catalog,
            )
            self.map_window.marker_clicked.connect(
                self._select_waypoint_from_map
            )
            self.map_window.add_waypoint_requested.connect(
                self.add_waypoint_from_map
            )
            self.map_window.add_search_result_requested.connect(
                self.add_waypoint_from_search_result
            )
            self.map_window.edit_waypoint_requested.connect(
                self.edit_waypoint_from_map
            )
            self.map_window.move_waypoint_requested.connect(
                self.move_waypoint_from_map
            )
            self.map_window.search_nearby_requested.connect(
                self.search_near_waypoint_from_map
            )
            self.map_window.open_waypoint_in_mapy_requested.connect(
                self.open_waypoint_in_mapy
            )
            self.map_window.delete_waypoint_requested.connect(
                self.delete_waypoint_from_map
            )
            self.map_window.destroyed.connect(self._map_window_destroyed)
        self.map_window.set_waypoints(self._map_waypoints)
        for collection_id in self._visible_collection_ids:
            self._show_collection_on_map(collection_id)
        self._shown_collection_ids = set(self._visible_collection_ids)
        self._shown_track_ids.clear()
        for track_id in self._effective_visible_track_ids():
            self._show_track_on_map(track_id)
            self._shown_track_ids.add(track_id)
        self.map_window.set_selected_waypoint_ids(
            self._selected_waypoint_ids
        )
        self.map_window.set_search_waypoint(
            self._selected_search_waypoint()
        )
        self.map_window.show()
        self.map_window.raise_()
        self.map_window.activateWindow()

    def _map_window_destroyed(self) -> None:
        self.map_window = None
        self._shown_track_ids.clear()
        self._shown_collection_ids.clear()

    def _set_map_waypoints(
        self,
        waypoints: list[Waypoint],
        fit_viewport: bool = True,
    ) -> None:
        self._map_waypoints = list(waypoints)
        if self.map_window is not None:
            self.map_window.set_waypoints(
                self._map_waypoints, fit_viewport=fit_viewport
            )
        item = self.collection_list.currentItem()
        if item is not None:
            collection_id = item.data(Qt.ItemDataRole.UserRole)
            self._refresh_map_collections({collection_id})

    def _update_map_waypoint(self, waypoint: Waypoint) -> None:
        self._map_waypoints = [
            waypoint if item.id == waypoint.id else item
            for item in self._map_waypoints
        ]
        if self.map_window is not None:
            self.map_window.set_waypoints(
                self._map_waypoints, fit_viewport=False
            )
            item = self.collection_list.currentItem()
            if item is not None:
                self._refresh_map_collections({item.data(Qt.ItemDataRole.UserRole)})

    def _sync_map_selection(self) -> None:
        self._selected_waypoint_ids = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.waypoint_list.selectedItems()
        ]
        if self.map_window is not None:
            self.map_window.set_selected_waypoint_ids(
                self._selected_waypoint_ids
            )
            self.map_window.set_search_waypoint(
                self._selected_search_waypoint()
            )

    def _selected_search_waypoint(self) -> Waypoint | None:
        if len(self._selected_waypoint_ids) != 1:
            return None
        selected_id = self._selected_waypoint_ids[0]
        return next(
            (
                waypoint
                for waypoint in self._map_waypoints
                if waypoint.id == selected_id
            ),
            None,
        )

    def _select_waypoint_from_map(self, waypoint_id: UUID) -> bool:
        try:
            collection_id = self.database.get_waypoint_collection_id(waypoint_id)
            waypoint = self.database.get_waypoint(waypoint_id)
        except (sqlite3.Error, ValueError):
            return False
        if collection_id is None or waypoint is None:
            return False
        collection_item = next(
            (self.collection_list.item(row)
             for row in range(self.collection_list.count())
             if self.collection_list.item(row).data(Qt.ItemDataRole.UserRole) == collection_id),
            None,
        )
        if collection_item is None:
            return False
        if self.collection_list.currentItem() is not collection_item:
            self.collection_list.setCurrentItem(collection_item)
        for index in range(self.waypoint_list.count()):
            item = self.waypoint_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == waypoint_id:
                self.waypoint_list.setCurrentItem(
                    item,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect,
                )
                return True
        return False

    def _map_waypoint_by_id(self, waypoint_id: UUID) -> Waypoint | None:
        try:
            return self.database.get_waypoint(waypoint_id)
        except (sqlite3.Error, ValueError):
            return None

    def edit_waypoint_from_map(self, waypoint_id: UUID) -> None:
        if not self._select_waypoint_from_map(waypoint_id):
            return
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if self.waypoint_list.currentItem() is not None:
            self.name_edit.setFocus()

    def move_waypoint_from_map(
        self,
        waypoint_id: UUID,
        latitude: float,
        longitude: float,
    ) -> None:
        waypoint = self._map_waypoint_by_id(waypoint_id)
        if waypoint is None:
            return

        if not self._confirm_waypoint_move(waypoint, latitude, longitude):
            return
        if not self._select_waypoint_from_map(waypoint_id):
            return

        moved_waypoint = replace(
            waypoint,
            latitude=latitude,
            longitude=longitude,
        )
        errors = validate_waypoint(moved_waypoint)
        if errors:
            QMessageBox.warning(
                self,
                "Invalid waypoint",
                "\n".join(errors),
            )
            return
        try:
            self.database.update_waypoint(moved_waypoint)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Move waypoint failed",
                f"The waypoint could not be moved:\n{exc}",
            )
            return

        collection_item = self.collection_list.currentItem()
        if collection_item is not None:
            self._reload_and_select_waypoint(
                waypoint_id,
                collection_item,
            )

    def _confirm_waypoint_move(
        self,
        waypoint: Waypoint,
        latitude: float,
        longitude: float,
    ) -> bool:
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Move waypoint")
        confirmation.setText(f'Move waypoint "{waypoint.name}"?')
        confirmation.setInformativeText(
            f"Old:\n{waypoint.latitude:.7f}, {waypoint.longitude:.7f}"
            f"\n\nNew:\n{latitude:.7f}, {longitude:.7f}"
        )
        move_button = confirmation.addButton(
            "Move", QMessageBox.ButtonRole.AcceptRole
        )
        confirmation.addButton(
            QMessageBox.StandardButton.Cancel
        )
        confirmation.setDefaultButton(move_button)
        confirmation.exec()
        return confirmation.clickedButton() is move_button

    def search_near_waypoint_from_map(self, waypoint_id: UUID) -> None:
        waypoint = self._map_waypoint_by_id(waypoint_id)
        if waypoint is None or self.map_window is None:
            return
        if self._select_waypoint_from_map(waypoint_id):
            self.map_window.prepare_search_near_waypoint(waypoint)

    def open_waypoint_in_mapy(self, waypoint_id: UUID) -> None:
        waypoint = self._map_waypoint_by_id(waypoint_id)
        if waypoint is None:
            return
        QDesktopServices.openUrl(
            build_mapy_show_url(waypoint.latitude, waypoint.longitude)
        )

    def delete_waypoint_from_map(self, waypoint_id: UUID) -> None:
        waypoint = self._map_waypoint_by_id(waypoint_id)
        if waypoint is None:
            return
        if not self._select_waypoint_from_map(waypoint_id):
            return
        self._confirm_and_delete_waypoints(
            [waypoint_id],
            f'Delete waypoint "{waypoint.name}"?',
            fit_map_viewport=False,
        )

    def add_waypoint_from_map(
        self,
        latitude: float,
        longitude: float,
    ) -> None:
        self.open_new_waypoint_dialog(latitude, longitude)

    def add_waypoint_from_search_result(
        self,
        result: MapSearchResult,
    ) -> None:
        self.open_new_waypoint_dialog(
            result.latitude,
            result.longitude,
            name=result.name,
            note=result.label,
            comment=result.location or "",
            clear_search_marker_on_success=True,
        )

    def open_new_waypoint_dialog(
        self,
        latitude: float,
        longitude: float,
        *,
        name: str = "",
        note: str = "",
        comment: str = "",
        clear_search_marker_on_success: bool = False,
    ) -> None:
        collections = [
            (
                self.collection_list.item(index).data(
                    Qt.ItemDataRole.UserRole
                ),
                self.collection_list.item(index).text(),
            )
            for index in range(self.collection_list.count())
        ]
        if not collections:
            QMessageBox.information(
                self,
                "Add waypoint",
                "Create a collection before adding a waypoint.",
            )
            return

        collection_item = self.collection_list.currentItem()
        selected_collection_id = (
            collection_item.data(Qt.ItemDataRole.UserRole)
            if collection_item is not None
            else None
        )

        initial_values = {}
        if name or note or comment:
            initial_values = {
                "name": name,
                "note": note,
                "comment": comment,
            }
        dialog = NewWaypointDialog(
            latitude,
            longitude,
            self.icon_catalog,
            collections,
            selected_collection_id,
            parent=self,
            **initial_values,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        waypoint = dialog.waypoint
        collection_id = dialog.collection_id
        if waypoint is None or collection_id is None:
            return

        try:
            self.database.save_waypoint(waypoint, collection_id)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Add waypoint failed",
                f"The waypoint could not be saved:\n{exc}",
            )
            return

        self._refresh_map_collections({collection_id})
        active_collection_item = self.collection_list.currentItem()
        active_collection_id = (
            active_collection_item.data(Qt.ItemDataRole.UserRole)
            if active_collection_item is not None
            else None
        )
        if (
            active_collection_item is not None
            and collection_id == active_collection_id
        ):
            reloaded = self._reload_and_select_waypoint(
                waypoint.id,
                active_collection_item,
            )
            if (
                reloaded
                and clear_search_marker_on_success
                and self.map_window is not None
            ):
                self.map_window.clear_search_result_marker()
            return

        collection_name = next(
            name
            for candidate_id, name in collections
            if candidate_id == collection_id
        )
        QMessageBox.information(
            self,
            "Waypoint saved",
            f'Waypoint was saved to collection "{collection_name}".',
        )

    def _reload_and_select_waypoint(
        self,
        waypoint_id: UUID,
        collection_item: QListWidgetItem,
    ) -> bool:
        if not self.load_waypoints(
            collection_item,
            fit_map_viewport=False,
        ):
            return False
        for index in range(self.waypoint_list.count()):
            item = self.waypoint_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == waypoint_id:
                self.waypoint_list.setCurrentItem(item)
                return True
        return False

    def reload_sorted_waypoints(self) -> None:
        collection_item = self.collection_list.currentItem()
        if collection_item is None:
            return

        selected_ids = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.waypoint_list.selectedItems()
        }
        current_item = self.waypoint_list.currentItem()
        current_id = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else None
        )
        self.waypoint_list.setUpdatesEnabled(False)
        loaded = False
        try:
            with QSignalBlocker(self.waypoint_list):
                loaded = self.load_waypoints(collection_item)
                if loaded:
                    for index in range(self.waypoint_list.count()):
                        item = self.waypoint_list.item(index)
                        waypoint_id = item.data(Qt.ItemDataRole.UserRole)
                        if waypoint_id in selected_ids:
                            item.setSelected(True)
                        if waypoint_id == current_id:
                            self.waypoint_list.setCurrentItem(
                                item,
                                QItemSelectionModel.SelectionFlag.NoUpdate,
                            )
        finally:
            self.waypoint_list.setUpdatesEnabled(True)
        self.waypoint_list.viewport().update()
        if not loaded:
            return
        self.update_waypoint_selection()

    def load_waypoint(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
    ) -> None:
        del previous_item
        self.clear_waypoint_editor()
        if current_item is None:
            return

        waypoint_id = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            waypoint = self.database.get_waypoint(waypoint_id)
        except (sqlite3.Error, ValueError) as exc:
            self.clear_waypoint_editor()
            QMessageBox.critical(
                self,
                "Load Waypoint failed",
                f"The Waypoint could not be loaded:\n{exc}",
            )
            return
        if waypoint is None:
            return

        self.waypoint_editor.show_waypoint(waypoint)

    def update_waypoint_selection(self) -> None:
        selected_items = self.waypoint_list.selectedItems()
        self._sync_map_selection()
        self.delete_waypoints_button.setEnabled(bool(selected_items))
        self._update_move_waypoints_button()
        self.clear_waypoint_editor()

        if len(selected_items) == 1:
            self.load_waypoint(selected_items[0])
            return

        if len(selected_items) > 1:
            try:
                waypoints = [
                    waypoint
                    for item in selected_items
                    if (waypoint := self.database.get_waypoint(
                        item.data(Qt.ItemDataRole.UserRole)
                    )) is not None
                ]
            except (sqlite3.Error, ValueError) as exc:
                self.clear_waypoint_editor()
                QMessageBox.critical(
                    self,
                    "Load Waypoints failed",
                    f"The selected Waypoints could not be loaded:\n{exc}",
                )
                return
            self.waypoint_editor.show_bulk(waypoints)
            return

        self.waypoint_editor.set_bulk_fields_enabled(False)

    def _update_move_waypoints_button(self) -> None:
        self.move_waypoints_button.setEnabled(
            bool(self.waypoint_list.selectedItems())
            and self.collection_list.count() > 1
        )

    def move_selected_waypoints(self) -> None:
        selected_items = self.waypoint_list.selectedItems()
        source_item = self.collection_list.currentItem()
        if not selected_items or source_item is None:
            return
        source_id = source_item.data(Qt.ItemDataRole.UserRole)
        try:
            targets = [
                collection
                for collection in self.database.list_collections()
                if collection.id != source_id
            ]
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Move Waypoints failed",
                f"Collections could not be loaded:\n{exc}",
            )
            return
        if not targets:
            QMessageBox.information(
                self,
                "Move Waypoints",
                "Create another Collection before moving Waypoints.",
            )
            self._update_move_waypoints_button()
            return

        dialog = MoveWaypointsDialog(len(selected_items), targets, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        target_id = dialog.target_collection_id
        if target_id is None:
            return
        waypoint_ids = [
            item.data(Qt.ItemDataRole.UserRole) for item in selected_items
        ]
        try:
            self.database.move_waypoints(waypoint_ids, target_id)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Move Waypoints failed",
                f"The Waypoint(s) could not be moved:\n{exc}",
            )
            return

        self.load_waypoints(source_item, fit_map_viewport=False)
        self._refresh_map_collections({source_id, target_id})
        target_name = next(
            collection.name
            for collection in targets
            if collection.id == target_id
        )
        QMessageBox.information(
            self,
            "Move Waypoints",
            f"{len(waypoint_ids)} waypoint(s) moved to {target_name}",
        )

    def delete_selected_waypoints(self) -> None:
        selected_items = self.waypoint_list.selectedItems()
        if not selected_items:
            return

        count = len(selected_items)
        self._confirm_and_delete_waypoints(
            [
                item.data(Qt.ItemDataRole.UserRole)
                for item in selected_items
            ],
            f"Delete {count} selected waypoint(s)?",
        )

    def _confirm_and_delete_waypoints(
        self,
        waypoint_ids: list[UUID],
        confirmation_text: str,
        *,
        fit_map_viewport: bool = True,
    ) -> None:
        answer = QMessageBox.question(
            self,
            "Delete waypoints",
            confirmation_text,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_waypoints(waypoint_ids)
        except sqlite3.Error as exc:
            QMessageBox.critical(
                self,
                "Delete waypoints failed",
                f"The waypoint(s) could not be deleted:\n{exc}",
            )
            return

        collection_item = self.collection_list.currentItem()
        if collection_item is not None:
            self.load_waypoints(
                collection_item,
                fit_map_viewport=fit_map_viewport,
            )
        else:
            self.waypoint_list.clear()
        self.clear_waypoint_editor()
        self.delete_waypoints_button.setEnabled(False)

    def delete_collection(self) -> None:
        current_item = self.collection_list.currentItem()
        if current_item is None:
            return

        current_index = self.collection_list.currentRow()
        collection_id = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            waypoint_count = len(
                self.database.list_waypoints(collection_id)
            )
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Delete collection failed",
                f"The collection could not be inspected:\n{exc}",
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete collection",
            f'Delete collection "{current_item.text()}" and '
            f"its {waypoint_count} waypoint(s)?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_collection(collection_id)
        except sqlite3.Error as exc:
            QMessageBox.critical(
                self,
                "Delete collection failed",
                f"The collection could not be deleted:\n{exc}",
            )
            return

        self._visible_collection_ids.discard(collection_id)
        self._refresh_map_collections({collection_id})

        self.load_collections()
        if self.collection_list.count() > 0:
            self.collection_list.setCurrentRow(
                min(current_index, self.collection_list.count() - 1)
            )
        else:
            self.waypoint_list.clear()
            self.clear_waypoint_editor()
            self.export_button.setEnabled(False)
            self.delete_collection_button.setEnabled(False)

    def edit_collection(self) -> None:
        current_item = self.collection_list.currentItem()
        if current_item is None:
            return
        collection_id = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            collection = self.database.get_collection(collection_id)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Edit Collection failed",
                f"The Collection could not be loaded:\n{exc}",
            )
            return
        if collection is None:
            QMessageBox.critical(
                self,
                "Edit Collection failed",
                "The Collection no longer exists.",
            )
            return

        dialog = CollectionEditDialog(collection, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            current_collection = self.database.get_collection(collection_id)
            if current_collection is None:
                raise ValueError("The Collection no longer exists.")
            current_collection.name = dialog.collection_name
            current_collection.description = dialog.collection_description
            self.database.update_collection(current_collection)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Edit Collection failed",
                f"The Collection could not be saved:\n{exc}",
            )
            return

        self.reload_and_select_collection(collection_id)

    def mark_bulk_field_changed(self, field: str) -> None:
        self.waypoint_editor.mark_bulk_field_changed(field)

    def clear_waypoint_editor(self) -> None:
        self.waypoint_editor.clear()

    def update_color_preview(self, color_value: str) -> None:
        self.waypoint_editor.update_color_preview(color_value)

    def choose_color(self) -> None:
        self.waypoint_editor.choose_color()

    def choose_icon(self) -> None:
        self.waypoint_editor.choose_icon()

    def update_icon_preview(self, icon_name: str) -> None:
        self.waypoint_editor.update_icon_preview(icon_name)

    def save_waypoint(self) -> None:
        selected_items = self.waypoint_list.selectedItems()
        if len(selected_items) > 1:
            self.save_bulk_waypoints(selected_items)
            return
        if len(selected_items) != 1:
            return
        current_item = selected_items[0]

        waypoint_id = current_item.data(Qt.ItemDataRole.UserRole)
        try:
            waypoint = self.database.get_waypoint(waypoint_id)
        except (sqlite3.Error, ValueError) as exc:
            self.clear_waypoint_editor()
            QMessageBox.critical(
                self,
                "Save waypoint failed",
                f"The waypoint could not be loaded:\n{exc}",
            )
            return
        if waypoint is None:
            self.clear_waypoint_editor()
            return

        values = self.waypoint_editor.values()
        waypoint.name = values.name
        waypoint.icon = values.icon
        waypoint.color = values.color
        waypoint.background = values.background
        waypoint.note = values.note
        waypoint.comment = values.comment

        errors = validate_waypoint(waypoint)
        if not QColor(waypoint.color).isValid():
            errors.append(
                "Waypoint color must be a valid Qt color or HEX value."
            )
        else:
            waypoint.color = QColor(waypoint.color).name(
                QColor.NameFormat.HexRgb
            ).upper()

        if errors:
            QMessageBox.warning(
                self,
                "Invalid waypoint",
                "\n".join(errors),
            )
            return

        try:
            self.database.update_waypoint(waypoint)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Save waypoint failed",
                f"The waypoint could not be saved:\n{exc}",
            )
            return

        current_item.setText(waypoint.name)
        self._update_map_waypoint(waypoint)
        self.load_waypoint(current_item)
        QMessageBox.information(
            self,
            "Save waypoint",
            f'Waypoint "{waypoint.name}" was saved.',
        )

    def save_bulk_waypoints(
        self,
        selected_items: list[QListWidgetItem],
    ) -> None:
        changed_fields = self.waypoint_editor.bulk_changed_fields
        if not changed_fields:
            return

        values = self.waypoint_editor.values()
        if "color" in changed_fields:
            color = QColor(values.color)
            if not color.isValid():
                QMessageBox.warning(
                    self,
                    "Invalid waypoint",
                    "Waypoint color must be a valid Qt color or HEX value.",
                )
                return
            color_value = color.name(QColor.NameFormat.HexRgb).upper()
        else:
            color_value = ""

        selected_ids = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in selected_items
        ]
        waypoints = []
        try:
            for waypoint_id in selected_ids:
                waypoint = self.database.get_waypoint(waypoint_id)
                if waypoint is None:
                    QMessageBox.critical(
                        self,
                        "Bulk update failed",
                        f"Waypoint does not exist: {waypoint_id}",
                    )
                    return
                if "icon" in changed_fields:
                    waypoint.icon = values.icon
                if "color" in changed_fields:
                    waypoint.color = color_value
                if "background" in changed_fields:
                    waypoint.background = values.background
                waypoints.append(waypoint)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Bulk update failed",
                f"The waypoints could not be loaded:\n{exc}",
            )
            return

        try:
            self.database.update_waypoints(waypoints)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Bulk update failed",
                f"The waypoints could not be updated:\n{exc}",
            )
            return

        collection_item = self.collection_list.currentItem()
        if collection_item is not None:
            self.load_waypoints(collection_item)
            self.waypoint_list.blockSignals(True)
            for index in range(self.waypoint_list.count()):
                item = self.waypoint_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) in selected_ids:
                    item.setSelected(True)
            self.waypoint_list.blockSignals(False)
            self.update_waypoint_selection()

        QMessageBox.information(
            self,
            "Bulk update",
            f"Updated {len(waypoints)} waypoints.",
        )

    def import_gpx_file(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import GPX",
            "",
            "GPX files (*.gpx)",
        )
        if not selected_path:
            return

        current_item = self.collection_list.currentItem()
        selected_target_id = (
            current_item.data(Qt.ItemDataRole.UserRole)
            if current_item is not None
            else None
        )
        try:
            dialog = GpxImportDialog(
                self.database,
                selected_path,
                selected_target_id,
                self,
            )
        except GpxReaderError as exc:
            QMessageBox.critical(
                self,
                "Import GPX failed",
                f"The GPX file could not be imported:\n{exc}",
            )
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_collection_id = (
            dialog.created_collection_id or dialog.merged_target_id
        )
        if selected_collection_id is not None:
            if dialog.created_collection_id is not None:
                self._visible_collection_ids.add(selected_collection_id)
            self.reload_and_select_collection(selected_collection_id)

    def export_gpx_file(self) -> None:
        current_item = self.collection_list.currentItem()
        if current_item is None:
            return

        collection_id = current_item.data(Qt.ItemDataRole.UserRole)
        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export GPX",
            f"{current_item.text()}.gpx",
            "GPX files (*.gpx)",
        )
        if not selected_path:
            return

        output_path = Path(selected_path)
        if output_path.suffix.lower() != ".gpx":
            output_path = Path(f"{selected_path}.gpx")

        try:
            export_collection_gpx(
                self.database,
                collection_id,
                output_path,
            )
        except (OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Export GPX failed",
                f"The collection could not be exported:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Export GPX",
            f'Collection "{current_item.text()}" was exported.',
        )
