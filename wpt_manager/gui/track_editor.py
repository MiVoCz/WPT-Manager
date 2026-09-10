from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.models.track import Track, TrackPoint


class TrackEditor(QGroupBox):
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Track editor", parent)
        self.name_edit = QLineEdit()
        self.color_edit = QLineEdit()
        self.color_button = QPushButton("Choose color")
        self.distance_edit = QLineEdit()
        self.point_count_edit = QLineEdit()
        self.segment_count_edit = QLineEdit()
        self.start_time_edit = QLineEdit()
        self.end_time_edit = QLineEdit()
        self.source_file_edit = QLineEdit()
        for widget in (
            self.distance_edit, self.point_count_edit, self.segment_count_edit,
            self.start_time_edit, self.end_time_edit, self.source_file_edit,
        ):
            widget.setReadOnly(True)
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        color_widget = QWidget()
        color_layout = QHBoxLayout(color_widget)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(self.color_edit)
        color_layout.addWidget(self.color_button)
        form.addRow("Color", color_widget)
        form.addRow("Distance", self.distance_edit)
        form.addRow("Point count", self.point_count_edit)
        form.addRow("Segment count", self.segment_count_edit)
        form.addRow("Start time", self.start_time_edit)
        form.addRow("End time", self.end_time_edit)
        form.addRow("Source file", self.source_file_edit)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        self.color_button.clicked.connect(self.choose_color)
        self.save_button.clicked.connect(self.save_requested)
        self.clear()

    def show_track(self, track: Track, points: list[TrackPoint]) -> None:
        self.name_edit.setText(track.name)
        self.color_edit.setText(track.color)
        self.distance_edit.setText(f"{track.distance_m / 1000:.1f} km")
        self.point_count_edit.setText(str(track.point_count))
        self.segment_count_edit.setText(
            str(len({point.segment_index for point in points}))
        )
        self.start_time_edit.setText(
            track.start_time.isoformat() if track.start_time else ""
        )
        self.end_time_edit.setText(
            track.end_time.isoformat() if track.end_time else ""
        )
        self.source_file_edit.setText(track.source_file)
        self._set_editing_enabled(True)

    def clear(self) -> None:
        for widget in (
            self.name_edit, self.color_edit, self.distance_edit,
            self.point_count_edit, self.segment_count_edit,
            self.start_time_edit, self.end_time_edit, self.source_file_edit,
        ):
            widget.clear()
        self._set_editing_enabled(False)

    def _set_editing_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.color_edit.setEnabled(enabled)
        self.color_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

    def choose_color(self) -> None:
        color = QColorDialog.getColor(
            QColor(self.color_edit.text()), self, "Track Color"
        )
        if color.isValid():
            self.color_edit.setText(
                color.name(QColor.NameFormat.HexRgb).upper()
            )
