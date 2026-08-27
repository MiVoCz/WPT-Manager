import sqlite3
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.database import Database
from wpt_manager.gui.collection_edit_dialog import CollectionEditDialog
from wpt_manager.gui.collection_merge_dialog import CollectionMergeDialog
from wpt_manager.gui.gpx_import_dialog import GpxImportDialog
from wpt_manager.gui.map_window import MapWindow
from wpt_manager.gui.new_waypoint_dialog import NewWaypointDialog
from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.gui.waypoint_editor import WaypointEditor
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_exporter import export_collection_gpx
from wpt_manager.io.icon_catalog import load_icon_catalog
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_validator import validate_waypoint


class MainWindow(QMainWindow):
    def __init__(
        self,
        database: Database,
        icon_catalog: list[IconInfo] | None = None,
    ) -> None:
        super().__init__()
        install_native_title_bar_theming()
        self.database = database
        self.icon_catalog = (
            load_icon_catalog()
            if icon_catalog is None
            else icon_catalog
        )
        self.setWindowTitle("WPT-Manager")
        self.resize(1000, 700)

        self.collection_list = QListWidget()
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

        collection_panel = QGroupBox("Collections")
        collection_layout = QVBoxLayout(collection_panel)
        collection_layout.addWidget(self.collection_list)

        collection_buttons = QHBoxLayout()
        collection_buttons.addWidget(self.import_button)
        collection_buttons.addWidget(self.export_button)
        collection_buttons.addWidget(self.edit_collection_button)
        collection_buttons.addWidget(self.delete_collection_button)
        collection_layout.addLayout(collection_buttons)
        collection_layout.addWidget(self.merge_collections_button)
        collection_layout.addWidget(self.open_map_button)

        self.waypoint_list = QListWidget()
        self.waypoint_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.waypoint_sort_combo = QComboBox()
        self.waypoint_sort_combo.addItem("Name", "name")
        self.waypoint_sort_combo.addItem("Added", "created_at")
        self.delete_waypoints_button = QPushButton("Delete Waypoint(s)")
        self.delete_waypoints_button.setEnabled(False)

        waypoint_panel = QGroupBox("Waypoints")
        waypoint_layout = QVBoxLayout(waypoint_panel)
        waypoint_layout.addWidget(self.waypoint_sort_combo)
        waypoint_layout.addWidget(self.waypoint_list)
        waypoint_layout.addWidget(self.delete_waypoints_button)

        self.waypoint_editor = WaypointEditor(self.icon_catalog)
        self.map_window: MapWindow | None = None
        self._map_waypoints: list[Waypoint] = []
        self._selected_waypoint_ids: list[UUID] = []
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

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(collection_panel)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([250, 750])

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(self.main_splitter)
        self.setCentralWidget(central_widget)

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
        self.waypoint_sort_combo.currentIndexChanged.connect(
            self.reload_sorted_waypoints
        )
        self.waypoint_editor.save_requested.connect(self.save_waypoint)
        self.export_button.clicked.connect(self.export_gpx_file)
        self.load_collections()

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
            QMessageBox.critical(
                self,
                "Load Collections failed",
                f"The Collections could not be loaded:\n{exc}",
            )
            return False

        self.collection_list.clear()
        for collection in collections:
            item = QListWidgetItem(collection.name)
            item.setData(Qt.ItemDataRole.UserRole, collection.id)
            self.collection_list.addItem(item)
        self.merge_collections_button.setEnabled(
            self.collection_list.count() >= 2
        )
        return True

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
                icon_catalog=self.icon_catalog,
            )
            self.map_window.marker_clicked.connect(
                self._select_waypoint_from_map
            )
            self.map_window.add_waypoint_requested.connect(
                self.add_waypoint_from_map
            )
            self.map_window.destroyed.connect(self._map_window_destroyed)
        self.map_window.set_waypoints(self._map_waypoints)
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

    def _set_map_waypoints(
        self,
        waypoints: list[Waypoint],
        fit_viewport: bool = True,
    ) -> None:
        self._map_waypoints = list(waypoints)
        if self.map_window is not None:
            self.map_window.set_waypoints(
                self._map_waypoints,
                fit_viewport=fit_viewport,
            )

    def _update_map_waypoint(self, waypoint: Waypoint) -> None:
        self._map_waypoints = [
            waypoint if item.id == waypoint.id else item
            for item in self._map_waypoints
        ]
        if self.map_window is not None:
            self.map_window.set_waypoints(
                self._map_waypoints,
                fit_viewport=False,
            )

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

    def _select_waypoint_from_map(self, waypoint_id: UUID) -> None:
        for index in range(self.waypoint_list.count()):
            item = self.waypoint_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == waypoint_id:
                self.waypoint_list.setCurrentItem(item)
                return

    def add_waypoint_from_map(
        self,
        latitude: float,
        longitude: float,
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

        dialog = NewWaypointDialog(
            latitude,
            longitude,
            self.icon_catalog,
            collections,
            selected_collection_id,
            parent=self,
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
            self._reload_and_select_waypoint(
                waypoint.id,
                active_collection_item,
            )
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
    ) -> None:
        if not self.load_waypoints(
            collection_item,
            fit_map_viewport=False,
        ):
            return
        for index in range(self.waypoint_list.count()):
            item = self.waypoint_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == waypoint_id:
                self.waypoint_list.setCurrentItem(item)
                return

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

    def delete_selected_waypoints(self) -> None:
        selected_items = self.waypoint_list.selectedItems()
        if not selected_items:
            return

        count = len(selected_items)
        answer = QMessageBox.question(
            self,
            "Delete waypoints",
            f"Delete {count} selected waypoint(s)?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.database.delete_waypoints(
                [
                    item.data(Qt.ItemDataRole.UserRole)
                    for item in selected_items
                ]
            )
        except sqlite3.Error as exc:
            QMessageBox.critical(
                self,
                "Delete waypoints failed",
                f"The waypoint(s) could not be deleted:\n{exc}",
            )
            return

        collection_item = self.collection_list.currentItem()
        if collection_item is not None:
            self.load_waypoints(collection_item)
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
