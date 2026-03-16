from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.app_info import (
    APP_NAME,
    APP_ORG,
    APP_TITLE,
    APP_VERSION,
    DEFAULT_THEME_ID,
    ICON_REMOTE_URL,
    REPO_URL,
    THEME_SETTINGS_KEY,
    UPDATE_CHECK_URL,
)
from core.theme_service import load_theme_qss, theme_choices
from modules.clothing_builder.builder import ClothingBuilderWidget
from modules.home.home import HomeWidget
from modules.meta_editor.editor import MetaEditorWidget
from modules.resource_builder.builder import ResourceBuilderWidget
from modules.ytd_editor.editor import YTDEditorWidget
from modules.ymt_editor.editor import YMTEditorWidget


_NAV_ITEMS: list[tuple[str, str]] = [
    ("Home", "Overview, quick start, and help"),
    ("YTD Editor", "Open and edit GTA texture dictionaries (.ytd)"),
    ("YMT Editor", "Edit clothing metadata files (.ymt)"),
    ("META Editor", "Edit vehicles.meta, handling.meta, and other XML files"),
    ("Clothing Builder", "Build advanced clothing packs with GTA naming automation"),
    ("Resource Builder", "Create ready-to-use FiveM resource folders"),
]


class _SidebarButton(QPushButton):
    def __init__(self, text: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFixedHeight(54)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setObjectName("NavButton")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1100, 700)
        self.resize(1400, 860)

        self._nav_buttons: list[_SidebarButton] = []
        self._settings = QSettings(APP_ORG, APP_NAME)
        self._setup_ui()

        self._nav_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)
        QTimer.singleShot(750, self._start_update_check)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._home = HomeWidget()
        self._home.helpRequested.connect(self._show_help_dialog)
        self._stack.addWidget(self._home)
        self._stack.addWidget(YTDEditorWidget())
        self._stack.addWidget(YMTEditorWidget())
        self._stack.addWidget(MetaEditorWidget())
        self._stack.addWidget(ClothingBuilderWidget())
        self._stack.addWidget(ResourceBuilderWidget())
        root.addWidget(self._stack, 1)

        status = QStatusBar()
        status.setObjectName("StatusBar")
        status.showMessage("Ready")
        self.setStatusBar(status)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo_frame = QFrame()
        logo_frame.setObjectName("LogoFrame")
        logo_frame.setFixedHeight(72)
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setAlignment(Qt.AlignCenter)
        logo_label = QLabel("FiveForge")
        logo_label.setObjectName("LogoLabel")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo_label)
        layout.addWidget(logo_frame)

        for index, (label, tooltip) in enumerate(_NAV_ITEMS):
            btn = _SidebarButton(label, tooltip)
            btn.clicked.connect(lambda _checked, i=index: self._switch_module(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        theme_row = QFrame()
        theme_layout = QVBoxLayout(theme_row)
        theme_layout.setContentsMargins(14, 0, 14, 10)
        theme_layout.setSpacing(6)
        theme_label = QLabel("Theme")
        theme_label.setObjectName("InfoLabel")
        self._theme_combo = QComboBox()
        for theme_id, theme_label_text in theme_choices():
            self._theme_combo.addItem(theme_label_text, theme_id)
        saved_theme = self._settings.value(THEME_SETTINGS_KEY, DEFAULT_THEME_ID, type=str)
        idx = self._theme_combo.findData(saved_theme)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self._theme_combo)
        layout.addWidget(theme_row)

        help_btn = QPushButton("Help")
        help_btn.setObjectName("SecondaryButton")
        help_btn.clicked.connect(self._show_help_dialog)
        layout.addWidget(help_btn)

        credit_row = QFrame()
        credit_layout = QHBoxLayout(credit_row)
        credit_layout.setContentsMargins(8, 6, 8, 10)
        credit_layout.setSpacing(6)

        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("VersionLabel")
        credit_layout.addWidget(version)

        byline = QLabel("Made by Orvlyn")
        byline.setObjectName("VersionLabel")
        byline.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        credit_layout.addWidget(byline, 1)

        layout.addWidget(credit_row)

        return sidebar

    def _switch_module(self, index: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)
        self.statusBar().showMessage(_NAV_ITEMS[index][0], 2500)

    def _on_theme_changed(self, index: int) -> None:
        theme_id = self._theme_combo.itemData(index)
        if not theme_id:
            return
        app = QApplication.instance()
        if app is None:
            return
        base_dir = Path(__file__).resolve().parent.parent
        app.setStyleSheet(load_theme_qss(base_dir, str(theme_id)))
        self._settings.setValue(THEME_SETTINGS_KEY, str(theme_id))
        self.statusBar().showMessage(f"Theme applied: {self._theme_combo.currentText()}", 3000)

    def _show_help_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("FiveForge Help")
        dlg.resize(980, 700)
        layout = QVBoxLayout(dlg)

        search_row = QHBoxLayout()
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search help topics (example: ymt, naming, build, props)")
        btn_prev = QPushButton("Previous")
        btn_prev.setObjectName("SecondaryButton")
        btn_next = QPushButton("Next")
        btn_next.setObjectName("SecondaryButton")
        result_label = QLabel("Type to search")
        result_label.setObjectName("InfoLabel")

        search_row.addWidget(QLabel("Search:"))
        search_row.addWidget(search_box, 1)
        search_row.addWidget(btn_prev)
        search_row.addWidget(btn_next)
        search_row.addWidget(result_label)
        layout.addLayout(search_row)

        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(
            """
            <html>
            <head>
                <style>
                    body { font-family: 'Segoe UI'; line-height: 1.55; color: #dfe6ee; }
                    .hero { border: 1px solid #3a4a62; border-radius: 12px; padding: 16px; margin-bottom: 10px; background: #1a2230; }
                    .hero h1 { margin: 0 0 6px 0; font-size: 24px; color: #9ed5ff; }
                    .hero p { margin: 0; color: #c3d5e8; }
                    .grid { width: 100%; border-collapse: separate; border-spacing: 10px; }
                    .card { border: 1px solid #2f4057; border-radius: 12px; padding: 12px; vertical-align: top; background: #131a26; }
                    .card h2 { margin: 0 0 8px 0; font-size: 17px; color: #8fc8ff; }
                    .mini { margin-top: 8px; color: #9fb5ca; font-size: 12px; }
                    ul { margin: 0; padding-left: 18px; color: #d8e4ef; }
                    li { margin-bottom: 4px; }
                    .steps { margin: 0; padding-left: 18px; color: #d8e4ef; }
                    .links { margin-top: 10px; padding: 10px; border: 1px dashed #3a5474; border-radius: 10px; background: #0f1621; }
                    .links b { color: #8fc8ff; }
                    .links a { color: #7fc1ff; text-decoration: none; }
                    .links a:hover { text-decoration: underline; }
                </style>
            </head>
            <body>
                <div class='hero'>
                    <h1>FiveForge Help Center</h1>
                    <p>Clean, visual guidance for building, editing, packaging, and troubleshooting with less guesswork.</p>
                </div>

                <table class='grid'>
                    <tr>
                        <td class='card' width='50%'>
                            <h2>Clothing Builder Workflow</h2>
                            <ol class='steps'>
                                <li>Add files or folders containing .ydd and .ytd assets.</li>
                                <li>Review each entry: Gender, Cloth Type, Drawable Type, Position.</li>
                                <li>Set Project Name. Spaces are automatically converted to underscores.</li>
                                <li>Configure prop options when needed (cut hair and take off in car).</li>
                                <li>Build directly to your server resource path and restart the resource.</li>
                            </ol>
                            <div class='mini'>Tip: test one drawable set first, then scale to full pack.</div>
                        </td>
                        <td class='card' width='50%'>
                            <h2>In-Game Validation</h2>
                            <ul>
                                <li>Check stream has male/female and prop folders.</li>
                                <li>Confirm stream root contains gender .ymt files.</li>
                                <li>Confirm stream/creaturemetadata contains creaturemetadata .ymt.</li>
                                <li>Confirm root contains shop meta files and fxmanifest.</li>
                                <li>Use a clean cache restart when testing changed metadata behavior.</li>
                            </ul>
                        </td>
                    </tr>

                    <tr>
                        <td class='card'>
                            <h2>Editors</h2>
                            <ul>
                                <li>YTD Editor: texture dictionary editing.</li>
                                <li>YMT Editor: binary YMT open/save support.</li>
                                <li>META Editor: syntax highlighted XML/meta editing.</li>
                                <li>META open dialog starts at All Files.</li>
                            </ul>
                            <div class='mini'>Use META Editor for quick text-level fixes; use YMT Editor for binary save integrity.</div>
                        </td>
                        <td class='card'>
                            <h2>Resource Builder (Simple Clothing)</h2>
                            <ul>
                                <li>No ped/component setup required.</li>
                                <li>Packs files into a clean resource layout.</li>
                                <li>Preserves stream folder structure when provided.</li>
                                <li>Auto-generates fxmanifest when missing.</li>
                                <li>Best for re-packaging already structured resources quickly.</li>
                            </ul>
                        </td>
                    </tr>

                    <tr>
                        <td class='card'>
                            <h2>Build and Release</h2>
                            <ul>
                                <li>Run build_exe.bat from project root.</li>
                                <li>Distribute the full dist/FiveForge folder.</li>
                                <li>Users do not need Python installed.</li>
                                <li>Include native DLLs for YTD/YMT features.</li>
                            </ul>
                        </td>
                        <td class='card'>
                            <h2>Search and Support</h2>
                            <ul>
                                <li>Type in Search and press Enter or Next.</li>
                                <li>Use Previous to move backward.</li>
                                <li>Search wraps automatically.</li>
                                <li>When reporting issues, include exact file path and error text.</li>
                            </ul>
                        </td>
                    </tr>
                </table>

                <div class='links'>
                    <b>Official Links</b><br/>
                    Repository: <a href="__REPO_URL__">__REPO_URL__</a><br/>
                    Version feed: <a href="__UPDATE_URL__">__UPDATE_URL__</a><br/>
                    Icon (raw): <a href="__ICON_URL__">__ICON_URL__</a>
                </div>
            </body>
            </html>
            """
            .replace("__REPO_URL__", REPO_URL)
            .replace("__UPDATE_URL__", UPDATE_CHECK_URL)
            .replace("__ICON_URL__", ICON_REMOTE_URL)
        )
        layout.addWidget(text, 1)

        def _search(forward: bool = True) -> None:
            term = search_box.text().strip()
            if not term:
                result_label.setText("Type to search")
                return

            flags = QTextDocument.FindFlag(0)
            if not forward:
                flags = QTextDocument.FindBackward

            found = text.find(term, flags)
            if found:
                result_label.setText(f"Found: {term}")
                return

            if forward:
                text.moveCursor(QTextCursor.Start)
            else:
                text.moveCursor(QTextCursor.End)

            wrapped = text.find(term, flags)
            if wrapped:
                result_label.setText(f"Found (wrapped): {term}")
            else:
                result_label.setText("No matches")

        search_box.returnPressed.connect(lambda: _search(True))
        btn_next.clicked.connect(lambda: _search(True))
        btn_prev.clicked.connect(lambda: _search(False))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)

        dlg.exec()

    def _start_update_check(self) -> None:
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def _check_update_worker(self) -> None:
        try:
            with urllib.request.urlopen(UPDATE_CHECK_URL, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            return
        except Exception:
            return

        latest = str(payload.get("version", "")).strip()
        release_url = str(payload.get("url", "")).strip()
        if latest and self._is_newer_version(latest, APP_VERSION):
            QTimer.singleShot(0, lambda: self._show_update_prompt(latest, release_url))

    @staticmethod
    def _version_parts(value: str) -> list[int]:
        return [int(part) for part in re.findall(r"\d+", value)]

    @classmethod
    def _is_newer_version(cls, latest: str, current: str) -> bool:
        latest_parts = cls._version_parts(latest)
        current_parts = cls._version_parts(current)
        width = max(len(latest_parts), len(current_parts), 3)
        latest_parts.extend([0] * (width - len(latest_parts)))
        current_parts.extend([0] * (width - len(current_parts)))
        return latest_parts > current_parts

    def _show_update_prompt(self, latest: str, release_url: str) -> None:
        message = f"A newer version is available: {latest}\nCurrent version: {APP_VERSION}"
        if release_url:
            message += "\n\nOpen releases page now?"
            choice = QMessageBox.question(self, "Update Available", message, QMessageBox.Yes | QMessageBox.No)
            if choice == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(release_url))
            return
        QMessageBox.information(self, "Update Available", message)
