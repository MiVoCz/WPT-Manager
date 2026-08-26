from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Signal, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.gui.icon_picker_dialog import IconPickerDialog
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint


@dataclass(frozen=True)
class WaypointEditorValues:
    name: str
    icon: str
    color: str
    background: str
    note: str
    comment: str


class WaypointEditor(QGroupBox):
    save_requested = Signal()

    def __init__(
        self,
        icon_catalog: list[IconInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Waypoint editor", parent)
        self.icon_catalog = icon_catalog
        self.icon_paths_by_name: dict[str, Path] = {}
        for icon in icon_catalog:
            self.icon_paths_by_name.setdefault(icon.icon_name, icon.svg_path)

        self.name_edit = QLineEdit()
        self.icon_edit = QLineEdit()
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(32, 32)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_button = QPushButton("Select...")
        self.color_edit = QLineEdit()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(24, 24)
        self.color_button = QPushButton("Choose color")
        self.background_combo = QComboBox()
        self.background_combo.setEditable(True)
        self.background_combo.addItems(["circle", "square", "octagon"])
        self.latitude_edit = QLineEdit()
        self.latitude_edit.setReadOnly(True)
        self.longitude_edit = QLineEdit()
        self.longitude_edit.setReadOnly(True)
        self.note_edit = QLineEdit()
        self.comment_edit = QTextEdit()
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)
        self.selection_label = QLabel()
        self.selection_label.setVisible(False)
        self.bulk_edit_mode = False
        self.bulk_changed_fields: set[str] = set()

        layout = QVBoxLayout(self)
        layout.addWidget(self.selection_label)
        form = QFormLayout()
        form.addRow(QLabel("Name"), self.name_edit)

        icon_editor = QWidget()
        icon_layout = QHBoxLayout(icon_editor)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addWidget(self.icon_edit)
        icon_layout.addWidget(self.icon_preview)
        icon_layout.addWidget(self.icon_button)
        form.addRow(QLabel("Icon"), icon_editor)

        color_editor = QWidget()
        color_layout = QHBoxLayout(color_editor)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(self.color_edit)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(self.color_button)
        form.addRow(QLabel("Color"), color_editor)
        form.addRow(QLabel("Background"), self.background_combo)
        form.addRow(QLabel("Latitude"), self.latitude_edit)
        form.addRow(QLabel("Longitude"), self.longitude_edit)
        form.addRow(QLabel("Note"), self.note_edit)
        form.addRow(QLabel("Comment"), self.comment_edit)
        layout.addLayout(form)
        layout.addWidget(self.save_button)

        self.save_button.clicked.connect(self.save_requested)
        self.color_button.clicked.connect(self.choose_color)
        self.icon_button.clicked.connect(self.choose_icon)
        self.icon_edit.textChanged.connect(self.update_icon_preview)
        self.icon_edit.textEdited.connect(
            lambda: self.mark_bulk_field_changed("icon")
        )
        self.color_edit.textEdited.connect(
            lambda: self.mark_bulk_field_changed("color")
        )
        self.background_combo.currentIndexChanged.connect(
            lambda: self.mark_bulk_field_changed("background")
        )
        self.background_combo.editTextChanged.connect(
            lambda: self.mark_bulk_field_changed("background")
        )

    def show_waypoint(self, waypoint: Waypoint) -> None:
        self.clear()
        self.set_bulk_fields_enabled(False)
        self.name_edit.setText(waypoint.name)
        self.icon_edit.setText(waypoint.icon)
        self.color_edit.setText(waypoint.color)
        self.update_color_preview(waypoint.color)
        self.background_combo.setCurrentText(waypoint.background)
        self.latitude_edit.setText(str(waypoint.latitude))
        self.longitude_edit.setText(str(waypoint.longitude))
        self.note_edit.setText(waypoint.note)
        self.comment_edit.setPlainText(waypoint.comment)
        self.save_button.setEnabled(True)

    def show_bulk(self, waypoints: list[Waypoint]) -> None:
        self.clear()
        if not waypoints:
            return
        self.bulk_edit_mode = True
        self.selection_label.setText(f"Selected waypoints: {len(waypoints)}")
        self.selection_label.setVisible(True)
        self.set_bulk_fields_enabled(True)
        blockers = [
            QSignalBlocker(self.icon_edit),
            QSignalBlocker(self.color_edit),
            QSignalBlocker(self.background_combo),
        ]
        self.icon_edit.setText(self._common_value(waypoints, "icon"))
        self.icon_edit.setPlaceholderText("(mixed)")
        self.color_edit.setText(self._common_value(waypoints, "color"))
        self.color_edit.setPlaceholderText("(mixed)")
        background = self._common_value(waypoints, "background")
        self.background_combo.setCurrentText(background)
        if not background:
            self.background_combo.setCurrentIndex(-1)
        del blockers
        self.update_icon_preview(self.icon_edit.text())
        self.update_color_preview(self.color_edit.text())
        self.bulk_changed_fields.clear()
        self.save_button.setEnabled(True)

    def clear(self) -> None:
        self.bulk_edit_mode = False
        self.bulk_changed_fields.clear()
        self.selection_label.clear()
        self.selection_label.setVisible(False)
        self.name_edit.clear()
        self.icon_edit.clear()
        self.icon_edit.setPlaceholderText("")
        self.color_edit.clear()
        self.color_edit.setPlaceholderText("")
        self.update_color_preview("")
        self.background_combo.setCurrentIndex(-1)
        self.latitude_edit.clear()
        self.longitude_edit.clear()
        self.note_edit.clear()
        self.comment_edit.clear()
        self.save_button.setEnabled(False)

    def values(self) -> WaypointEditorValues:
        return WaypointEditorValues(
            name=self.name_edit.text(),
            icon=self.icon_edit.text(),
            color=self.color_edit.text(),
            background=self.background_combo.currentText(),
            note=self.note_edit.text(),
            comment=self.comment_edit.toPlainText(),
        )

    def set_bulk_fields_enabled(self, bulk_mode: bool) -> None:
        for widget in (
            self.name_edit,
            self.latitude_edit,
            self.longitude_edit,
            self.note_edit,
            self.comment_edit,
        ):
            widget.setEnabled(not bulk_mode)
        for widget in (
            self.icon_edit,
            self.icon_preview,
            self.icon_button,
            self.color_edit,
            self.color_preview,
            self.color_button,
            self.background_combo,
        ):
            widget.setEnabled(True)

    def mark_bulk_field_changed(self, field: str) -> None:
        if self.bulk_edit_mode:
            self.bulk_changed_fields.add(field)

    def choose_color(self) -> None:
        selected_color = QColorDialog.getColor(
            QColor(self.color_edit.text()), self, "Select color"
        )
        if not selected_color.isValid():
            return
        color_value = selected_color.name(QColor.NameFormat.HexRgb).upper()
        self.color_edit.setText(color_value)
        self.update_color_preview(color_value)
        self.mark_bulk_field_changed("color")

    def choose_icon(self) -> None:
        dialog = IconPickerDialog(self.icon_catalog, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.selected_icon_name is not None:
                self.icon_edit.setText(dialog.selected_icon_name)
                self.mark_bulk_field_changed("icon")

    def update_color_preview(self, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            self.color_preview.setAutoFillBackground(False)
            self.color_preview.setPalette(QPalette())
            return
        palette = self.color_preview.palette()
        palette.setColor(QPalette.ColorRole.Window, color)
        self.color_preview.setPalette(palette)
        self.color_preview.setAutoFillBackground(True)

    def update_icon_preview(self, icon_name: str) -> None:
        svg_path = self.icon_paths_by_name.get(icon_name)
        if svg_path is None:
            self.icon_preview.clear()
            return
        icon = QIcon(str(svg_path))
        if icon.isNull():
            self.icon_preview.clear()
            return
        self.icon_preview.setPixmap(icon.pixmap(self.icon_preview.size()))

    @staticmethod
    def _common_value(waypoints: list[Waypoint], field: str) -> str:
        values = {getattr(waypoint, field) for waypoint in waypoints}
        return values.pop() if len(values) == 1 else ""
