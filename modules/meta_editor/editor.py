"""
META Editor — syntax-highlighted plain-text editor for GTA XML / meta files.

Supports:  vehicles.meta  handling.meta  carcols.meta  carvariations.meta
           and any .xml / .txt file.

No CodeWalker DLL required.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QFrame, QPlainTextEdit,
    QComboBox, QSplitter,
)
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import (
    QFont, QSyntaxHighlighter, QTextCharFormat, QColor,
    QTextDocument,
)

from core.ymt_service import YMTFile


# ---------------------------------------------------------------------------
# Syntax highlighter
# ---------------------------------------------------------------------------

class _XMLHighlighter(QSyntaxHighlighter):
    """Lightweight XML/meta syntax highlighter."""

    _RULES: list[tuple[str, str, bool]] = [
        # (pattern, colour_hex, bold)
        (r"<!--.*?-->",            "#6A9955", False),   # comments
        (r"<[!/]?[\w:.-]+",       "#569CD6", False),   # tag names
        (r"\/>|>|<",              "#808080", False),   # brackets
        (r'\b[\w:.-]+(?=\s*=)',   "#9CDCFE", False),   # attribute names
        (r'"[^"]*"',              "#CE9178", False),   # attribute values
        (r"(?<=>)[^<>]+(?=<)",    "#D4D4D4", False),   # text content
    ]

    def __init__(self, doc: QTextDocument) -> None:
        super().__init__(doc)
        self._compiled: list[tuple[QRegularExpression, QTextCharFormat]] = []
        for pattern, colour, bold in self._RULES:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colour))
            if bold:
                fmt.setFontWeight(700)
            self._compiled.append((QRegularExpression(pattern), fmt))

    def highlightBlock(self, text: str) -> None:
        for rx, fmt in self._compiled:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, str] = {
    "vehicles.meta": """\
<?xml version="1.0" encoding="UTF-8"?>
<CVehicleModelInfo__InitDataList>
  <InitDatas>
    <Item>
      <modelName>mycar</modelName>
      <txdName>mycar</txdName>
      <handlingId>MYCAR</handlingId>
      <gameName>MYCAR</gameName>
      <vehicleMakeName>CUSTOM</vehicleMakeName>
      <expressionDictName>null</expressionDictName>
      <expressionName>null</expressionName>
      <vehicleClass>VC_SUPER</vehicleClass>
      <vehicleType>AUTOMOBILE</vehicleType>
    </Item>
  </InitDatas>
</CVehicleModelInfo__InitDataList>
""",
    "handling.meta": """\
<?xml version="1.0" encoding="UTF-8"?>
<CHandlingDataMgr>
  <HandlingData>
    <Item type="CHandlingData">
      <handlingName>MYCAR</handlingName>
      <fMass value="1500.000000" />
      <fInitialDragCoeff value="10.000000" />
      <fDownforceModifier value="0.000000" />
      <fPopUpLightRotation value="0.000000" />
      <fDriveInertia value="1.000000" />
      <fClutchChangeRateScaleUpShift value="3.000000" />
      <fClutchChangeRateScaleDownShift value="3.000000" />
      <fDriveMaxFlatVel value="120.000000" />
      <fInitialDriveForce value="0.400000" />
      <fBrakeForce value="0.700000" />
      <fBrakeBiasFront value="0.500000" />
      <fHandBrakeForce value="0.600000" />
      <fSteeringLock value="40.000000" />
      <nInitialDriveGears value="6" />
      <fInitialDriveMaxFlatVel value="120.000000" />
    </Item>
  </HandlingData>
</CHandlingDataMgr>
""",
    "carcols.meta": """\
<?xml version="1.0" encoding="UTF-8"?>
<CVehicleModelInfoVarGlobal>
  <Kits>
    <Item>
      <kitName>0_default_modkit</kitName>
      <id value="0" />
    </Item>
  </Kits>
  <Lights />
</CVehicleModelInfoVarGlobal>
""",
    "carvariations.meta": """\
<?xml version="1.0" encoding="UTF-8"?>
<CVehicleModelInfoVariation>
  <variationData>
    <Item>
      <modelName>mycar</modelName>
      <colors>
        <Item>
          <indices content="char_array">
            0 0
          </indices>
        </Item>
      </colors>
    </Item>
  </variationData>
