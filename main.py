import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from app.main_window import MainWindow
from core.app_info import (
    APP_NAME,
    APP_ORG,
    APP_VERSION,
    DEFAULT_THEME_ID,
    ICON_RELATIVE_PATH,
    THEME_SETTINGS_KEY,
)
from core.theme_service import load_theme_qss


def main() -> None:
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    base_dir = Path(__file__).parent

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ORG)

    settings = QSettings(APP_ORG, APP_NAME)
    theme_id = settings.value(THEME_SETTINGS_KEY, DEFAULT_THEME_ID, type=str)
    app.setStyleSheet(load_theme_qss(base_dir, theme_id))

    icon_path = base_dir / ICON_RELATIVE_PATH
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
