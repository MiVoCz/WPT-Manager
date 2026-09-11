from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from wpt_manager.models.photo import Photo
from wpt_manager.photos.imagekit import build_imagekit_preview_url


def photo_preview_url(photo: Photo) -> str | None:
    if photo.thumbnail_url:
        return photo.thumbnail_url
    if photo.source_url and photo.source_type == "imagekit":
        return build_imagekit_preview_url(photo.source_url)
    return photo.source_url


class PhotoPreview(QLabel):
    """Asynchronous preview with selection isolation and a bounded memory cache."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("No photo selected", parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(300, 200)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._generation = 0
        self._original = QPixmap()
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    def show_photo(self, photo: Photo | None) -> None:
        self._generation += 1
        self._timer.stop()
        old, self._reply = self._reply, None
        if old is not None:
            old.abort()
        self._original = QPixmap()
        self.clear()
        if photo is None:
            self.setText("No photo selected")
            return
        try:
            url = photo_preview_url(photo)
        except ValueError:
            url = None
        if not url:
            self.setText("No preview available")
            return
        if url in self._cache:
            self._original = self._cache[url]
            self._cache.move_to_end(url)
            self._scale()
            return
        target = QUrl.fromLocalFile(str(Path(url).absolute())) if Path(url).is_absolute() else QUrl(url)
        if not target.isValid() or target.scheme() not in {"http", "https", "file"}:
            self.setText("Failed to load preview")
            return
        request = QNetworkRequest(target)
        request.setTransferTimeout(15000)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        self.setText("Loading...")
        reply = self._network.get(request)
        self._reply = reply
        generation = self._generation
        reply.finished.connect(lambda: self._finished(reply, generation, url))
        reply.downloadProgress.connect(lambda received, total: self._progress(reply, received, total))
        self._timer.start(15000)

    def _progress(self, reply: QNetworkReply, received: int, total: int) -> None:
        if reply is self._reply and max(received, total) > 10 * 1024 * 1024:
            reply.abort()

    def _timeout(self) -> None:
        if self._reply is not None:
            self._reply.abort()

    def _finished(self, reply: QNetworkReply, generation: int, url: str) -> None:
        reply.deleteLater()
        if generation != self._generation or reply is not self._reply:
            return
        self._reply = None
        self._timer.stop()
        pixmap = QPixmap()
        if reply.error() != QNetworkReply.NetworkError.NoError or not pixmap.loadFromData(reply.readAll()):
            self.setText("Failed to load preview")
            return
        self._original = pixmap.scaled(600, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._cache[url] = self._original
        if len(self._cache) > 32:
            self._cache.popitem(last=False)
        self._scale()

    def _scale(self) -> None:
        if not self._original.isNull():
            self.setPixmap(self._original.scaled(
                self.contentsRect().size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._scale()
