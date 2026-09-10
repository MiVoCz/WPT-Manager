from PySide6.QtCore import Signal, Qt, QSignalBlocker
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QLineEdit, QPushButton, QTextEdit,
    QVBoxLayout, QWidget, QHBoxLayout, QTableView, QAbstractItemView,
)

from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track
from wpt_manager.gui.track_table import TRACK_ID_ROLE, TrackTableModel
from wpt_manager.gui.visibility_header import VisibilityHeaderCheckBox


class AdventureEditor(QGroupBox):
    save_requested = Signal()
    add_existing_requested = Signal()
    import_requested = Signal()
    remove_requested = Signal()
    move_up_requested = Signal()
    move_down_requested = Signal()
    track_visibility_requested = Signal(object, bool)
    tracks_visibility_requested = Signal(list, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Adventure editor", parent)
        self.name_edit = QLineEdit()
        self.description_edit = QTextEdit()
        self.track_count_edit = QLineEdit()
        self.total_distance_edit = QLineEdit()
        self.track_table = QTableView()
        self.track_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.track_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.track_model = TrackTableModel()
        self.track_table.setModel(self.track_model)
        self.track_table.setColumnHidden(4, True)
        self.visibility_header = VisibilityHeaderCheckBox()
        self.add_existing_button = QPushButton("Add Existing Tracks...")
        self.import_button = QPushButton("Import Tracks...")
        self.remove_button = QPushButton("Remove from Adventure")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        self.track_count_edit.setReadOnly(True)
        self.total_distance_edit.setReadOnly(True)
        self.save_button = QPushButton("Save")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        tracks_widget = QWidget()
        tracks_layout = QVBoxLayout(tracks_widget)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.addWidget(self.visibility_header)
        tracks_layout.addWidget(self.track_table)
        form.addRow("Tracks in Adventure", tracks_widget)
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(0, 0, 0, 0)
        for button in (
            self.add_existing_button, self.import_button,
            self.remove_button, self.move_up_button, self.move_down_button,
        ):
            action_layout.addWidget(button)
        form.addRow(action_widget)
        form.addRow("Track count", self.track_count_edit)
        form.addRow("Total distance", self.total_distance_edit)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        self.save_button.clicked.connect(self.save_requested)
        self.add_existing_button.clicked.connect(self.add_existing_requested)
        self.import_button.clicked.connect(self.import_requested)
        self.remove_button.clicked.connect(self.remove_requested)
        self.move_up_button.clicked.connect(self.move_up_requested)
        self.move_down_button.clicked.connect(self.move_down_requested)
        self.track_model.visibility_changed.connect(
            self.track_visibility_requested
        )
        self.visibility_header.stateChanged.connect(
            self._set_all_visible
        )
        self.clear()

    def clear(self) -> None:
        self.name_edit.clear()
        self.description_edit.clear()
        self.track_count_edit.clear()
        self.total_distance_edit.clear()
        self.track_model.removeRows(0, self.track_model.rowCount())
        self._visible_ids: set = set()
        self._update_header()
        self._set_enabled(False)

    def _set_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.description_edit.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        for button in (
            self.add_existing_button, self.import_button,
            self.remove_button, self.move_up_button, self.move_down_button,
        ):
            button.setEnabled(enabled)

    def set_track_visibility(self, track_id, visible: bool) -> None:
        if visible:
            self._visible_ids.add(track_id)
        else:
            self._visible_ids.discard(track_id)
        self.track_model._loading = True
        try:
            for row in range(self.track_model.rowCount()):
                item = self.track_model.item(row, 0)
                if item.data(TRACK_ID_ROLE) == track_id:
                    item.setCheckState(
                        Qt.CheckState.Checked if visible
                        else Qt.CheckState.Unchecked
                    )
        finally:
            self.track_model._loading = False
        self._update_header()

    def show_adventure(
        self, adventure: Adventure, tracks: list[Track],
        visible_ids: set | None = None,
    ) -> None:
        self._visible_ids = set(visible_ids or set())
        self.name_edit.setText(adventure.name)
        self.description_edit.setPlainText(adventure.description)
        self.track_count_edit.setText(str(len(tracks)))
        self.total_distance_edit.setText(
            f"{sum(track.distance_m for track in tracks) / 1000:.1f} km"
        )
        self.track_model.set_tracks(tracks, {}, self._visible_ids)
        self._update_header()
        self._set_enabled(True)

    def selected_track_ids(self) -> list:
        return [
            index.data(TRACK_ID_ROLE)
            for index in self.track_table.selectionModel().selectedRows(1)
        ]

    def current_track_id(self):
        index = self.track_table.currentIndex()
        return index.data(TRACK_ID_ROLE) if index.isValid() else None

    def current_track_row(self) -> int:
        return self.track_table.currentIndex().row()

    def select_track(self, track_id) -> None:
        for row in range(self.track_model.rowCount()):
            if self.track_model.item(row, 0).data(TRACK_ID_ROLE) == track_id:
                self.track_table.selectRow(row)
                return

    def _update_header(self) -> None:
        states = [
            self.track_model.item(row, 0).checkState()
            == Qt.CheckState.Checked
            for row in range(self.track_model.rowCount())
        ]
        state = (
            Qt.CheckState.Unchecked if not states or not any(states)
            else Qt.CheckState.Checked if all(states)
            else Qt.CheckState.PartiallyChecked
        )
        with QSignalBlocker(self.visibility_header):
            self.visibility_header.setEnabled(bool(states))
            self.visibility_header.setCheckState(state)

    def _set_all_visible(self, state: int) -> None:
        visible = Qt.CheckState(state) == Qt.CheckState.Checked
        ids = [
            self.track_model.item(row, 0).data(TRACK_ID_ROLE)
            for row in range(self.track_model.rowCount())
        ]
        self.tracks_visibility_requested.emit(ids, visible)
