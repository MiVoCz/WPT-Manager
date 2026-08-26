from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.models.collection import Collection


class CollectionEditDialog(QDialog):
    def __init__(
        self,
        collection: Collection,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.setWindowTitle("Edit Collection")

        self.name_edit = QLineEdit(collection.name)
        self.description_edit = QTextEdit()
        self.description_edit.setPlainText(collection.description)

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Description:", self.description_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.save_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Save
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.button_box)

        self.name_edit.textChanged.connect(self.update_save_button)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.update_save_button()

    def update_save_button(self) -> None:
        self.save_button.setEnabled(bool(self.collection_name))

    @property
    def collection_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def collection_description(self) -> str:
        return self.description_edit.toPlainText()
