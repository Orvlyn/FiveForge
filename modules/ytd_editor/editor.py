"""
YTD Editor — open, preview, replace, and export textures in a .ytd file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QListWidget, QListWidgetItem, QLabel,
    QFileDialog, QMessageBox, QFrame, QProgressBar,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QImage

from core.ytd_service import YTDFile, dds_bytes_to_qimage


# ---------------------------------------------------------------------------
# Background loader so the UI stays responsive on large YTDs
# ---------------------------------------------------------------------------

class _LoadWorker(QThread):
    finished: Signal = Signal(object)
    error: Signal = Signal(str)

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            self.finished.emit(YTDFile.load(self._path))
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Texture preview widget
# ---------------------------------------------------------------------------

class _PreviewLabel(QLabel):
    def __init__(self) -> None:
        super().__init__("No texture selected")
        self.setObjectName("TexturePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(256, 256)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def show_dds(self, dds_data: bytes) -> None:
        if not dds_data:
            self.setText("No data")
            return
        qimg = dds_bytes_to_qimage(dds_data)
        if qimg is None:
            self.setText("Preview unavailable\n(unsupported DDS format)")
            return
        pixmap = QPixmap.fromImage(qimg)
        self.setPixmap(
            pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # Re-scale if we already have a pixmap
        if self.pixmap() and not self.pixmap().isNull():
            scaled = self.pixmap().scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.setPixmap(scaled)


# ---------------------------------------------------------------------------
# Main editor widget
# ---------------------------------------------------------------------------

class YTDEditorWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._ytd: Optional[YTDFile] = None
        self._worker: Optional[_LoadWorker] = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.setSizes([280, 720])
        layout.addWidget(splitter, 1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        layout.addWidget(QLabel("YTD Texture Editor", objectName="PanelTitle"))
        layout.addStretch()

        self._btn_open = QPushButton("Open YTD")
        self._btn_open.setObjectName("PrimaryButton")
        self._btn_open.clicked.connect(self._open_ytd)
        layout.addWidget(self._btn_open)

        self._btn_save = QPushButton("Save YTD")
        self._btn_save.setObjectName("SecondaryButton")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self._save_ytd)
        layout.addWidget(self._btn_save)

        return bar

    def _build_list_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("ListPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Textures", objectName="SectionHeader")
        layout.addWidget(header)

        self._tex_list = QListWidget()
        self._tex_list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._tex_list)

        return panel

    def _build_preview_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PreviewPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        self._preview = _PreviewLabel()
        layout.addWidget(self._preview, 1)

        self._info_label = QLabel("")
        self._info_label.setObjectName("InfoLabel")
        self._info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._info_label)

        self._diag_label = QLabel("")
        self._diag_label.setObjectName("InfoLabel")
        self._diag_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._diag_label)

        btn_row = QHBoxLayout()

        self._btn_replace = QPushButton("Replace Texture")
        self._btn_replace.setObjectName("PrimaryButton")
        self._btn_replace.setEnabled(False)
        self._btn_replace.clicked.connect(self._replace_texture)
        btn_row.addWidget(self._btn_replace)

        self._btn_export_png = QPushButton("Export PNG")
        self._btn_export_png.setObjectName("SecondaryButton")
        self._btn_export_png.setEnabled(False)
        self._btn_export_png.clicked.connect(lambda: self._export(png=True))
        btn_row.addWidget(self._btn_export_png)

        self._btn_export_dds = QPushButton("Export DDS")
        self._btn_export_dds.setObjectName("SecondaryButton")
        self._btn_export_dds.setEnabled(False)
        self._btn_export_dds.clicked.connect(lambda: self._export(png=False))
        btn_row.addWidget(self._btn_export_dds)

        layout.addLayout(btn_row)
        return panel

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _open_ytd(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open YTD File", "", "Texture Dictionary (*.ytd)"
        )
        if not path:
            return

        self._progress.setVisible(True)
        self._btn_open.setEnabled(False)
        self._tex_list.clear()
        self._info_label.setText("")
        self._diag_label.setText("")
        self._preview.setText("Loading…")

        self._worker = _LoadWorker(Path(path))
        self._worker.finished.connect(self._on_loaded)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_loaded(self, ytd: YTDFile) -> None:
        self._progress.setVisible(False)
        self._btn_open.setEnabled(True)
        self._ytd = ytd
        self._btn_save.setEnabled(True)

        self._tex_list.clear()
        for tex in ytd.textures:
            self._tex_list.addItem(
                QListWidgetItem(f"{tex.name}  ({tex.width}×{tex.height}  {tex.fmt})")
            )

        if ytd.textures:
            self._tex_list.setCurrentRow(0)
        else:
            self._preview.setText("No textures found in this YTD.")

    def _on_load_error(self, message: str) -> None:
        self._progress.setVisible(False)
        self._btn_open.setEnabled(True)
        self._preview.setText("Failed to load.")
        QMessageBox.critical(self, "Error Loading YTD", message)

    def _on_row_changed(self, row: int) -> None:
        if self._ytd is None or row < 0 or row >= len(self._ytd.textures):
            return
        tex = self._ytd.textures[row]
        self._preview.show_dds(tex.dds_data)
        self._info_label.setText(
            f"{tex.name}  ·  {tex.width}×{tex.height}  ·  {tex.fmt}  ·  {tex.mip_levels} mip(s)"
        )
        for btn in (self._btn_replace, self._btn_export_png, self._btn_export_dds):
            btn.setEnabled(True)

    def _replace_texture(self) -> None:
        if self._ytd is None:
            return
        row = self._tex_list.currentRow()
        if row < 0:
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Replacement Texture", "", "DDS or PNG (*.dds *.png)"
        )
        if not path:
            return

        try:
            backend = self._ytd.replace_texture(row, Path(path))
            self._on_row_changed(row)
            if backend == "dds-direct":
                self._diag_label.setText("Replace backend: direct DDS")
            else:
                self._diag_label.setText(f"Replace backend: PNG converted via {backend}")
            QMessageBox.information(self, "Success", "Texture replaced successfully.")
        except Exception as exc:
            self._diag_label.setText(f"Replace failed: {exc}")
            QMessageBox.critical(self, "Replace Failed", str(exc))

    def _export(self, *, png: bool) -> None:
        if self._ytd is None:
            return
        row = self._tex_list.currentRow()
        if row < 0:
            return

        tex = self._ytd.textures[row]
        suffix = ".png" if png else ".dds"
        flt = "PNG Image (*.png)" if png else "DDS Texture (*.dds)"

        out, _ = QFileDialog.getSaveFileName(
            self, "Export Texture", tex.name + suffix, flt
        )
        if not out:
            return

        try:
            self._ytd.export_texture(row, Path(out))
            QMessageBox.information(self, "Exported", f"Saved to:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _save_ytd(self) -> None:
        if self._ytd is None:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "Save YTD", self._ytd.path.name, "Texture Dictionary (*.ytd)"
        )
        if not out:
            return

        try:
            self._ytd.save(Path(out))
            QMessageBox.information(self, "Saved", f"Saved to:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
