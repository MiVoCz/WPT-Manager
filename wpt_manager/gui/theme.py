import ctypes
import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QWidget


class _NativeTitleBarThemeFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            isinstance(watched, QWidget)
            and watched.isWindow()
            and event.type()
            in (QEvent.Type.Show, QEvent.Type.PaletteChange)
        ):
            _apply_windows_title_bar_theme(watched)
        return super().eventFilter(watched, event)


def install_native_title_bar_theming() -> None:
    """Keep native Windows title bars aligned with the Qt palette."""
    application = QApplication.instance()
    if application is None or hasattr(
        application,
        "_wpt_title_bar_theme_filter",
    ):
        return

    theme_filter = _NativeTitleBarThemeFilter(application)
    application.installEventFilter(theme_filter)
    application._wpt_title_bar_theme_filter = theme_filter


def _apply_windows_title_bar_theme(widget: QWidget) -> None:
    if sys.platform != "win32":
        return

    dark_mode = widget.palette().color(
        QPalette.ColorRole.Window
    ).lightness() < 128
    enabled = ctypes.c_int(dark_mode)
    window_handle = ctypes.c_void_p(int(widget.winId()))
    try:
        dwm_api = ctypes.windll.dwmapi

        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on current Windows builds and
        # 19 on early Windows 10 builds.
        result = dwm_api.DwmSetWindowAttribute(
            window_handle,
            20,
            ctypes.byref(enabled),
            ctypes.sizeof(enabled),
        )
        if result != 0:
            dwm_api.DwmSetWindowAttribute(
                window_handle,
                19,
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
    except (AttributeError, OSError):
        return
