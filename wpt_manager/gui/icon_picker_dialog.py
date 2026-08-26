from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.models.icon import IconInfo
from wpt_manager.gui.theme import install_native_title_bar_theming


class IconPickerDialog(QDialog):
    def __init__(
        self,
        catalog: list[IconInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.setWindowTitle("Select icon")
        self.setMinimumSize(800, 550)
        self.resize(900, 650)
        self.selected_icon_name: str | None = None
        self.catalog = catalog

        self.icons_by_group: dict[str, list[IconInfo]] = {}
        for icon in catalog:
            self.icons_by_group.setdefault(icon.group, []).append(icon)

        self.group_list = QListWidget()
        self.group_list.setMinimumWidth(140)
        self.group_list.setMaximumWidth(220)
        self.group_list.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search")

        self.icon_list = QListWidget()
        self.icon_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.icon_list.setIconSize(QSize(48, 48))
        self.icon_list.setGridSize(QSize(120, 90))
        self.icon_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.icon_list.setWordWrap(True)
        self.icon_list.setUniformItemSizes(True)
        self.icon_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.empty_label = QLabel("No icons available.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_panel = QWidget()
        icon_layout = QVBoxLayout(icon_panel)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addWidget(self.empty_label)
        icon_layout.addWidget(self.icon_list)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.addWidget(self.group_list)
        self.content_splitter.addWidget(icon_panel)
        self.content_splitter.setStretchFactor(0, 0)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setSizes([180, 700])

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.select_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )
        self.select_button.setText("Select")
        self.select_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.content_splitter, 1)
        layout.addWidget(self.button_box)

        self.group_list.currentItemChanged.connect(self.load_group)
        self.search_edit.textChanged.connect(self.refresh_icons)
        self.icon_list.currentItemChanged.connect(
            self.update_select_button
        )
        self.icon_list.itemDoubleClicked.connect(
            self.select_current_icon
        )
        self.button_box.accepted.connect(self.select_current_icon)
        self.button_box.rejected.connect(self.reject)

        for group in self.icons_by_group:
            self.group_list.addItem(group)

        if self.group_list.count() > 0:
            self.group_list.setCurrentRow(0)
        else:
            self.update_empty_state()

    def load_group(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
    ) -> None:
        del current_item
        del previous_item
        self.refresh_icons()

    def refresh_icons(self, search_text: str | None = None) -> None:
        del search_text
        self.icon_list.clear()
        query = self.search_edit.text().strip().casefold()

        if query:
            icons = [
                icon
                for icon in self.catalog
                if query in icon.icon_name.casefold()
            ]
        else:
            current_group = self.group_list.currentItem()
            icons = (
                self.icons_by_group[current_group.text()]
                if current_group is not None
                else []
            )

        for icon in icons:
            label = (
                f"{icon.icon_name}\n{icon.group}"
                if query
                else icon.icon_name
            )
            item = QListWidgetItem(
                QIcon(str(icon.svg_path)),
                label,
            )
            item.setData(Qt.ItemDataRole.UserRole, icon.icon_name)
            item.setData(Qt.ItemDataRole.UserRole + 1, icon.group)
            self.icon_list.addItem(item)
        self.update_empty_state()

    def update_empty_state(self) -> None:
        is_empty = self.icon_list.count() == 0
        self.empty_label.setVisible(is_empty)
        self.icon_list.setVisible(not is_empty)
        self.select_button.setEnabled(False)

    def update_select_button(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
    ) -> None:
        del previous_item
        self.select_button.setEnabled(current_item is not None)

    def select_current_icon(
        self,
        item: QListWidgetItem | None = None,
    ) -> None:
        selected_item = item or self.icon_list.currentItem()
        if selected_item is None:
            return

        self.selected_icon_name = selected_item.data(
            Qt.ItemDataRole.UserRole
        )
        self.accept()