</CVehicleModelInfoVariation>
""",
}


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class MetaEditorWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._current_path: Optional[Path] = None
        self._opened_ymt_path: Optional[Path] = None
        self._dirty: bool = False
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        self._editor = QPlainTextEdit()
        self._editor.setObjectName("CodeEditor")
        self._editor.setFont(QFont("Consolas", 10))
        self._editor.setPlaceholderText("Open a file or load a template to begin…")
        self._editor.textChanged.connect(self._on_changed)
        self._highlighter = _XMLHighlighter(self._editor.document())
        layout.addWidget(self._editor, 1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("InfoLabel")
        self._status_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self._status_label)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        layout.addWidget(QLabel("META / XML Editor", objectName="PanelTitle"))

        # Template loader
        layout.addSpacing(20)
        layout.addWidget(QLabel("Template:"))
        self._template_combo = QComboBox()
        self._template_combo.addItem("— select —")
        self._template_combo.addItems(list(_TEMPLATES.keys()))
        self._template_combo.currentIndexChanged.connect(self._load_template)
        self._template_combo.setFixedWidth(200)
        layout.addWidget(self._template_combo)

        layout.addStretch()

        btn_open = QPushButton("Open File")
        btn_open.setObjectName("PrimaryButton")
        btn_open.clicked.connect(self._open_file)
        layout.addWidget(btn_open)

        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("SecondaryButton")
        self._btn_save.clicked.connect(self._save)
        layout.addWidget(self._btn_save)

        self._btn_save_as = QPushButton("Save As")
        self._btn_save_as.setObjectName("SecondaryButton")
        self._btn_save_as.clicked.connect(self._save_as)
        layout.addWidget(self._btn_save_as)

        return bar

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_changed(self) -> None:
        self._dirty = True

    def _load_template(self, index: int) -> None:
        if index <= 0:
            return
        key = self._template_combo.itemText(index)
        content = _TEMPLATES.get(key, "")
        if content:
            self._editor.setPlainText(content)
            self._current_path = None
            self._dirty = False
            self._status_label.setText(f"Template loaded: {key}")
        self._template_combo.setCurrentIndex(0)

    def _open_file(self) -> None:
        if self._dirty and self._editor.toPlainText():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Discard them?",
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return

        path, _ = QFileDialog.getOpenFileName(
            self, "Open META / XML File", "",
            "All Files (*);;META Files (*.meta);;XML Files (*.xml *.ymt.xml);;YMT Binary (*.ymt);;All Text (*.txt *.lua)",
        )
        if not path:
            return

        try:
            selected = Path(path)
            if selected.suffix.lower() == ".ymt":
                self._open_ymt_as_text(selected)
                return

            content = selected.read_text(encoding="utf-8", errors="replace")
            self._editor.setPlainText(content)
            self._current_path = selected
            self._opened_ymt_path = None
            self._dirty = False
            self._status_label.setText(path)
        except Exception as exc:
            QMessageBox.critical(self, "Error Opening File", str(exc))

    def _open_ymt_as_text(self, ymt_path: Path) -> None:
        ymt = YMTFile.load(ymt_path)
        xml_text = ymt._build_xml()
        self._editor.setPlainText(xml_text)
        self._opened_ymt_path = ymt_path
        self._current_path = ymt_path.with_suffix(ymt_path.suffix + ".xml")
        self._dirty = False
        self._status_label.setText(
            f"Loaded YMT as editable XML text: {ymt_path.name} (Save writes {self._current_path.name})"
        )

    def _save(self) -> None:
        if self._current_path is None:
            self._save_as()
            return
        self._write(self._current_path)

    def _save_as(self) -> None:
        if self._opened_ymt_path is not None:
            default_name = self._opened_ymt_path.with_suffix(self._opened_ymt_path.suffix + ".xml").name
        else:
            default_name = "output.meta"
        suggested = self._current_path.name if self._current_path else default_name
        out, _ = QFileDialog.getSaveFileName(
            self, "Save File", suggested,
            "META Files (*.meta);;XML Files (*.xml *.ymt.xml);;All Files (*)",
        )
        if not out:
            return
        self._current_path = Path(out)
        self._write(self._current_path)

    def _write(self, path: Path) -> None:
        try:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")
            self._dirty = False
            self._status_label.setText(f"Saved: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
