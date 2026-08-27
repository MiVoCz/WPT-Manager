from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QScreen, QWindow
from PySide6.QtWidgets import QApplication, QComboBox, QWidget


def _point(point: QPoint) -> str:
    return f"({point.x()}, {point.y()})"


def _object(value: QObject | None) -> str:
    if value is None:
        return "None"
    name = value.objectName()
    suffix = f" name={name!r}" if name else ""
    return f"{type(value).__name__}@0x{id(value):x}{suffix}"


def _window(value: QWindow | None) -> str:
    if value is None:
        return "None"
    return f"{_object(value)} geometry={value.geometry().getRect()}"


def _screen_name(screen: QScreen | None) -> str:
    return screen.name() if screen is not None else "None"


def print_screens() -> None:
    print("\nSCREENS")
    for screen in QGuiApplication.screens():
        print(
            f"  name={screen.name()!r} "
            f"geometry={screen.geometry().getRect()} "
            f"availableGeometry={screen.availableGeometry().getRect()} "
            f"dpr={screen.devicePixelRatio():.3f} "
            f"logicalDpi={screen.logicalDotsPerInch():.3f}"
        )


class PopupProbe(QObject):
    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self.combo = combo
        self.opening = 0
        application = QApplication.instance()
        if application is None:
            raise RuntimeError("QApplication must exist before PopupProbe.")
        application.installEventFilter(self)
        self._application = application

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.combo and event.type() == QEvent.Type.MouseButtonPress:
            self.opening += 1
            print(f"\n=== COMBO OPENING {self.opening} ===")
            self._print_combo()
            print_screens()
        if (
            isinstance(watched, QWidget)
            and event.type() == QEvent.Type.Show
            and watched.windowFlags() & Qt.WindowType.Popup
        ):
            QTimer.singleShot(0, lambda widget=watched: self._print_popup(widget))
        return super().eventFilter(watched, event)

    def _print_combo(self) -> None:
        combo = self.combo
        window = combo.window()
        handle = window.windowHandle()
        global_top_left = combo.mapToGlobal(QPoint(0, 0))
        print("COMBOBOX")
        print(f"  object={_object(combo)}")
        print(f"  geometry={combo.geometry().getRect()}")
        print(f"  rect={combo.rect().getRect()}")
        print(f"  globalTopLeft={_point(global_top_left)}")
        print(f"  window={_object(window)} geometry={window.geometry().getRect()}")
        print(f"  screen={_screen_name(handle.screen() if handle else None)!r}")
        print(f"  dpr={combo.devicePixelRatioF():.3f}")

    def _print_popup(self, popup: QWidget) -> None:
        if not popup.isVisible():
            return
        combo = self.combo
        combo_window = combo.window()
        combo_handle = combo_window.windowHandle()
        popup_handle = popup.windowHandle()
        combo_top_left = combo.mapToGlobal(QPoint(0, 0))
        expected = combo.mapToGlobal(QPoint(0, combo.height()))
        actual = popup.mapToGlobal(QPoint(0, 0))
        combo_screen = combo_handle.screen() if combo_handle else combo.screen()
        popup_screen = popup_handle.screen() if popup_handle else popup.screen()
        screen_at_popup = QGuiApplication.screenAt(actual)
        delta = actual - expected

        print("POPUP")
        print(f"  object={_object(popup)}")
        print(f"  geometry={popup.geometry().getRect()}")
        print(f"  frameGeometry={popup.frameGeometry().getRect()}")
        print(f"  globalTopLeft={_point(actual)}")
        print(f"  screen={_screen_name(popup_screen)!r}")
        print(f"  screenAtTopLeft={_screen_name(screen_at_popup)!r}")
        print(f"  dpr={popup.devicePixelRatioF():.3f}")
        print(f"  parent={_object(popup.parent())}")
        print(f"  windowParent={_window(popup_handle.parent() if popup_handle else None)}")
        print(
            "  transientParent="
            f"{_window(popup_handle.transientParent() if popup_handle else None)}"
        )
        print(f"  windowFlags=0x{popup.windowFlags().value:x}")
        print(f"  isWindow={popup.isWindow()} topLevel={popup.window() is popup}")

        print("COMPARISON")
        print(f"  mapWindowScreen={_screen_name(combo_screen)!r}")
        print(f"  popupScreen={_screen_name(popup_screen)!r}")
        print(f"  sameScreen={combo_screen is popup_screen}")
        print(f"  comboGlobalTopLeft={_point(combo_top_left)}")
        print(f"  expectedPopupBelowCombo={_point(expected)}")
        print(f"  actualMinusExpected={_point(delta)}")
        if combo_screen is not None:
            for screen in QGuiApplication.screens():
                if screen is combo_screen:
                    continue
                origin_delta = (
                    screen.geometry().topLeft()
                    - combo_screen.geometry().topLeft()
                )
                residual = delta - origin_delta
                print(
                    f"  againstScreenOrigin={screen.name()!r} "
                    f"originDelta={_point(origin_delta)} "
                    f"residual={_point(residual)}"
                )
        print(
            "  Reproduce repeatedly on each monitor; compare opening blocks "
            "and sameScreen/originDelta values."
        )

