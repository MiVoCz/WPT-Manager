from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.gui.theme import install_native_title_bar_theming


class CollectionCreateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.setWindowTitle("New Collection")

        self.name_edit = QLineEdit()
        form = QFormLayout()
        form.addRow("Name:", self.name_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.create_button = self.button_box.addButton(
            "Create",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.button_box)

        self.name_edit.textChanged.connect(self._update_create_button)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self._update_create_button()

    @property
    def collection_name(self) -> str:
        return self.name_edit.text().strip()

    def _update_create_button(self) -> None:
        self.create_button.setEnabled(bool(self.collection_name))
