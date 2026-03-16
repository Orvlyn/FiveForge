"""
Clothing Builder — drawable-centric clothing pack builder.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.ymt_service import (
    ComponentEntry,
    ComponentInfo,
    DrawableEntry,
    PropDrawable,
    PropEntry,
    PropTextureData,
    TextureData,
    YMTFile,
    save_ymt_resource_from_xml,
)

_COMPONENTS: list[tuple[int, str, str]] = [
    (0, "Head [head]", "head"),
    (1, "Mask [berd]", "berd"),
    (2, "Hair [hair]", "hair"),
    (3, "Body [uppr]", "uppr"),
    (4, "Legs [lowr]", "lowr"),
    (5, "Bag [hand]", "hand"),
    (6, "Shoes [feet]", "feet"),
    (7, "Accessories [teef]", "teef"),
    (8, "Undershirt [accs]", "accs"),
    (9, "Armor [task]", "task"),
    (10, "Decal [decl]", "decl"),
    (11, "Top [jbib]", "jbib"),
]

_PROPS: list[tuple[int, str, str]] = [
    (0, "Head Prop [p_head]", "head"),
    (1, "Eyes Prop [p_eyes]", "eyes"),
    (2, "Ears Prop [p_ears]", "ears"),
    (3, "Mouth Prop [p_mouth]", "mouth"),
    (4, "Left Hand Prop [p_lhand]", "lhand"),
    (5, "Right Hand Prop [p_rhand]", "rhand"),
    (6, "Left Wrist Prop [p_lwrist]", "lwrist"),
    (7, "Right Wrist Prop [p_rwrist]", "rwrist"),
    (8, "Hip Prop [p_hip]", "hip"),
    (9, "Left Foot Prop [p_lfoot]", "lfoot"),
    (10, "Right Foot Prop [p_rfoot]", "rfoot"),
    (11, "Unknown 1 [p_unk1]", "unk1"),
    (12, "Unknown 2 [p_unk2]", "unk2"),
]

_PED_BY_GENDER = {
    "male": ("mp_m_freemode_01", "mp_m"),
    "female": ("mp_f_freemode_01", "mp_f"),
}

_COMPONENT_CATEGORY_LABELS: dict[str, str] = {
    "head": "Identity",
    "berd": "Identity",
    "hair": "Identity",
    "uppr": "Body",
    "lowr": "Body",
    "hand": "Body",
    "feet": "Body",
    "teef": "Face",
    "accs": "Accessories",
    "task": "Accessories",
    "decl": "Overlays",
    "jbib": "Outerwear",
}

_PROP_CATEGORY_LABELS: dict[str, str] = {
    "head": "Headwear",
    "eyes": "Face",
    "ears": "Face",
    "mouth": "Face",
    "lhand": "Hands",
    "rhand": "Hands",
    "lwrist": "Hands",
    "rwrist": "Hands",
    "hip": "Body",
    "lfoot": "Feet",
    "rfoot": "Feet",
    "unk1": "Other",
    "unk2": "Other",
}

_PROP_FLAG_CUT_HAIR = 1
_PROP_FLAG_TAKE_OFF_IN_CAR = 2


def _sanitize_project_name(name: str) -> str:
    value = re.sub(r"\s+", "_", (name or "").strip())
    return value


@dataclass
class DrawableItem:
    gender: str
    cloth_type: str  # component | prop
    drawable_type_id: int
    slot_tag: str
    position: int
    name: str
    model_postfix: str = "u"
    model_source: Path | None = None
    textures: list[Path] = field(default_factory=list)
    prop_flags: int = 0
    prop_cut_hair_amount: float = 0.0
    prop_take_off_in_car: bool = False


@dataclass
class ParsedAsset:
    gender: str | None
    cloth_type: str | None
    slot_tag: str | None
    drawable_key: str | None
    is_texture: bool
    model_postfix: str
    tex_letter: str
    tex_variant: str


def _guess_gender(stem: str) -> str | None:
    lower = stem.lower()
    if "mp_m_freemode_01" in lower or "_mp_m_" in lower:
        return "male"
    if "mp_f_freemode_01" in lower or "_mp_f_" in lower:
        return "female"
    return None


def _strip_prefix(stem: str) -> str:
    if "^" in stem:
        return stem.split("^", 1)[1]
    return stem


def _parse_asset_name(path: Path) -> ParsedAsset:
    stem = _strip_prefix(path.stem.lower())
    ext = path.suffix.lower()

    # component model: uppr_000_u
    m = re.fullmatch(r"([a-z0-9]+)_(\d{3})_([a-z0-9]+)(?:_1)?", stem)
    if m and ext == ".ydd":
        slot = m.group(1)
        if any(tag == slot for _, _, tag in _COMPONENTS):
            return ParsedAsset(_guess_gender(path.stem), "component", slot, m.group(2), False, m.group(3), "a", "uni")

    # prop model: p_eyes_000
    m = re.fullmatch(r"p_([a-z0-9]+)_(\d{3})", stem)
    if m and ext == ".ydd":
        return ParsedAsset(_guess_gender(path.stem), "prop", m.group(1), m.group(2), False, "", "a", "")

    # component texture: uppr_diff_000_a_uni
    m = re.fullmatch(r"([a-z0-9]+)_diff_(\d{3})_([a-z])(?:_([a-z0-9]+))?", stem)
    if m and ext == ".ytd":
        slot = m.group(1)
        if any(tag == slot for _, _, tag in _COMPONENTS):
            return ParsedAsset(_guess_gender(path.stem), "component", slot, m.group(2), True, "u", m.group(3), m.group(4) or "uni")

    # prop texture: p_eyes_diff_000_a
    m = re.fullmatch(r"p_([a-z0-9]+)_diff_(\d{3})_([a-z])", stem)
    if m and ext == ".ytd":
        return ParsedAsset(_guess_gender(path.stem), "prop", m.group(1), m.group(2), True, "", m.group(3), "")

    return ParsedAsset(_guess_gender(path.stem), None, None, None, ext == ".ytd", "u", "a", "uni")


def _normalize_model_postfix(value: str) -> str:
    normalized = (value or "u").strip().lower().lstrip("_")
    return normalized or "u"


def _mask_from_postfix(postfix: str) -> int:
    suffix = _normalize_model_postfix(postfix)
    if suffix.startswith("r"):
        return 17
    if suffix.startswith("h"):
        return 65
    return 1


def _blank_ped_variation_ymt(dlc_name: str) -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<CPedVariationInfo>\n"
        " <bHasTexVariations value=\"false\" />\n"
        " <bHasDrawblVariations value=\"false\" />\n"
        " <bHasLowLODs value=\"false\" />\n"
        " <bIsSuperLOD value=\"false\" />\n"
        " <availComp>255 255 255 255 255 255 255 255 255 255 255 255</availComp>\n"
        " <aComponentData3 itemType=\"CPVComponentData\">\n"
        " </aComponentData3>\n"
        " <aSelectionSets itemType=\"CPedSelectionSet\" />\n"
        " <compInfos itemType=\"CComponentInfo\">\n"
        " </compInfos>\n"
        " <propInfo>\n"
        "  <numAvailProps value=\"0\" />\n"
        "  <aPropMetaData itemType=\"CPedPropMetaData\">\n"
        "  </aPropMetaData>\n"
        "  <aAnchors itemType=\"CAnchorProps\" />\n"
        " </propInfo>\n"
        f" <dlcName>{dlc_name}</dlcName>\n"
        "</CPedVariationInfo>\n"
    )


def _creaturemetadata_ymt_content(collection_name: str) -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<CPedModelInfo__InitDataList>\n"
        "  <residentTxd>uppr_diff_000_a_uni</residentTxd>\n"
        "  <InitDatas>\n"
        "    <Item>\n"
        f"      <Name>MP_CreatureMetadata_{collection_name}</Name>\n"
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


def _shop_ped_meta_content(gender: str, collection_name: str) -> str:
    ped_name, prefix = _PED_BY_GENDER[gender]
    dlc_name = f"{prefix}_{collection_name}"
    full_dlc_name = f"{ped_name}_{dlc_name}"
    character = "SCR_CHAR_MULTIPLAYER_F" if gender == "female" else "SCR_CHAR_MULTIPLAYER"
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ShopPedApparel>\n"
        f"  <pedName>{ped_name}</pedName>\n"
        f"  <dlcName>{dlc_name}</dlcName>\n"
        f"  <fullDlcName>{full_dlc_name}</fullDlcName>\n"
        f"  <eCharacter>{character}</eCharacter>\n"
        f"  <creatureMetaData>MP_CreatureMetadata_{collection_name}</creatureMetaData>\n"
        "  <pedOutfits>\n"
        "  </pedOutfits>\n"
        "  <pedComponents>\n"
        "  </pedComponents>\n"
        "  <pedProps>\n"
        "  </pedProps>\n"
        "</ShopPedApparel>\n"
    )


def _manifest_content(meta_files: list[str], creature_file: str) -> str:
    files = [
        "stream/**/*.ydd",
        "stream/**/*.ytd",
        "stream/**/*.ymt",
        *meta_files,
        creature_file,
    ]
    files_text = "\n".join(f"    '{f}'," for f in files)
    meta_rows = "\n".join(f"data_file 'SHOP_PED_APPAREL_META_FILE' '{m}'" for m in meta_files)
    return (
        "fx_version 'cerulean'\n"
        "game 'gta5'\n\n"
        "files {\n"
        f"{files_text}\n"
        "}\n\n"
        f"{meta_rows}\n"
        f"data_file 'PED_METADATA_FILE' '{creature_file}'\n"
    )


class ClothingBuilderWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._items: list[DrawableItem] = []
        self._updating_editor = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._right_panel())
        splitter.setSizes([390, 910])
        root.addWidget(splitter, 1)

        bottom = QFrame()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(12, 8, 12, 8)

        bl.addWidget(QLabel("Project name:"))
        self._project_name = QLineEdit()
        self._project_name.setPlaceholderText("e.g. Orvlyn_Pack")
        self._project_name.setFixedWidth(280)
        bl.addWidget(self._project_name)

        self._status = QLabel("No drawables loaded")
        self._status.setObjectName("InfoLabel")
        bl.addWidget(self._status, 1)

        self._btn_build = QPushButton("Build project")
        self._btn_build.setObjectName("PrimaryButton")
        self._btn_build.setFixedHeight(38)
        self._btn_build.clicked.connect(self._build_project)
        bl.addWidget(self._btn_build)

        root.addWidget(bottom)

    def _toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(52)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(16, 0, 16, 0)
        hl.addWidget(QLabel("Clothing Builder", objectName="PanelTitle"))
        hl.addWidget(QLabel("Drawable editor workflow", objectName="InfoLabel"))
        hl.addStretch()
        return bar

    def _left_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ListPanel")
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        title = QLabel("Drawables")
        title.setObjectName("SectionGroupLabel")
        v.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Enter search term")
        self._search.textChanged.connect(self._refresh_list)
        v.addWidget(self._search)

        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selected)
        v.addWidget(self._list, 1)

        row = QGridLayout()
        self._btn_add_auto = QPushButton("Add")
        self._btn_add_auto.clicked.connect(lambda: self._import_files(None))
        row.addWidget(self._btn_add_auto, 0, 0)

        self._btn_add_male = QPushButton("Add Male")
        self._btn_add_male.clicked.connect(lambda: self._import_files("male"))
        row.addWidget(self._btn_add_male, 0, 1)

        self._btn_add_female = QPushButton("Add Female")
        self._btn_add_female.clicked.connect(lambda: self._import_files("female"))
        row.addWidget(self._btn_add_female, 0, 2)

        self._btn_remove = QPushButton("Remove")
        self._btn_remove.setObjectName("DangerButton")
        self._btn_remove.clicked.connect(self._remove_selected)
        row.addWidget(self._btn_remove, 1, 0)

        self._btn_add_folder = QPushButton("Add Folder")
        self._btn_add_folder.clicked.connect(lambda: self._import_folder(None))
        row.addWidget(self._btn_add_folder, 1, 1)

        self._btn_clear = QPushButton("Clear All")
        self._btn_clear.clicked.connect(self._clear_all)
        row.addWidget(self._btn_clear, 1, 2)
        v.addLayout(row)

        return frame

    def _right_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ContentFrame")
        v = QVBoxLayout(frame)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(10)

        v.addWidget(QLabel("Edit selected drawable", objectName="PanelTitle"))

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._spin_position = QSpinBox()
        self._spin_position.setRange(0, 999)
        self._spin_position.setToolTip("In-game drawable order. Lower numbers are shown first.")
        self._spin_position.valueChanged.connect(self._apply_editor_to_current)
        form.addRow("Position (in-game order)", self._spin_position)

        self._cmb_cloth_type = QComboBox()
        self._cmb_cloth_type.addItems(["Component", "Prop"])
        self._cmb_cloth_type.currentIndexChanged.connect(self._on_cloth_type_changed)
        form.addRow("Cloth type", self._cmb_cloth_type)

        self._cmb_drawable_type = QComboBox()
        self._cmb_drawable_type.currentIndexChanged.connect(self._apply_editor_to_current)
        form.addRow("Drawable type", self._cmb_drawable_type)

        self._cmb_gender = QComboBox()
        self._cmb_gender.addItems(["male", "female"])
        self._cmb_gender.currentIndexChanged.connect(self._apply_editor_to_current)
        form.addRow("Gender", self._cmb_gender)

        self._edit_name = QLineEdit()
        self._edit_name.textChanged.connect(self._apply_editor_to_current)
        form.addRow("Name", self._edit_name)

        self._edit_model = QLineEdit()
        self._edit_model.setReadOnly(True)
        form.addRow("Model source", self._edit_model)

        self._edit_postfix = QLineEdit()
        self._edit_postfix.setMaxLength(8)
        self._edit_postfix.textChanged.connect(self._apply_editor_to_current)
        form.addRow("Model postfix", self._edit_postfix)

        self._spin_prop_flags = QSpinBox()
        self._spin_prop_flags.setRange(0, 255)
        self._spin_prop_flags.valueChanged.connect(self._on_prop_flags_changed)
        form.addRow("Prop flags", self._spin_prop_flags)

        self._spin_prop_cut_hair_amount = QDoubleSpinBox()
        self._spin_prop_cut_hair_amount.setRange(0.0, 1.0)
        self._spin_prop_cut_hair_amount.setSingleStep(0.1)
        self._spin_prop_cut_hair_amount.setDecimals(2)
        self._spin_prop_cut_hair_amount.valueChanged.connect(self._on_prop_cut_hair_amount_changed)
        form.addRow("Cut hair amount (0.0-1.0)", self._spin_prop_cut_hair_amount)

        self._chk_prop_cut_hair = QPushButton("Cut hair flag")
        self._chk_prop_cut_hair.setCheckable(True)
        self._chk_prop_cut_hair.toggled.connect(self._on_prop_cut_hair_toggled)

        self._chk_prop_take_off_in_car = QPushButton("Take off in car")
        self._chk_prop_take_off_in_car.setCheckable(True)
        self._chk_prop_take_off_in_car.toggled.connect(self._on_prop_take_off_in_car_toggled)

        prop_options = QHBoxLayout()
        prop_options.addWidget(self._chk_prop_cut_hair)
        prop_options.addWidget(self._chk_prop_take_off_in_car)
        prop_options.addStretch(1)
        form.addRow("Prop options", prop_options)

        v.addLayout(form)

        tx_hdr = QHBoxLayout()
        tx_hdr.addWidget(QLabel("Textures"))
        tx_hdr.addStretch()
        btn_add_tx = QPushButton("Add textures")
        btn_add_tx.clicked.connect(self._add_textures_to_selected)
        tx_hdr.addWidget(btn_add_tx)
        btn_del_tx = QPushButton("Remove selected")
        btn_del_tx.clicked.connect(self._remove_selected_texture)
        tx_hdr.addWidget(btn_del_tx)
        v.addLayout(tx_hdr)

        self._tx_list = QListWidget()
        v.addWidget(self._tx_list, 1)

        self._on_cloth_type_changed(0)
        self._set_editor_enabled(False)
        return frame

    def _set_editor_enabled(self, enabled: bool) -> None:
        for w in [
            self._spin_position,
            self._cmb_cloth_type,
            self._cmb_drawable_type,
            self._cmb_gender,
            self._edit_name,
            self._edit_postfix,
            self._spin_prop_flags,
            self._spin_prop_cut_hair_amount,
            self._chk_prop_cut_hair,
            self._chk_prop_take_off_in_car,
            self._tx_list,
        ]:
            w.setEnabled(enabled)

    def _on_cloth_type_changed(self, index: int) -> None:
        self._cmb_drawable_type.blockSignals(True)
        self._cmb_drawable_type.clear()
        if index == 0:
            for value, label, tag in _COMPONENTS:
                category = _COMPONENT_CATEGORY_LABELS.get(tag, "Other")
                self._cmb_drawable_type.addItem(f"{category} • {value}  {label}", (value, tag))
        else:
            for value, label, tag in _PROPS:
                category = _PROP_CATEGORY_LABELS.get(tag, "Other")
                self._cmb_drawable_type.addItem(f"{category} • {value}  {label}", (value, tag))
        self._cmb_drawable_type.blockSignals(False)
        self._spin_prop_flags.setVisible(index == 1)
        self._spin_prop_cut_hair_amount.setVisible(index == 1)
        self._chk_prop_cut_hair.setVisible(index == 1)
        self._chk_prop_take_off_in_car.setVisible(index == 1)
        if self._updating_editor:
            return
        self._apply_editor_to_current()

    def _on_prop_flags_changed(self, value: int) -> None:
        if self._updating_editor:
            return
        self._updating_editor = True
        try:
            has_cut_hair = bool(value & _PROP_FLAG_CUT_HAIR)
            self._chk_prop_cut_hair.setChecked(has_cut_hair)
            self._chk_prop_take_off_in_car.setChecked(bool(value & _PROP_FLAG_TAKE_OFF_IN_CAR))
            if not has_cut_hair:
                self._spin_prop_cut_hair_amount.setValue(0.0)
            elif self._spin_prop_cut_hair_amount.value() == 0.0:
                self._spin_prop_cut_hair_amount.setValue(1.0)
        finally:
            self._updating_editor = False
        self._apply_editor_to_current()

    def _on_prop_cut_hair_amount_changed(self, value: float) -> None:
        if self._updating_editor:
            return
        self._updating_editor = True
        try:
            self._chk_prop_cut_hair.setChecked(value > 0.0)
        finally:
            self._updating_editor = False
        self._apply_editor_to_current()

    def _on_prop_cut_hair_toggled(self, checked: bool) -> None:
        if self._updating_editor:
            return
        flags = self._spin_prop_flags.value()
        if checked:
            flags |= _PROP_FLAG_CUT_HAIR
        else:
            flags &= ~_PROP_FLAG_CUT_HAIR
        self._updating_editor = True
        try:
            self._spin_prop_flags.setValue(flags)
            if checked and self._spin_prop_cut_hair_amount.value() == 0.0:
                self._spin_prop_cut_hair_amount.setValue(1.0)
            if not checked:
                self._spin_prop_cut_hair_amount.setValue(0.0)
        finally:
            self._updating_editor = False
        self._apply_editor_to_current()

    def _on_prop_take_off_in_car_toggled(self, checked: bool) -> None:
        if self._updating_editor:
            return
        flags = self._spin_prop_flags.value()
        if checked:
            flags |= _PROP_FLAG_TAKE_OFF_IN_CAR
        else:
            flags &= ~_PROP_FLAG_TAKE_OFF_IN_CAR
        self._updating_editor = True
        try:
            self._spin_prop_flags.setValue(flags)
        finally:
            self._updating_editor = False
        self._apply_editor_to_current()

    def _iter_candidate_files(self, paths: list[Path]) -> list[Path]:
        out: list[Path] = []
        for p in paths:
            if not p.exists():
                continue
            if p.is_dir():
                out.extend([f for f in p.rglob("*") if f.is_file()])
            else:
                out.append(p)
        return out

    def _import_files(self, forced_gender: str | None) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Clothing Files",
            "",
            "Clothing Files (*.ydd *.ytd);;All Files (*)",
        )
        if not paths:
            return
        self._ingest_paths([Path(p) for p in paths], forced_gender)

    def _import_folder(self, forced_gender: str | None) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if not folder:
            return
        self._ingest_paths([Path(folder)], forced_gender)

    def _ingest_paths(self, paths: list[Path], forced_gender: str | None) -> None:
        candidates = self._iter_candidate_files(paths)
        if not candidates:
            return

        grouped: dict[tuple[str, str, str, str], DrawableItem] = {}

        for src in candidates:
            if src.suffix.lower() not in {".ydd", ".ytd"}:
                continue

            parsed = _parse_asset_name(src)
            if parsed.cloth_type is None or parsed.slot_tag is None or parsed.drawable_key is None:
                continue

            gender = forced_gender or parsed.gender or "male"
            key = (gender, parsed.cloth_type, parsed.slot_tag, parsed.drawable_key)

            if key not in grouped:
                if parsed.cloth_type == "component":
                    dtype = next((v for v, _l, t in _COMPONENTS if t == parsed.slot_tag), 3)
                else:
                    dtype = next((v for v, _l, t in _PROPS if t == parsed.slot_tag), 0)

                grouped[key] = DrawableItem(
                    gender=gender,
                    cloth_type=parsed.cloth_type,
                    drawable_type_id=dtype,
                    slot_tag=parsed.slot_tag,
                    position=int(parsed.drawable_key),
                    name=parsed.slot_tag,
                    model_postfix=_normalize_model_postfix(parsed.model_postfix or "u"),
                )

            item = grouped[key]
            if parsed.is_texture:
                item.textures.append(src)
            else:
                item.model_source = src
                if parsed.model_postfix:
                    item.model_postfix = _normalize_model_postfix(parsed.model_postfix)

        if not grouped:
            QMessageBox.warning(self, "No valid files", "No supported clothing naming patterns were found.")
            return

        self._items.extend(grouped.values())
        self._items.sort(key=lambda x: (x.gender, x.cloth_type, x.drawable_type_id, x.position, x.name))
        self._refresh_list()

    def _clear_all(self) -> None:
        self._items.clear()
        self._refresh_list()

    def _remove_selected(self) -> None:
        idx = self._list.currentRow()
        if idx < 0 or idx >= len(self._filtered_indices()):
            return
        real_idx = self._filtered_indices()[idx]
        self._items.pop(real_idx)
        self._refresh_list()

    def _add_textures_to_selected(self) -> None:
        item = self._current_item()
        if item is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add textures", "", "Textures (*.ytd)")
        for path in paths:
            p = Path(path)
            if p not in item.textures:
                item.textures.append(p)
        self._load_editor_from_item(item)
        self._refresh_list()

    def _remove_selected_texture(self) -> None:
        item = self._current_item()
        if item is None:
            return
        tx_idx = self._tx_list.currentRow()
        if tx_idx < 0 or tx_idx >= len(item.textures):
            return
        item.textures.pop(tx_idx)
        self._load_editor_from_item(item)
        self._refresh_list()

    def _filtered_indices(self) -> list[int]:
        q = self._search.text().strip().lower()
        if not q:
            return list(range(len(self._items)))
        out: list[int] = []
        for i, it in enumerate(self._items):
            text = f"{it.gender} {it.cloth_type} {it.slot_tag} {it.position:03d} {it.name}".lower()
            if q in text:
                out.append(i)
        return out

    def _refresh_list(self) -> None:
        current = self._current_item()
        current_key = None
        if current is not None:
            current_key = (current.gender, current.cloth_type, current.slot_tag, current.position, current.name)

        self._list.blockSignals(True)
        self._list.clear()
        indices = self._filtered_indices()
        for i in indices:
            it = self._items[i]
            label = f"{it.position:03d} {it.name} [{it.slot_tag}] ({it.gender})  tx:{len(it.textures)}"
            item = QListWidgetItem(label)
            self._list.addItem(item)
        self._list.blockSignals(False)

        self._status.setText(f"{len(self._items)} drawables loaded")

        if not indices:
            self._set_editor_enabled(False)
            self._tx_list.clear()
            self._edit_model.clear()
            return

        target_row = 0
        if current_key is not None:
            for row, i in enumerate(indices):
                it = self._items[i]
                key = (it.gender, it.cloth_type, it.slot_tag, it.position, it.name)
                if key == current_key:
                    target_row = row
                    break
        self._list.setCurrentRow(target_row)

    def _current_item(self) -> DrawableItem | None:
        indices = self._filtered_indices()
        row = self._list.currentRow()
        if row < 0 or row >= len(indices):
            return None
        return self._items[indices[row]]

    def _on_selected(self, row: int) -> None:
        item = self._current_item()
        if item is None:
            self._set_editor_enabled(False)
            return
        self._set_editor_enabled(True)
        self._load_editor_from_item(item)

    def _load_editor_from_item(self, item: DrawableItem) -> None:
        self._updating_editor = True
        self._spin_position.blockSignals(True)
        self._cmb_cloth_type.blockSignals(True)
        self._cmb_drawable_type.blockSignals(True)
        self._cmb_gender.blockSignals(True)
        self._edit_name.blockSignals(True)
        self._edit_postfix.blockSignals(True)
        try:
            self._spin_position.setValue(item.position)
            self._cmb_cloth_type.setCurrentIndex(0 if item.cloth_type == "component" else 1)
            self._on_cloth_type_changed(self._cmb_cloth_type.currentIndex())

            for i in range(self._cmb_drawable_type.count()):
                value = self._cmb_drawable_type.itemData(i)
                if value and value[0] == item.drawable_type_id:
                    self._cmb_drawable_type.setCurrentIndex(i)
                    break

            self._cmb_gender.setCurrentText(item.gender)
            self._edit_name.setText(item.name)
            self._edit_model.setText(str(item.model_source) if item.model_source else "")
            self._edit_postfix.setText(item.model_postfix)
            self._spin_prop_flags.setValue(item.prop_flags)
            self._spin_prop_cut_hair_amount.setValue(max(0.0, min(1.0, item.prop_cut_hair_amount)))
            self._chk_prop_cut_hair.setChecked(bool(item.prop_flags & _PROP_FLAG_CUT_HAIR))
            self._chk_prop_take_off_in_car.setChecked(bool(item.prop_flags & _PROP_FLAG_TAKE_OFF_IN_CAR))

            self._tx_list.clear()
            for tx in item.textures:
                self._tx_list.addItem(tx.name)
        finally:
            self._spin_position.blockSignals(False)
            self._cmb_cloth_type.blockSignals(False)
            self._cmb_drawable_type.blockSignals(False)
            self._cmb_gender.blockSignals(False)
            self._edit_name.blockSignals(False)
            self._edit_postfix.blockSignals(False)
            self._updating_editor = False

    def _apply_editor_to_current(self) -> None:
        if self._updating_editor:
            return
        item = self._current_item()
        if item is None:
            return

        item.position = self._spin_position.value()
        item.cloth_type = "component" if self._cmb_cloth_type.currentIndex() == 0 else "prop"
        item.gender = self._cmb_gender.currentText()
        item.name = self._edit_name.text().strip() or item.slot_tag
        item.model_postfix = _normalize_model_postfix(self._edit_postfix.text())
        item.prop_cut_hair_amount = max(0.0, min(1.0, float(self._spin_prop_cut_hair_amount.value())))
        item.prop_take_off_in_car = self._chk_prop_take_off_in_car.isChecked()

        prop_flags = self._spin_prop_flags.value()
        if item.prop_cut_hair_amount > 0.0 or self._chk_prop_cut_hair.isChecked():
            prop_flags |= _PROP_FLAG_CUT_HAIR
        else:
            prop_flags &= ~_PROP_FLAG_CUT_HAIR
        if item.prop_take_off_in_car:
            prop_flags |= _PROP_FLAG_TAKE_OFF_IN_CAR
        else:
            prop_flags &= ~_PROP_FLAG_TAKE_OFF_IN_CAR
        item.prop_flags = prop_flags

        self._updating_editor = True
        try:
            self._spin_prop_flags.setValue(prop_flags)
            self._chk_prop_cut_hair.setChecked(bool(prop_flags & _PROP_FLAG_CUT_HAIR))
        finally:
            self._updating_editor = False

        value = self._cmb_drawable_type.currentData()
        if value:
            item.drawable_type_id = int(value[0])
            item.slot_tag = str(value[1])

        self._refresh_list()

    def _build_gender_ymt(self, stream: Path, project: str, gender: str) -> None:
        ped_name, ped_prefix = _PED_BY_GENDER[gender]
        dlc_name = f"{ped_name}_{ped_prefix}_{project}"
        ymt_name = f"{ped_name}_{ped_prefix}_{project}.ymt"

        gender_items = [it for it in self._items if it.gender == gender]
        component_items = [it for it in gender_items if it.cloth_type == "component"]
        prop_items = [it for it in gender_items if it.cloth_type == "prop"]

        comp_by_id: dict[int, list[DrawableItem]] = {}
        for it in component_items:
            comp_by_id.setdefault(it.drawable_type_id, []).append(it)

        active_comp_ids = sorted(comp_by_id.keys())
        avail_comp = [255] * 12
        components: list[ComponentEntry] = []
        for slot_idx, comp_id in enumerate(active_comp_ids):
            if 0 <= comp_id < 12:
                avail_comp[comp_id] = slot_idx
            source_items = sorted(comp_by_id[comp_id], key=lambda x: x.position)
            drawables: list[DrawableEntry] = []
            for it in source_items:
                textures = [TextureData(tex_id=i, distribution=255) for i, _ in enumerate(it.textures)]
                drawables.append(
                    DrawableEntry(
                        drawable_id=it.position,
                        texture_count=len(textures),
                        prop_mask=_mask_from_postfix(it.model_postfix),
                        num_alternatives=0,
                        has_cloth=False,
                        textures=textures,
                        comp_info=ComponentInfo(comp_idx=comp_id, drawbl_idx=it.position),
                        flags=_mask_from_postfix(it.model_postfix),
                    )
                )
            comp_name = source_items[0].slot_tag if source_items else f"comp_{comp_id}"
            components.append(ComponentEntry(name=comp_name, component_id=comp_id, drawables=drawables))

        prop_by_anchor: dict[int, list[DrawableItem]] = {}
        for it in prop_items:
            prop_by_anchor.setdefault(it.drawable_type_id, []).append(it)

        props: list[PropEntry] = []
        for anchor_id in sorted(prop_by_anchor.keys()):
            items: list[PropDrawable] = []
            for it in sorted(prop_by_anchor[anchor_id], key=lambda x: x.position):
                tex = [
                    PropTextureData(
                        tex_id=i,
                        inclusions="0",
                        exclusions="0",
                        inclusion_id=0,
                        exclusion_id=0,
                        distribution=255,
                    )
                    for i, _ in enumerate(it.textures)
                ]
                items.append(
                    PropDrawable(
                        prop_index=it.position,
                        anchor_id=anchor_id,
                        prop_id=it.position,
                        audio_id="none",
                        expression_mods=[f"{it.prop_cut_hair_amount:.2f}", "0", "0", "0", "0"],
                        render_flags="take_off_in_car" if it.prop_take_off_in_car else "",
                        prop_flags=it.prop_flags,
                        flags=0,
                        hash_AC887A91=int(round(it.prop_cut_hair_amount * 100)),
                        textures=tex,
                    )
                )
            props.append(PropEntry(name=f"prop_{anchor_id}", prop_id=anchor_id, items=items))

        ymt = YMTFile(path=stream / ymt_name)
        ymt.dlc_name = dlc_name
        ymt.has_tex_variations = bool(component_items or prop_items)
        ymt.has_drawbl_variations = bool(component_items or prop_items)
        ymt.has_low_lods = False
        ymt.is_super_lod = False
        ymt.avail_comp = avail_comp
        ymt.components = components
        ymt.props = props
        ymt.save(stream / ymt_name)

    def _build_project(self) -> None:
        project_raw = self._project_name.text().strip()
        if not project_raw:
            QMessageBox.warning(self, "Missing project name", "Enter a project name.")
            return
        project = _sanitize_project_name(project_raw)
        if not project:
            QMessageBox.warning(self, "Missing project name", "Enter a project name.")
            return
        if project != project_raw:
            self._project_name.setText(project)
        if not self._items:
            QMessageBox.warning(self, "No drawables", "Add drawables before building.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not out_dir:
            return

        root = Path(out_dir) / project
        stream = root / "stream"
        stream.mkdir(parents=True, exist_ok=True)

        seen_genders = sorted({i.gender for i in self._items})
        for gender in seen_genders:
            ped_name, ped_prefix = _PED_BY_GENDER[gender]
            collection_tag = f"{ped_prefix}_{project}"
            (stream / f"{ped_name}_{collection_tag}").mkdir(parents=True, exist_ok=True)
            (stream / f"{ped_name}_p_{collection_tag}").mkdir(parents=True, exist_ok=True)

        for it in self._items:
            ped_name, ped_prefix = _PED_BY_GENDER[it.gender]
            collection_tag = f"{ped_prefix}_{project}"

            if it.cloth_type == "component":
                folder = stream / f"{ped_name}_{collection_tag}"
                base = f"{ped_name}_{collection_tag}"
                model_name = f"{base}^{it.slot_tag}_{it.position:03d}_{it.model_postfix}.ydd"
                if it.model_source and it.model_source.exists():
                    shutil.copy2(it.model_source, folder / model_name)
                for tx in it.textures:
                    m = re.search(r"_([a-z])(?:_([a-z0-9]+))?\.ytd$", tx.name.lower())
                    letter = m.group(1) if m else "a"
                    variant = m.group(2) if (m and m.group(2)) else "uni"
                    tex_name = f"{base}^{it.slot_tag}_diff_{it.position:03d}_{letter}_{variant}.ytd"
                    if tx.exists():
                        shutil.copy2(tx, folder / tex_name)
            else:
                folder = stream / f"{ped_name}_p_{collection_tag}"
                base = f"{ped_name}_p_{collection_tag}"
                model_name = f"{base}^p_{it.slot_tag}_{it.position:03d}.ydd"
                if it.model_source and it.model_source.exists():
                    shutil.copy2(it.model_source, folder / model_name)
                for tx in it.textures:
                    m = re.search(r"_([a-z])\.ytd$", tx.name.lower())
                    letter = m.group(1) if m else "a"
                    tex_name = f"{base}^p_{it.slot_tag}_diff_{it.position:03d}_{letter}.ytd"
                    if tx.exists():
                        shutil.copy2(tx, folder / tex_name)

        # Gender YMTs in stream root.
        for gender in seen_genders:
            self._build_gender_ymt(stream, project, gender)

        creature_dir = stream / "creaturemetadata"
        creature_dir.mkdir(parents=True, exist_ok=True)
        creature_file_name = f"mp_creaturemetadata_{project}.ymt"
        save_ymt_resource_from_xml(
            _creaturemetadata_ymt_content(project),
            creature_dir / creature_file_name,
            version=2,
        )
        creature_rel = f"stream/creaturemetadata/{creature_file_name}"

        meta_files: list[str] = []
        for gender in seen_genders:
            ped_name, ped_prefix = _PED_BY_GENDER[gender]
            meta_name = f"{ped_name}_{ped_prefix}_{project}_shop.meta"
            (root / meta_name).write_text(_shop_ped_meta_content(gender, project), encoding="utf-8")
            meta_files.append(meta_name)

        (root / "fxmanifest.lua").write_text(_manifest_content(meta_files, creature_rel), encoding="utf-8")

        QMessageBox.information(self, "Build complete", f"Project built at:\n{root}")
