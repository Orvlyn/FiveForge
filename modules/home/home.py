from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class HomeWidget(QWidget):
    helpRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(10)

        title = QLabel("Welcome to FiveForge")
        title.setObjectName("HeroTitle")
        subtitle = QLabel(
            "Build GTA V and FiveM resources faster. Use the sidebar to open an editor, or start with Clothing Builder for end-to-end pack output."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("HeroBody")

        actions = QHBoxLayout()
        actions.addStretch()
        help_btn = QPushButton("Open Help")
        help_btn.setObjectName("PrimaryButton")
        help_btn.clicked.connect(self.helpRequested.emit)
        actions.addWidget(help_btn)

        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        hero_layout.addLayout(actions)

        tips = QFrame()
        tips.setObjectName("InfoCard")
        tips_layout = QVBoxLayout(tips)
        tips_layout.setContentsMargins(18, 16, 18, 16)
        tips_layout.setSpacing(8)

        tips_title = QLabel("Quick Start")
        tips_title.setObjectName("SectionGroupLabel")
        tips_layout.addWidget(tips_title)

        lines = [
            "1. Load .ydd/.ytd assets in Clothing Builder and set Project name.",
            "2. Build to generate stream folders, .ymt binaries, .meta files, and fxmanifest.",
            "3. Use Resource Builder to reorganize and package existing assets quickly.",
            "4. Use YTD/YMT editors when you need direct file-level edits.",
            "5. Run from dist/FiveForge/FiveForge.exe after packaging.",
        ]
        for text in lines:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setObjectName("InfoLabel")
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            tips_layout.addWidget(lbl)

        root.addWidget(hero)
        root.addWidget(tips)
        root.addStretch(1)
