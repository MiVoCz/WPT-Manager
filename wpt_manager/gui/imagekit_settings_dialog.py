"""Small ImageKit settings dialog; secrets never enter application config."""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from wpt_manager import credential_store as credentials
from wpt_manager.photos.imagekit import (
    ImageKitPhotoSource, ImageKitAuthenticationError, ImageKitConnectionError,
)


class _ConnectionTest(QThread):
    result = Signal(str)

    def __init__(self, key: str, parent: QWidget) -> None:
        super().__init__(parent)
        self._key = key

    def run(self) -> None:
        try:
            ImageKitPhotoSource(self._key, timeout=5).test_connection()
            status = "Connected"
        except ImageKitAuthenticationError:
            status = "Invalid API key"
        except ImageKitConnectionError:
            status = "Network error"
        except Exception:
            status = "Unexpected API error"
        finally:
            self._key = ""
        self.result.emit(status)


class ImageKitSettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ImageKit settings")
        self.worker: _ConnectionTest | None = None
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.environment_label = QLabel()
        self.environment_label.setWordWrap(True)
        if credentials.imagekit_environment_key():
            self.environment_label.setText(
                "ImageKit key is currently provided by environment variable. "
                "Environment variable overrides saved credential. "
                "A newly entered key can be tested and saved, but will not be active."
            )
        self.status_label = QLabel("Not configured")
        self.test_button = QPushButton("Test connection")
        self.remove_button = QPushButton("Remove saved key")
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        form = QFormLayout()
        form.addRow("Private API key", self.key_edit)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("ImageKit"))
        layout.addLayout(form)
        for widget in (self.environment_label, self.test_button, self.status_label,
                       self.remove_button, self.buttons):
            layout.addWidget(widget)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.test_button.clicked.connect(self.test_connection)
        self.remove_button.clicked.connect(self.remove_saved_key)
        self.key_edit.textChanged.connect(lambda: self.status_label.setText("Not tested"))
        self._refresh_saved()

    def _refresh_saved(self) -> None:
        try:
            saved = bool(credentials.get_saved_imagekit_private_key())
        except credentials.CredentialStoreError:
            self.status_label.setText("Credential store unavailable")
            return
        self.key_edit.setPlaceholderText("Saved credential" if saved else "")
        self.remove_button.setEnabled(saved)
        self.status_label.setText(
            "Not tested" if saved or credentials.imagekit_environment_key() else "Not configured"
        )

    def save(self) -> None:
        if self.key_edit.text() or self.key_edit.isModified():
            try:
                credentials.set_imagekit_private_key(self.key_edit.text())
            except (ValueError, credentials.CredentialStoreError) as exc:
                self.status_label.setText(str(exc))
                return
        self.accept()

    def remove_saved_key(self) -> None:
        try:
            credentials.delete_imagekit_private_key()
        except credentials.CredentialStoreError:
            self.status_label.setText("Credential store unavailable")
            return
        self.key_edit.clear()
        self.key_edit.setModified(False)
        self._refresh_saved()

    def test_connection(self) -> None:
        if self.key_edit.text() or self.key_edit.isModified():
            key = self.key_edit.text().strip()
            if not key:
                self.status_label.setText("Enter a non-empty Private API key.")
                return
        else:
            try:
                key = credentials.get_imagekit_private_key()
            except credentials.CredentialStoreError:
                self.status_label.setText("Credential store unavailable")
                return
        if not key:
            self.status_label.setText("Not configured")
            return
        self.status_label.setText("Testing...")
        self._set_busy(True)
        self.worker = _ConnectionTest(key, self)
        self.worker.result.connect(self.status_label.setText)
        self.worker.finished.connect(self._test_finished)
        self.worker.start()

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.key_edit, self.test_button, self.remove_button, self.buttons):
            widget.setEnabled(not busy)

    def _test_finished(self) -> None:
        self._set_busy(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def done(self, result: int) -> None:
        # Keep the owner alive until the bounded request finishes, including Escape/X.
        if self.worker is not None:
            return
        self.key_edit.clear()
        super().done(result)
