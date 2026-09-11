"""Shared provider credential dialog; secrets never enter application preferences."""
from pathlib import Path
from typing import Literal

from wpt_manager.mapy_search import MapySearchClient
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
    def __init__(
        self, parent: QWidget | None = None, *,
        provider: Literal["imagekit", "mapy"] = "imagekit",
        legacy_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._mapy = provider == "mapy"
        self._legacy_path = legacy_path
        self._environment = credentials.mapy_environment_key if self._mapy else credentials.imagekit_environment_key
        self._get_saved = credentials.get_saved_mapy_api_key if self._mapy else credentials.get_saved_imagekit_private_key
        self._set_key = credentials.set_mapy_api_key if self._mapy else credentials.set_imagekit_private_key
        self._delete_key = credentials.delete_mapy_api_key if self._mapy else credentials.delete_imagekit_private_key
        self._resolve = (lambda: credentials.get_mapy_api_key(legacy_path)) if self._mapy else credentials.get_imagekit_private_key
        label = "Mapy.com" if self._mapy else "ImageKit"
        self.setWindowTitle(f"{label} settings")
        self._mapy_client: MapySearchClient | None = None
        self.worker: _ConnectionTest | None = None
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.environment_label = QLabel()
        self.environment_label.setWordWrap(True)
        if self._environment():
            self.environment_label.setText(
                f"{label} {'API key' if self._mapy else 'key'} is currently provided by environment variable. "
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
        form.addRow("API key" if self._mapy else "Private API key", self.key_edit)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(label))
        layout.addLayout(form)
        for widget in (self.environment_label, self.test_button, self.status_label,
                       self.remove_button, self.buttons):
            layout.addWidget(widget)
        self.legacy_label = QLabel()
        self.legacy_label.setWordWrap(True)
        self.migrate_button = QPushButton("Import legacy key")
        self.migrate_button.setVisible(self._mapy)
        self.legacy_label.setVisible(self._mapy)
        layout.addWidget(self.legacy_label)
        layout.addWidget(self.migrate_button)
        self.migrate_button.clicked.connect(self.import_legacy_key)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        self.test_button.clicked.connect(self.test_connection)
        self.remove_button.clicked.connect(self.remove_saved_key)
        self.key_edit.textChanged.connect(lambda: self.status_label.setText("Not tested"))
        self._refresh_saved()

    def _refresh_saved(self) -> None:
        try:
            saved = bool(self._get_saved())
        except credentials.CredentialStoreError:
            self.status_label.setText("Credential store unavailable")
            return
        self.key_edit.setPlaceholderText("Saved credential" if saved else "")
        self.remove_button.setEnabled(saved)
        self.status_label.setText(
            "Not tested" if saved or self._environment() else "Not configured"
        )

        if self._mapy:
            legacy = bool(credentials.get_legacy_mapy_api_key(self._legacy_path))
            self.migrate_button.setEnabled(legacy and not saved and not self._environment())
            self.legacy_label.setText(
                "Legacy config contains a Mapy.com key. Import it here, then remove "
                "mapy_api_key from any mixed config manually. While present, it remains "
                "a fallback even after Remove saved key." if legacy else ""
            )
            if legacy and not saved and not self._environment():
                self.status_label.setText("Legacy credential (not tested)")

    def import_legacy_key(self) -> None:
        try:
            credentials.migrate_legacy_mapy_api_key(self._legacy_path)
        except credentials.CredentialStoreError:
            self.status_label.setText("Credential store unavailable")
            return
        self._refresh_saved()

    def save(self) -> None:
        if self.key_edit.text() or self.key_edit.isModified():
            try:
                self._set_key(self.key_edit.text())
            except (ValueError, credentials.CredentialStoreError) as exc:
                self.status_label.setText(str(exc))
                return
        self.accept()

    def remove_saved_key(self) -> None:
        try:
            self._delete_key()
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
                key = self._resolve()
            except credentials.CredentialStoreError:
                self.status_label.setText("Credential store unavailable")
                return
        if not key:
            self.status_label.setText("Not configured")
            return
        self.status_label.setText("Testing...")
        self._set_busy(True)
        if self._mapy:
            self._mapy_client = MapySearchClient(key, self)
            self._mapy_client.connection_result.connect(self._mapy_test_finished)
            self._mapy_client.test_connection()
            return
        self.worker = _ConnectionTest(key, self)
        self.worker.result.connect(self.status_label.setText)
        self.worker.finished.connect(self._test_finished)
        self.worker.start()

    def _mapy_test_finished(self, status: str) -> None:
        self.status_label.setText(status)
        if self._mapy_client is not None:
            self._mapy_client.deleteLater()
            self._mapy_client = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.key_edit, self.test_button, self.remove_button, self.buttons, self.migrate_button):
            widget.setEnabled(not busy)

    def _test_finished(self) -> None:
        self._set_busy(False)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def done(self, result: int) -> None:
        # Keep the owner alive until the bounded request finishes, including Escape/X.
        if self.worker is not None or self._mapy_client is not None:
            return
        self.key_edit.clear()
        super().done(result)
