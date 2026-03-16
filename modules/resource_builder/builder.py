"""
Resource Builder — build organized FiveM resources with optional clothing naming assistant.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_STREAM_BUCKETS: dict[str, str] = {
    ".ydd": "YDD",
    ".ytd": "YTD",
    ".yft": "YFT",
    ".ydr": "YDR",
    ".ybn": "YBN",
    ".ymt": "YMT",
    ".ymap": "YMAP",
    ".ytyp": "YTYP",
    ".ycd": "YCD",
    ".yld": "YLD",
    ".ynd": "YND",
    ".ynv": "YNV",
    ".ysc": "YSC",
}
_STREAM_EXT: frozenset[str] = frozenset(_STREAM_BUCKETS.keys())
_DATA_EXT: frozenset[str] = frozenset({".meta", ".xml", ".dat"})

@dataclass
class BuildOptions:
    organize_stream: bool = True
    meta_in_root: bool = True
    clothing_rename: bool = False
    generate_creature_metadata: bool = False


def _sanitize_name(value: str) -> str:
    return re.sub(r"\s+", "_", (value or "").strip())


_META_DATAFILE_TYPES: dict[str, str] = {
    "handling.meta": "HANDLING_FILE",
    "vehicles.meta": "VEHICLE_METADATA_FILE",
    "carcols.meta": "CARCOLS_FILE",
    "carvariations.meta": "VEHICLE_VARIATION_FILE",
    "peds.meta": "PED_METADATA_FILE",
    "creaturemetadata.meta": "PED_METADATA_FILE",
    "shop_ped_apparel.meta": "SHOP_PED_APPAREL_META_FILE",
}


def _creature_metadata_template() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<CPedModelInfo__InitDataList>\n"
        "  <residentTxd>uppr_diff_000_a_uni</residentTxd>\n"
        "  <InitDatas>\n"
        "    <Item>\n"
        "      <Name>your_ped_model</Name>\n"
        "      <PropsName></PropsName>\n"
        "      <ClipDictionaryName>move_m@generic</ClipDictionaryName>\n"
        "      <ExpressionSetName>expr_set_ambient_male</ExpressionSetName>\n"
        "      <CreatureMetadataName>creaturemetadata</CreatureMetadataName>\n"
        "      <DecisionMakerName>DEFAULT</DecisionMakerName>\n"
        "      <MovementClipSet>move_m@generic</MovementClipSet>\n"
        "      <DefaultGestureClipSet>ANIM_GROUP_GESTURE_M_GENERIC</DefaultGestureClipSet>\n"
        "      <Pedtype>CIVMALE</Pedtype>\n"
        "      <IsStreamedGfx value=\"true\" />\n"
        "    </Item>\n"
        "  </InitDatas>\n"
        "</CPedModelInfo__InitDataList>\n"
    )


def _manifest_for(resource_type: str, *, meta_paths: list[str]) -> str:
    lines: list[str] = ["fx_version 'cerulean'", "game 'gta5'", ""]

    # Auto-add data_file lines from detected meta files.
    used_meta_lines: set[str] = set()
    for rel_path in meta_paths:
        filename = Path(rel_path).name.lower()
        data_type = _META_DATAFILE_TYPES.get(filename)
        if data_type:
            line = f"data_file '{data_type}' '{rel_path}'"
            if line not in used_meta_lines:
                lines.append(line)
                used_meta_lines.add(line)

    if used_meta_lines:
        lines.append("")

    if resource_type == "vehicle":
        if not used_meta_lines:
            lines.extend([
                "data_file 'HANDLING_FILE' 'handling.meta'",
                "data_file 'VEHICLE_METADATA_FILE' 'vehicles.meta'",
                "data_file 'CARCOLS_FILE' 'carcols.meta'",
                "data_file 'VEHICLE_VARIATION_FILE' 'carvariations.meta'",
                "",
            ])
        return "\n".join(lines).rstrip() + "\n"
    if resource_type == "clothing":
        lines.extend([
            "files {",
            "    'stream/**/*.ydd',",
            "    'stream/**/*.ytd',",
            "    'stream/**/*.ymt',",
            "}",
        ])
        return "\n".join(lines).rstrip() + "\n"
    if resource_type == "mlo":
        lines.extend([
            "data_file 'DLC_ITYP_REQUEST' 'stream/*.ytyp'",
            "",
            "files {",
            "    'stream/**/*.ymap',",
            "    'stream/**/*.ytyp',",
            "    'stream/**/*.ytd',",
            "}",
        ])
        return "\n".join(lines).rstrip() + "\n"
    if resource_type == "script":
        lines.extend([
            "client_script 'client.lua'",
            "server_script 'server.lua'",
        ])
        return "\n".join(lines).rstrip() + "\n"
    lines.extend([
        "files {",
        "    'stream/**',",
        "}",
    ])
    return "\n".join(lines).rstrip() + "\n"


class _DropList(QListWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and not self._contains(path):
                    self.addItem(path)
            event.accept()

    def _contains(self, path: str) -> bool:
        return any(self.item(i).text() == path for i in range(self.count()))


class ResourceBuilderWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        content = QFrame()
        content.setObjectName("ContentFrame")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(14)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Resource Name:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. my_vehicle")
        self._name_input.setFixedWidth(320)
        row1.addWidget(self._name_input)
        row1.addStretch()
        cl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Resource Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["vehicle", "clothing", "mlo", "script", "generic"])
        self._type_combo.setFixedWidth(200)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        row2.addWidget(self._type_combo)
        row2.addStretch()
        cl.addLayout(row2)

        opts_row = QHBoxLayout()
        self._chk_organized = QCheckBox("Organize stream into subfolders (YDD/YTD/...)")
        self._chk_organized.setChecked(True)
        self._chk_meta_root = QCheckBox("Keep .meta/.xml/.dat in resource root")
        self._chk_meta_root.setChecked(True)
        self._chk_creature_meta = QCheckBox("Generate creaturemetadata.meta template")
        self._chk_creature_meta.setChecked(False)
        opts_row.addWidget(self._chk_organized)
        opts_row.addWidget(self._chk_meta_root)
        opts_row.addWidget(self._chk_creature_meta)
        opts_row.addStretch()
        cl.addLayout(opts_row)

        cl.addWidget(QLabel("Files (drag and drop, or click Add):"))
        self._file_list = _DropList()
        cl.addWidget(self._file_list, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Files")
        btn_add.setObjectName("SecondaryButton")
        btn_add.clicked.connect(self._add_files)
        btn_row.addWidget(btn_add)

        btn_clear = QPushButton("Clear All")
        btn_clear.setObjectName("DangerButton")
        btn_clear.clicked.connect(self._file_list.clear)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        cl.addLayout(btn_row)

        btn_build = QPushButton("Build Resource")
        btn_build.setObjectName("PrimaryButton")
        btn_build.setFixedHeight(46)
        btn_build.clicked.connect(self._build)
        cl.addWidget(btn_build)

        layout.addWidget(content, 1)
        self._on_type_changed(self._type_combo.currentText())

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.addWidget(QLabel("Resource Builder", objectName="PanelTitle"))
        layout.addStretch()
        return bar

    def _on_type_changed(self, resource_type: str) -> None:
        self._chk_creature_meta.setVisible(resource_type in {"clothing", "generic"})

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Files",
            "",
            "GTA Assets (*.ytd *.yft *.ydd *.ydr *.ymt *.ymap *.ytyp *.meta *.xml *.lua);;All Files (*)",
        )
        for path in paths:
            if path and not self._file_list._contains(path):
                self._file_list.addItem(path)

    def _build(self) -> None:
        name_raw = self._name_input.text().strip()
        name = _sanitize_name(name_raw)
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a resource name first.")
            return
        if name != name_raw:
            self._name_input.setText(name)
        if self._file_list.count() == 0:
            QMessageBox.warning(self, "No Files", "Add at least one file.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not out_dir:
            return

        options = BuildOptions(
            organize_stream=self._chk_organized.isChecked(),
            meta_in_root=self._chk_meta_root.isChecked(),
            clothing_rename=False,
            generate_creature_metadata=self._chk_creature_meta.isChecked() and self._type_combo.currentText() in {"clothing", "generic"},
        )

        try:
            resource_dir = _build_resource(
                output_root=Path(out_dir),
                name=name,
                resource_type=self._type_combo.currentText(),
                file_paths=[Path(self._file_list.item(i).text()) for i in range(self._file_list.count())],
                options=options,
            )
            QMessageBox.information(self, "Done", f"Resource created:\n{resource_dir}")
        except Exception as exc:
            QMessageBox.critical(self, "Build Error", str(exc))


def _build_resource(
    output_root: Path,
    name: str,
    resource_type: str,
    file_paths: list[Path],
    options: BuildOptions,
) -> Path:
    name = _sanitize_name(name)
    resource_dir = output_root / name
    stream_dir = resource_dir / "stream"
    data_dir = resource_dir / "data"

    resource_dir.mkdir(parents=True, exist_ok=True)
    stream_dir.mkdir(exist_ok=True)

    has_manifest = False
    written_meta_paths: list[str] = []

    expanded_inputs: list[tuple[Path, Path | None]] = []
    for src in file_paths:
        if not src.exists():
            logger.warning("File not found, skipping: %s", src)
            continue
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    expanded_inputs.append((f, f.relative_to(src)))
        else:
            expanded_inputs.append((src, None))

    for src, rel_hint in expanded_inputs:
        ext = src.suffix.lower()
        out_name = src.name

        if src.name.lower() == "fxmanifest.lua":
            shutil.copy2(src, resource_dir / "fxmanifest.lua")
            has_manifest = True
            continue

        if ext in _STREAM_EXT:
            if resource_type == "clothing":
                if rel_hint is not None:
                    parts = rel_hint.parts
                    if parts and parts[0].lower() == "stream":
                        dest = resource_dir / rel_hint
                    else:
                        dest = stream_dir / rel_hint
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    continue
                if src.parent.name.lower() == "creaturemetadata":
                    creature_dir = stream_dir / "creaturemetadata"
                    creature_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, creature_dir / out_name)
                    continue
                shutil.copy2(src, stream_dir / out_name)
                continue
            if options.organize_stream:
                bucket = stream_dir / _STREAM_BUCKETS.get(ext, "MISC")
                bucket.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, bucket / out_name)
            else:
                shutil.copy2(src, stream_dir / out_name)
            continue

        if ext in _DATA_EXT:
            if options.meta_in_root:
                dest = resource_dir / out_name
                shutil.copy2(src, dest)
                written_meta_paths.append(dest.relative_to(resource_dir).as_posix())
            else:
                data_dir.mkdir(exist_ok=True)
                dest = data_dir / out_name
                shutil.copy2(src, dest)
                written_meta_paths.append(dest.relative_to(resource_dir).as_posix())
            continue

        if rel_hint is not None:
            dest = resource_dir / rel_hint
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        else:
            shutil.copy2(src, resource_dir / out_name)

    if options.generate_creature_metadata:
        creature_path = (resource_dir / "creaturemetadata.meta") if options.meta_in_root else (data_dir / "creaturemetadata.meta")
        creature_path.parent.mkdir(parents=True, exist_ok=True)
        if not creature_path.exists():
            creature_path.write_text(_creature_metadata_template(), encoding="utf-8")
        rel = creature_path.relative_to(resource_dir).as_posix()
        if rel not in written_meta_paths:
            written_meta_paths.append(rel)

    if not has_manifest:
        manifest = _manifest_for(resource_type, meta_paths=written_meta_paths)
        (resource_dir / "fxmanifest.lua").write_text(manifest, encoding="utf-8")

    return resource_dir
