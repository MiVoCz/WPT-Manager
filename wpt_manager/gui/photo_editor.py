from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track
from wpt_manager.gui.photo_preview import PhotoPreview


class PhotoEditor(QGroupBox):
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Photo editor", parent)
        self.name_edit = QLineEdit()
        self.description_edit = QPlainTextEdit()
        self.track_combo = QComboBox()
        self.preview_label = PhotoPreview(self)
        self.taken_at_edit = QLineEdit()
        self.latitude_edit = QLineEdit()
        self.longitude_edit = QLineEdit()
        self.altitude_edit = QLineEdit()
        self.source_type_edit = QLineEdit()
        self.source_url_edit = QLineEdit()
        self.external_id_edit = QLineEdit()
        for widget in (
            self.taken_at_edit, self.latitude_edit, self.longitude_edit,
            self.altitude_edit, self.source_type_edit, self.source_url_edit,
            self.external_id_edit,
        ):
            widget.setReadOnly(True)
        self.save_button = QPushButton("Save")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Preview"))
        layout.addWidget(self.preview_label)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Track", self.track_combo)
        form.addRow("Taken at", self.taken_at_edit)
        form.addRow("Latitude", self.latitude_edit)
        form.addRow("Longitude", self.longitude_edit)
        form.addRow("Altitude", self.altitude_edit)
        form.addRow("Source type", self.source_type_edit)
        form.addRow("Source URL", self.source_url_edit)
        form.addRow("External ID", self.external_id_edit)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addStretch()
        self.save_button.clicked.connect(self.save_requested)
        self.clear([])

    def show_photo(self, photo: Photo, tracks: list[Track]) -> None:
        self._set_tracks(tracks, photo.track_uuid)
        self.name_edit.setText(photo.name)
        self.description_edit.setPlainText(photo.description)
        self.taken_at_edit.setText(photo.taken_at.isoformat() if photo.taken_at else "")
        self.latitude_edit.setText("" if photo.latitude is None else str(photo.latitude))
        self.longitude_edit.setText("" if photo.longitude is None else str(photo.longitude))
        self.altitude_edit.setText("" if photo.altitude is None else str(photo.altitude))
        self.source_type_edit.setText(photo.source_type)
        self.source_url_edit.setText(photo.source_url or "")
        self.external_id_edit.setText(photo.external_id or "")
        self.preview_label.show_photo(photo)
        self._set_enabled(True)

    def clear(self, tracks: list[Track]) -> None:
        self._set_tracks(tracks, None)
        self.name_edit.clear()
        self.description_edit.clear()
        for widget in (
            self.taken_at_edit, self.latitude_edit, self.longitude_edit,
            self.altitude_edit, self.source_type_edit, self.source_url_edit,
            self.external_id_edit,
        ):
            widget.clear()
        self.preview_label.show_photo(None)
        self._set_enabled(False)

    def _set_tracks(self, tracks: list[Track], selected: UUID | None) -> None:
        self.track_combo.clear()
        self.track_combo.addItem("Standalone", None)
        for track in tracks:
            self.track_combo.addItem(track.name, str(track.id))
        index = self.track_combo.findData(str(selected) if selected else None)
        self.track_combo.setCurrentIndex(max(index, 0))

    def _set_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.description_edit.setEnabled(enabled)
        self.track_combo.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

    @property
    def selected_track_uuid(self) -> UUID | None:
        value = self.track_combo.currentData()
        return UUID(value) if value else None
