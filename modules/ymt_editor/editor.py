"""
YMT Editor — GTA V clothing metadata (.ymt) editor, YMTEditor-style layout.

Left panel   : accordion sections per component / prop anchor, each collapsible.
               "Components ▾" button opens a checkable dropdown menu to add/remove
               component slots.  "Props ▾" does the same for prop anchors.
               Each section header has [+] / [−] to add or remove the last drawable.
               Clicking a drawable row selects it and populates the right panel.
Right panel  : properties for the selected drawable.
               Drawable Properties / Textures / Component Info (collapsible groups).
               Prop fields shown instead when a prop drawable is selected.
Header bar   : dlcName field + flag checkboxes.
Footer       : status log.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QFileDialog, QMessageBox,
    QFrame, QScrollArea, QMenu,
    QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QLineEdit,
    QRadioButton, QDialog, QDialogButtonBox,
    QButtonGroup,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor, QAction

from core.ymt_service import (
    YMTFile, ComponentEntry, PropEntry,
    DrawableEntry, PropDrawable,
    TextureData, PropTextureData, ComponentInfo,
    COMPONENT_NAMES, PROP_NAMES,
)

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

_TEX_LETTERS = "abcdefghijklmnopqrstuvwxyz"

_COMPONENT_FRIENDLY = {
    0: "Head",
    1: "Beard",
    2: "Hair",
    3: "Upper",
    4: "Lower",
    5: "Hands",
    6: "Feet",
    7: "Teeth",
    8: "Accessories",
    9: "Task",
    10: "Decals",
    11: "Jacket / Bib",
}

_PROP_FRIENDLY = {
    0: "Head",
    1: "Eyes",
    2: "Ears",
    3: "Mouth",
    4: "Left hand",
    5: "Right hand",
    6: "Left wrist",
    7: "Right wrist",
    8: "Left foot",
    9: "Right foot",
    10: "Physics left hand",
    11: "Physics right hand",
    12: "Hat",
}

_MASK_NAMES = {
    1: "_u",
    17: "_r",
}

_MASK_PRESETS = [
    ("Model suffix _u (default model)", 1),
    ("Model suffix _r (alt model)", 17),
]

_COMMON_MASK_HINT = "Model suffixes are usually _u or _r (this field). Texture suffixes such as _uni, _whi, _bla are texture-variant naming, not propMask values."

_TEXTURE_VARIANT_PRESETS: list[tuple[str, Optional[int]]] = [
    ("Custom", None),
    ("_uni (base)", 0),
    ("_whi", 1),
    ("_bla", 2),
    ("_chi", 3),
    ("_lat", 4),
]

_TEXTURE_VARIANT_BY_TEXID: dict[int, str] = {
    0: "_uni (base)",
    1: "_whi",
    2: "_bla",
    3: "_chi",
    4: "_lat",
}


def _infer_ped_from_name(name: str) -> str:
    lower = (name or "").lower()
    if "mp_m_freemode_01" in lower or re.search(r"(^|_)mp_m(_|$)", lower):
        return "Male (mp_m_freemode_01)"
    if "mp_f_freemode_01" in lower or re.search(r"(^|_)mp_f(_|$)", lower):
        return "Female (mp_f_freemode_01)"
    return "Custom / Unknown ped"


def _is_hash_name(value: str) -> bool:
    return re.fullmatch(r"hash_[0-9a-fA-F]{6,}", (value or "").strip()) is not None


def _normalize_dlc_name(raw_dlc: str, fallback_stem: str) -> str:
    dlc = (raw_dlc or "").strip()
    if not dlc or _is_hash_name(dlc):
        return fallback_stem
    return dlc

def _tex_letter(idx: int) -> str:
    if idx < 26:
        return _TEX_LETTERS[idx]
    return _TEX_LETTERS[idx // 26 - 1] + _TEX_LETTERS[idx % 26]


def _component_display(component_id: int, raw_name: str | None = None) -> str:
    code = COMPONENT_NAMES.get(component_id, raw_name or f"comp_{component_id}").upper()
    friendly = _COMPONENT_FRIENDLY.get(component_id, code.title())
    return f"{code} · {friendly} · slot {component_id}"


def _prop_display(prop_id: int, raw_name: str | None = None) -> str:
    code = PROP_NAMES.get(prop_id, raw_name or f"prop_{prop_id}").upper()
    friendly = _PROP_FRIENDLY.get(prop_id, code.replace("P_", "").replace("_", " ").title())
    return f"{code} · {friendly} · anchor {prop_id}"


def _mask_display(mask: int) -> str:
    if mask == 1:
        return "model _u  (mask 1)"
    suffix = _MASK_NAMES.get(mask)
    if suffix:
        return f"model {suffix}  (mask {mask})"
    return f"custom / unknown  (mask {mask})"


def _mask_hint(mask: int) -> str:
    if mask == 1:
        return "Mask 1 means the model variant is _u (default). Texture names may still use _a_uni / _a_whi etc; those texture suffixes are separate from this field."
    suffix = _MASK_NAMES.get(mask)
    if suffix:
        return f"Known suffix for this mask: {suffix}. {_COMMON_MASK_HINT}"
    return f"Mask {mask} is not in the built-in known list. {_COMMON_MASK_HINT}"

_SECTION_HEADER_STYLE = (
    "QFrame#SectionHeader{background:transparent;border:1px solid #222244;border-radius:6px;}"
    "QFrame#SectionHeader:hover{border-color:#3a3a68;}"
)
_SEL_ROW   = "QFrame{background:transparent;border-left:3px solid #e84560;border-radius:3px;}"
_NORM_ROW  = "QFrame{background:transparent;border-left:3px solid transparent;border-radius:3px;}"
_NORM_HOV  = "QFrame:hover{background:transparent;border-left:3px solid #2a2a50;border-radius:3px;}"
_SECTION_LABEL_STYLE = "color:#7070a0;font-size:11px;font-weight:700;letter-spacing:1px;background:transparent;padding:0;"
_GROUP_LABEL_STYLE = "color:#8080b0;font-size:12px;font-weight:700;background:transparent;padding:8px 2px 4px 2px;"

_DRAWABLE_PRESETS = {
    "Default freemode": {"mask": 1, "alternatives": 0, "cloth": False},
    "Cloth-enabled": {"mask": 1, "alternatives": 0, "cloth": True},
    "Alt model (_r)": {"mask": 17, "alternatives": 0, "cloth": False},
}

_COMPONENT_DRAWABLE_PRESETS = {
    2: {"title": "Hair starter", "mask": 1, "alternatives": 0, "cloth": False},
    3: {"title": "Upper starter", "mask": 1, "alternatives": 0, "cloth": True},
    4: {"title": "Lower starter", "mask": 1, "alternatives": 0, "cloth": False},
    6: {"title": "Feet starter", "mask": 1, "alternatives": 0, "cloth": False},
    11: {"title": "Jbib starter", "mask": 1, "alternatives": 0, "cloth": True},
}

_COMPONENT_META_PRESETS = {
    "Neutral / safe defaults": {
        "audio_id": "none",
        "audio_id2": "",
        "expression_mods": [0.0, 0.0, 0.0, 0.0, 0.0],
        "flags": 0,
        "inclusions": "0",
        "exclusions": "0",
        "vfx_comps": "",
        "vfx_flags": 0,
    },
    "Keep VFX, reset flags": {
        "audio_id": "none",
        "audio_id2": "",
        "expression_mods": [0.0, 0.0, 0.0, 0.0, 0.0],
        "flags": 0,
        "inclusions": "0",
        "exclusions": "0",
        "vfx_comps": None,
        "vfx_flags": 0,
    },
}

_PROP_META_PRESETS = {
    "Neutral / safe defaults": {
        "audio_id": "none",
        "expression_mods": [0.0, 0.0, 0.0, 0.0, 0.0],
        "render_flags": "",
        "prop_flags": 0,
        "flags": 0,
        "hash": 0,
    },
    "Keep anchor and id, clear flags": {
        "audio_id": "none",
        "expression_mods": [0.0, 0.0, 0.0, 0.0, 0.0],
        "render_flags": "",
        "prop_flags": 0,
        "flags": 0,
        "hash": 0,
    },
}


class _SmallSpin(QSpinBox):
    def __init__(self, lo: int = 0, hi: int = 255, parent=None):
        super().__init__(parent)
        self.setRange(lo, hi)
        self.setFixedWidth(72)


class _FloatSpin(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(-999.0, 999.0)
        self.setDecimals(3)
        self.setSingleStep(0.01)
        self.setFixedWidth(72)


# ---------------------------------------------------------------------------
#  New-YMT dialog
# ---------------------------------------------------------------------------

class _NewYMTDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create new YMT...")
        self.setFixedSize(400, 260)
        vbox = QVBoxLayout(self)
        vbox.setSpacing(10)

        vbox.addWidget(QLabel("Select which ped your YMT will be for:"))
        self._grp = QButtonGroup(self)
        self._rb_male   = QRadioButton("mp_m_freemode_01  (male)")
        self._rb_female = QRadioButton("mp_f_freemode_01  (female)")
        self._rb_other  = QRadioButton("other ped  (non-mp ped)")
        self._rb_male.setChecked(True)
        for i, rb in enumerate((self._rb_male, self._rb_female, self._rb_other)):
            self._grp.addButton(rb, i)
            vbox.addWidget(rb)

        self._other_edit = QLineEdit()
        self._other_edit.setPlaceholderText("ped model name, e.g. a_m_y_beach_01")
        self._other_edit.setEnabled(False)
        vbox.addWidget(self._other_edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("Input your YMT name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("mynewymt")
        row.addWidget(self._name_edit)
        vbox.addLayout(row)

        self._preview = QLabel("Your full YMT name:  mp_m_freemode_01_")
        self._preview.setObjectName("InfoLabel")
        vbox.addWidget(self._preview)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        vbox.addWidget(btns)

        self._rb_other.toggled.connect(lambda on: self._other_edit.setEnabled(on))
        self._grp.buttonClicked.connect(self._update_preview)
        self._name_edit.textChanged.connect(self._update_preview)
        self._other_edit.textChanged.connect(self._update_preview)

    def _prefix(self) -> str:
        if self._rb_male.isChecked():   return "mp_m_freemode_01"
        if self._rb_female.isChecked(): return "mp_f_freemode_01"
        return self._other_edit.text().strip() or "ped_model"

    def _update_preview(self) -> None:
        n = self._name_edit.text().strip()
        self._preview.setText(f"Your full YMT name:  {self._prefix()}_{n}")

    def result_values(self):
        pfx   = self._prefix()
        short = self._name_edit.text().strip() or "newymt"
        return pfx, short, f"{pfx}_{short}"


# ---------------------------------------------------------------------------
#  Texture row  (one texture inside a component drawable)
# ---------------------------------------------------------------------------

class _TextureRow(QFrame):
    move_up  = Signal(int)
    move_down= Signal(int)
    removed  = Signal(int)
    changed  = Signal()

    def __init__(self, index: int, tex: TextureData, parent=None):
        super().__init__(parent)
        self._index = index
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(4, 2, 4, 2)
        hbox.setSpacing(6)

        self._ltr_lbl = QLabel(f"Texture {_tex_letter(index)}")
        self._ltr_lbl.setFixedWidth(68)
        hbox.addWidget(self._ltr_lbl)

        hbox.addWidget(QLabel("texId:"))
        self._tex_id = _SmallSpin(0, 127)
        self._tex_id.setValue(tex.tex_id)
        self._tex_id.setEnabled(False)
        self._tex_id.setToolTip("Auto-managed from texture order: a=0, b=1, c=2...")
        hbox.addWidget(self._tex_id)

        hbox.addWidget(QLabel("variant:"))
        self._variant = QComboBox()
        self._variant.setFixedWidth(112)
        for label, value in _TEXTURE_VARIANT_PRESETS:
            self._variant.addItem(label, value)
        self._variant.setToolTip("Naming hint only. It is not auto-changed after load.")
        hbox.addWidget(self._variant)

        hbox.addWidget(QLabel("dist:"))
        self._dist = _SmallSpin(0, 255)
        self._dist.setValue(tex.distribution)
        hbox.addWidget(self._dist)

        self._btn_up  = QPushButton("↑"); self._btn_up.setFixedSize(24,24)
        self._btn_dn  = QPushButton("↓"); self._btn_dn.setFixedSize(24,24)
        self._btn_del = QPushButton("×"); self._btn_del.setFixedSize(24,24)
        hbox.addWidget(self._btn_up)
        hbox.addWidget(self._btn_dn)
        hbox.addWidget(self._btn_del)
        hbox.addStretch()

        self._tex_id.valueChanged.connect(lambda *_: self.changed.emit())
        self._dist.valueChanged.connect(lambda *_: self.changed.emit())
        self._variant.currentIndexChanged.connect(lambda *_: self.changed.emit())
        self._btn_up.clicked.connect(lambda: self.move_up.emit(self._index))
        self._btn_dn.clicked.connect(lambda: self.move_down.emit(self._index))
        self._btn_del.clicked.connect(lambda: self.removed.emit(self._index))
        self._sync_variant_from_texid()

    def _sync_variant_from_texid(self) -> None:
        label = _TEXTURE_VARIANT_BY_TEXID.get(self._tex_id.value(), "Custom")
        self._variant.blockSignals(True)
        idx = self._variant.findText(label)
        self._variant.setCurrentIndex(idx if idx >= 0 else 0)
        self._variant.blockSignals(False)

    def get_texture(self) -> TextureData:
        return TextureData(tex_id=self._tex_id.value(), distribution=self._dist.value())

    def set_index(self, i: int) -> None:
        self._index = i
        self._ltr_lbl.setText(f"Texture {_tex_letter(i)}")


class _TextureListWidget(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_TextureRow] = []
        self._vbox = QVBoxLayout(self)
        self._vbox.setContentsMargins(8, 4, 8, 4)
        self._vbox.setSpacing(2)
        bar = QHBoxLayout()
        self._btn_add = QPushButton("+1 texture"); self._btn_add.setFixedHeight(26)
        bar.addWidget(self._btn_add); bar.addStretch()
        self._vbox.addLayout(bar)
        self._btn_add.clicked.connect(self._add_texture)

    def load(self, textures: list[TextureData]) -> None:
        for r in self._rows: r.deleteLater()
        self._rows.clear()
        for i, t in enumerate(textures):
            self._append_row(i, t)
        self._sync_texids_to_index()

    def _append_row(self, idx: int, t: TextureData) -> None:
        row = _TextureRow(idx, t, self)
        row.changed.connect(self.changed)
        row.move_up.connect(self._on_up)
        row.move_down.connect(self._on_down)
        row.removed.connect(self._on_del)
        self._vbox.insertWidget(self._vbox.count() - 1, row)
        self._rows.append(row)

    def _add_texture(self) -> None:
        idx = len(self._rows)
        self._append_row(idx, TextureData(tex_id=idx, distribution=255))
        self._sync_texids_to_index()
        self.changed.emit()

    def _on_up(self, idx: int) -> None:
        if idx <= 0: return
        self._swap(idx, idx - 1)
        self._sync_texids_to_index()
        self.changed.emit()

    def _on_down(self, idx: int) -> None:
        if idx >= len(self._rows) - 1: return
        self._swap(idx, idx + 1)
        self._sync_texids_to_index()
        self.changed.emit()

    def _swap(self, a: int, b: int) -> None:
        ta = self._rows[a].get_texture()
        tb = self._rows[b].get_texture()
        self._rows[a].deleteLater()
        self._rows[b].deleteLater()
        ra = _TextureRow(a, tb, self)
        rb = _TextureRow(b, ta, self)
        for r in (ra, rb):
            r.changed.connect(self.changed)
            r.move_up.connect(self._on_up)
            r.move_down.connect(self._on_down)
            r.removed.connect(self._on_del)
        base = self._vbox.count() - 1 - len(self._rows)
        self._vbox.insertWidget(base + a, ra)
        self._vbox.insertWidget(base + b, rb)
        self._rows[a] = ra
        self._rows[b] = rb

    def _on_del(self, idx: int) -> None:
        if idx >= len(self._rows): return
        self._rows.pop(idx).deleteLater()
        for i in range(idx, len(self._rows)):
            self._rows[i].set_index(i)
        self._sync_texids_to_index()
        self.changed.emit()

    def _sync_texids_to_index(self) -> None:
        for i, row in enumerate(self._rows):
            row._tex_id.blockSignals(True)
            row._tex_id.setValue(i)
            row._tex_id.blockSignals(False)

    def get_textures(self) -> list[TextureData]:
        return [r.get_texture() for r in self._rows]


# ---------------------------------------------------------------------------
#  Prop texture list  (full 6-field rows)
# ---------------------------------------------------------------------------

class _PropTexRow(QFrame):
    removed = Signal(int); changed = Signal()
    def __init__(self, idx: int, t: PropTextureData, parent=None):
        super().__init__(parent)
        self._idx = idx
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(4,2,4,2); hbox.setSpacing(4)
        hbox.addWidget(QLabel(f"Tex {_tex_letter(idx)}"))
        fields = [("texId",str(t.tex_id)),("inc",t.inclusions),("exc",t.exclusions),
                  ("incId",str(t.inclusion_id)),("excId",str(t.exclusion_id)),("dist",str(t.distribution))]
        self._edits: list[QLineEdit] = []
        for lbl,val in fields:
            hbox.addWidget(QLabel(f"{lbl}:"))
            e = QLineEdit(val); e.setFixedWidth(46)
            e.textChanged.connect(lambda *_: self.changed.emit())
            hbox.addWidget(e); self._edits.append(e)
        btn = QPushButton("×"); btn.setFixedSize(22,22)
        btn.clicked.connect(lambda: self.removed.emit(self._idx))
        hbox.addWidget(btn)

    def get_texture(self) -> PropTextureData:
        def v(i,d="0"): t=self._edits[i].text().strip(); return t if t else d
        try:
            return PropTextureData(tex_id=int(v(0)),inclusions=v(1,"0"),exclusions=v(2,"0"),
                inclusion_id=int(v(3)),exclusion_id=int(v(4)),distribution=int(v(5,"255")))
        except ValueError:
            return PropTextureData()

    def set_index(self, i: int) -> None:
        self._idx = i


class _PropTexListWidget(QWidget):
    changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_PropTexRow] = []
        self._vbox = QVBoxLayout(self)
        self._vbox.setContentsMargins(8,4,8,4); self._vbox.setSpacing(2)
        bar = QHBoxLayout()
        self._btn = QPushButton("+1 texture"); self._btn.setFixedHeight(26)
        bar.addWidget(self._btn); bar.addStretch()
        self._vbox.addLayout(bar)
        self._btn.clicked.connect(self._add)

    def load(self, textures: list[PropTextureData]) -> None:
        for r in self._rows: r.deleteLater()
        self._rows.clear()
        for i,t in enumerate(textures): self._append(i,t)

    def _append(self, idx: int, t: PropTextureData) -> None:
        row = _PropTexRow(idx, t, self)
        row.changed.connect(self.changed); row.removed.connect(self._on_del)
        self._vbox.insertWidget(self._vbox.count()-1, row)
        self._rows.append(row)

    def _add(self) -> None:
        idx = len(self._rows); self._append(idx, PropTextureData(tex_id=idx)); self.changed.emit()

    def _on_del(self, idx: int) -> None:
        if idx >= len(self._rows): return
        self._rows.pop(idx).deleteLater()
        for i in range(idx, len(self._rows)): self._rows[i].set_index(i)
        self.changed.emit()

    def get_textures(self) -> list[PropTextureData]:
        return [r.get_texture() for r in self._rows]


# ---------------------------------------------------------------------------
#  Drawable row  (left-panel selectable item)
# ---------------------------------------------------------------------------

class _DrawableRow(QFrame):
    clicked = Signal(object, object)

    def __init__(self, owner, drawable, parent=None):
        super().__init__(parent)
        self._owner = owner; self._drawable = drawable
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_NORM_ROW + _NORM_HOV)
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(12,4,8,4)
        self._lbl = QLabel()
        self._lbl.setStyleSheet("background:transparent;")
        hbox.addWidget(self._lbl); hbox.addStretch()
        self.setFixedHeight(30)
        self.update_label()

    def update_label(self) -> None:
        d = self._drawable
        if isinstance(d, DrawableEntry):
            tc = len(d.textures) or d.texture_count
            comp_code = COMPONENT_NAMES.get(getattr(self._owner, "component_id", -1), getattr(self._owner, "name", "COMP")).upper()
            cl = "  |  cloth sim" if d.has_cloth else ""
            self._lbl.setText(
                f"{comp_code} {d.drawable_id:03d}  |  {tc} textures  |  {_mask_display(d.prop_mask)}{cl}"
            )
        else:
            anchor_name = _PROP_FRIENDLY.get(d.anchor_id, f"Anchor {d.anchor_id}")
            prop_code = PROP_NAMES.get(getattr(self._owner, "prop_id", -1), getattr(self._owner, "name", "PROP")).upper()
            self._lbl.setText(
                f"{prop_code} {d.prop_index:03d}  |  {len(d.textures)} textures  |  {anchor_name}"
            )

    def set_selected(self, sel: bool) -> None:
        self.setStyleSheet(_SEL_ROW if sel else (_NORM_ROW + _NORM_HOV))

    def mousePressEvent(self, ev) -> None:
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._owner, self._drawable)
        super().mousePressEvent(ev)


# ---------------------------------------------------------------------------
#  Accordion section  (one component or prop anchor)
# ---------------------------------------------------------------------------

class _AccordionSection(QFrame):
    drawable_selected = Signal(object, object)
    structure_changed = Signal()

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._rows: list[_DrawableRow] = []
        self._selected_row: Optional[_DrawableRow] = None
        self._collapsed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,4); root.setSpacing(0)

        # Header
        self._hdr = QFrame(); self._hdr.setObjectName("SectionHeader")
        self._hdr.setStyleSheet(_SECTION_HEADER_STYLE)
        self._hdr.setFixedHeight(34); self._hdr.setCursor(Qt.PointingHandCursor)
        hl = QHBoxLayout(self._hdr)
        hl.setContentsMargins(8,0,8,0); hl.setSpacing(6)
        self._arrow = QLabel("▾"); hl.addWidget(self._arrow)
        if isinstance(owner, ComponentEntry):
            title = _component_display(owner.component_id, owner.name)
        else:
            title = _prop_display(owner.prop_id, owner.name)
        lbl = QLabel(title)
        f = lbl.font(); f.setBold(True); lbl.setFont(f)
        hl.addWidget(lbl)
        self._cnt = QLabel()
        hl.addWidget(self._cnt); hl.addStretch()
        self._btn_add = QPushButton("+"); self._btn_add.setFixedSize(22,22)
        self._btn_rem = QPushButton("−"); self._btn_rem.setFixedSize(22,22)
        self._btn_add.setToolTip("Add drawable")
        self._btn_rem.setToolTip("Remove last drawable")
        hl.addWidget(self._btn_add); hl.addWidget(self._btn_rem)
        root.addWidget(self._hdr)

        # Body
        self._body = QFrame()
        self._blay = QVBoxLayout(self._body)
        self._blay.setContentsMargins(0,2,0,2); self._blay.setSpacing(1)
        root.addWidget(self._body)

        self._hdr.mousePressEvent = self._toggle
        self._btn_add.clicked.connect(self._on_add)
        self._btn_rem.clicked.connect(self._on_rem)
        self._populate()

    def _drawables(self):
        return self._owner.drawables if isinstance(self._owner, ComponentEntry) else self._owner.items

    def _populate(self) -> None:
        for r in self._rows: r.deleteLater()
        self._rows.clear(); self._selected_row = None
        for d in self._drawables():
            self._mk_row(d)
        self._update_count()

    def _mk_row(self, drawable) -> _DrawableRow:
        row = _DrawableRow(self._owner, drawable, self._body)
        row.clicked.connect(self._on_row_clicked)
        self._blay.addWidget(row); self._rows.append(row)
        return row

    def _update_count(self) -> None:
        n = len(self._rows)
        self._cnt.setText(f"  {n} drawable{'s' if n!=1 else ''}")
        self._btn_rem.setEnabled(n > 0)

    def _toggle(self, ev=None) -> None:
        self._collapsed = not self._collapsed
        self._body.setVisible(not self._collapsed)
        self._arrow.setText("▸" if self._collapsed else "▾")

    def _on_row_clicked(self, owner, drawable) -> None:
        for r in self._rows:
            sel = r._drawable is drawable
            r.set_selected(sel)
            if sel: self._selected_row = r
        self.drawable_selected.emit(owner, drawable)

    def _on_add(self) -> None:
        if isinstance(self._owner, ComponentEntry):
            comp = self._owner; new_id = len(comp.drawables)
            dd = DrawableEntry(drawable_id=new_id, texture_count=1, prop_mask=1,
                               textures=[TextureData(tex_id=0)])
            dd.comp_info = ComponentInfo(comp_idx=comp.component_id, drawbl_idx=new_id)
            comp.drawables.append(dd)
            row = self._mk_row(dd)
        else:
            pe = self._owner; new_idx = len(pe.items)
            pd = PropDrawable(prop_index=new_idx, anchor_id=pe.prop_id, prop_id=new_idx,
                              textures=[PropTextureData(tex_id=new_idx)])
            pe.items.append(pd)
            row = self._mk_row(pd)
        self._update_count()
        # auto-select
        drawable = row._drawable
        for r in self._rows:
            r.set_selected(r._drawable is drawable)
        self._selected_row = row
        self.drawable_selected.emit(self._owner, drawable)
        self.structure_changed.emit()

    def _on_rem(self) -> None:
        if not self._rows: return
        row = self._rows.pop()
        draws = self._drawables()
        if draws: draws.pop()
        row.deleteLater()
        self._update_count()
        if self._selected_row is row:
            self._selected_row = None
            self.drawable_selected.emit(self._owner, None)
        self.structure_changed.emit()

    def deselect_all(self) -> None:
        for r in self._rows: r.set_selected(False)
        self._selected_row = None

    def refresh(self) -> None:
        self._populate()


# ---------------------------------------------------------------------------
#  Collapsible group box for right panel
# ---------------------------------------------------------------------------

class _CollapsibleGroup(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        self._btn = QPushButton(f"▾  {title}")
        self._btn.setObjectName("CollapsibleHeader")
        self._btn.setCheckable(True); self._btn.setChecked(True)
        self._btn.setFixedHeight(30)
        self._btn.setStyleSheet(
            "QPushButton{background:transparent;border:none;padding:6px 0;text-align:left;font-weight:700;color:#b4b4d8;}"
            "QPushButton:hover{color:#ececff;}"
        )
        self._btn.clicked.connect(self._toggle)
        vbox.addWidget(self._btn)
        self._body = QWidget()
        vbox.addWidget(self._body)
        self.body_layout = QVBoxLayout(self._body)
        self.body_layout.setContentsMargins(12,6,12,6); self.body_layout.setSpacing(6)

    def _toggle(self, checked: bool) -> None:
        self._body.setVisible(checked)
        t = self._btn.text()
        self._btn.setText(t.replace("▸","▾") if checked else t.replace("▾","▸"))


# ---------------------------------------------------------------------------
#  Right-side detail panel
# ---------------------------------------------------------------------------

class _DetailPanel(QScrollArea):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        inner = QWidget(); self.setWidget(inner)
        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(16,16,16,16); self._root.setSpacing(10)

        self._title = QLabel("Select a drawable")
        f = self._title.font(); f.setPointSize(f.pointSize()+2); f.setBold(True)
        self._title.setFont(f)
        self._root.addWidget(self._title)

        self._context = QLabel("Select a drawable on the left to see what component or prop you are editing.")
        self._context.setWordWrap(True)
        self._context.setObjectName("InfoLabel")
        self._root.addWidget(self._context)

        # Drawable props
        self._grp_draw = _CollapsibleGroup("Drawable Basics")
        frm = QFormLayout(); frm.setSpacing(8); frm.setLabelAlignment(Qt.AlignRight)
        draw_preset_row = QHBoxLayout()
        self._draw_preset = QComboBox()
        self._draw_preset.addItems(list(_DRAWABLE_PRESETS.keys()))
        self._btn_apply_draw_preset = QPushButton("Apply preset")
        self._btn_apply_draw_preset.setObjectName("SecondaryButton")
        self._btn_apply_draw_preset.setFixedHeight(34)
        draw_preset_row.addWidget(self._draw_preset)
        draw_preset_row.addWidget(self._btn_apply_draw_preset)
        frm.addRow("Quick preset:", draw_preset_row)
        self._mask_combo = QComboBox()
        for label, value in _MASK_PRESETS:
            self._mask_combo.addItem(label, value)
        self._mask_combo.addItem("Custom mask value", None)
        frm.addRow("Variant preset:", self._mask_combo)
        self._spin_mask = _SmallSpin(0,255)
        self._spin_mask.setToolTip("Original field name: propMask")
        frm.addRow("Mask value:", self._spin_mask)
        self._mask_info = QLabel(_COMMON_MASK_HINT)
        self._mask_info.setWordWrap(True)
        frm.addRow("", self._mask_info)
        self._spin_alt = _SmallSpin(0,255)
        self._spin_alt.setToolTip("Original field name: numAlternatives")
        frm.addRow("Alt count:", self._spin_alt)
        self._chk_cloth = QCheckBox("enabled")
        self._chk_cloth.setToolTip("Original field name: clothData")
        frm.addRow("Cloth sim:", self._chk_cloth)
        self._grp_draw.body_layout.addLayout(frm)
        self._root.addWidget(self._grp_draw)

        # Textures
        self._grp_tex = _CollapsibleGroup("Texture Variants  (a, b, c...) ")
        self._tex_list = _TextureListWidget()
        self._grp_tex.body_layout.addWidget(self._tex_list)
        self._root.addWidget(self._grp_tex)

        # Comp info
        self._grp_ci = _CollapsibleGroup("Advanced Component Data")
        ci = QFormLayout(); ci.setSpacing(6); ci.setLabelAlignment(Qt.AlignRight)
        comp_preset_row = QHBoxLayout()
        self._comp_preset = QComboBox()
        self._comp_preset.addItems(list(_COMPONENT_META_PRESETS.keys()))
        self._btn_apply_comp_preset = QPushButton("Apply preset")
        self._btn_apply_comp_preset.setObjectName("SecondaryButton")
        self._btn_apply_comp_preset.setFixedHeight(34)
        comp_preset_row.addWidget(self._comp_preset)
        comp_preset_row.addWidget(self._btn_apply_comp_preset)
        ci.addRow("Quick preset:", comp_preset_row)
        self._ci_audio  = QLineEdit("none"); self._ci_audio.setToolTip("Original field name: audioId"); ci.addRow("Audio 1:", self._ci_audio)
        self._ci_audio2 = QLineEdit(); self._ci_audio2.setToolTip("Original field name: audioId2"); ci.addRow("Audio 2:", self._ci_audio2)
        em_row = QHBoxLayout()
        self._ci_em = [_FloatSpin() for _ in range(5)]
        for sp in self._ci_em: em_row.addWidget(sp)
        em_row.addStretch(); ci.addRow("Expression mods:", em_row)
        self._ci_flags  = _SmallSpin(0,65535); self._ci_flags.setToolTip("Original field name: flags"); ci.addRow("Flags:", self._ci_flags)
        self._ci_inc    = QLineEdit("0"); self._ci_inc.setToolTip("Original field name: inclusions"); ci.addRow("Includes:", self._ci_inc)
        self._ci_exc    = QLineEdit("0"); self._ci_exc.setToolTip("Original field name: exclusions"); ci.addRow("Excludes:", self._ci_exc)
        self._ci_vfx    = QLineEdit("PV_COMP_HEAD"); self._ci_vfx.setToolTip("Original field name: vfxComps"); ci.addRow("VFX comps:", self._ci_vfx)
        self._ci_vflags = _SmallSpin(0,65535); self._ci_vflags.setToolTip("Original field name: vfxFlags"); ci.addRow("VFX flags:", self._ci_vflags)
        self._grp_ci.body_layout.addLayout(ci)
        self._root.addWidget(self._grp_ci)

        # Prop props
        self._grp_prop = _CollapsibleGroup("Prop Basics")
        pf = QFormLayout(); pf.setSpacing(6); pf.setLabelAlignment(Qt.AlignRight)
        prop_preset_row = QHBoxLayout()
        self._prop_preset = QComboBox()
        self._prop_preset.addItems(list(_PROP_META_PRESETS.keys()))
        self._btn_apply_prop_preset = QPushButton("Apply preset")
        self._btn_apply_prop_preset.setObjectName("SecondaryButton")
        self._btn_apply_prop_preset.setFixedHeight(34)
        prop_preset_row.addWidget(self._prop_preset)
        prop_preset_row.addWidget(self._btn_apply_prop_preset)
        pf.addRow("Quick preset:", prop_preset_row)
        self._p_audio  = QLineEdit("none"); self._p_audio.setToolTip("Original field name: audioId"); pf.addRow("Audio:", self._p_audio)
        p_em = QHBoxLayout()
        self._p_em = [_FloatSpin() for _ in range(5)]
        for sp in self._p_em: p_em.addWidget(sp)
        p_em.addStretch(); pf.addRow("Expression mods:", p_em)
        self._p_rf     = QLineEdit(); self._p_rf.setToolTip("Original field name: renderFlags"); pf.addRow("Render flags:", self._p_rf)
        self._p_pflags = _SmallSpin(0,65535); self._p_pflags.setToolTip("Original field name: propFlags"); pf.addRow("Prop flags:", self._p_pflags)
        self._p_flags  = _SmallSpin(0,65535); self._p_flags.setToolTip("Original field name: flags"); pf.addRow("Flags:", self._p_flags)
        self._p_anch   = _SmallSpin(0,12)
        self._p_anch.setToolTip("Original field name: anchorId")
        pf.addRow("Anchor slot:", self._p_anch)
        self._anchor_info = QLabel("")
        self._anchor_info.setWordWrap(True)
        pf.addRow("", self._anchor_info)
        self._p_pid    = _SmallSpin(0,255); self._p_pid.setToolTip("Original field name: propId"); pf.addRow("Prop id:", self._p_pid)
        self._p_hash   = _SmallSpin(0,2147483647); self._p_hash.setToolTip("Original field name: hash_AC887A91"); pf.addRow("Hash AC887A91:", self._p_hash)
        self._grp_prop.body_layout.addLayout(pf)
        self._root.addWidget(self._grp_prop)

        self._grp_ptex = _CollapsibleGroup("Prop Texture Variants")
        self._ptex = _PropTexListWidget()
        self._grp_ptex.body_layout.addWidget(self._ptex)
        self._root.addWidget(self._grp_ptex)
        self._root.addStretch()

        for g in (self._grp_draw, self._grp_tex, self._grp_ci,
                  self._grp_prop, self._grp_ptex):
            g.setVisible(False)

        # Wire signals
        self._spin_mask.valueChanged.connect(self._on_draw_ch)
        self._mask_combo.currentIndexChanged.connect(self._on_mask_preset_changed)
        self._spin_alt.valueChanged.connect(self._on_draw_ch)
        self._chk_cloth.stateChanged.connect(self._on_draw_ch)
        self._btn_apply_draw_preset.clicked.connect(self._apply_drawable_preset)
        self._tex_list.changed.connect(self._on_tex_ch)
        for w in (self._ci_audio, self._ci_audio2, self._ci_inc, self._ci_exc, self._ci_vfx):
            w.textChanged.connect(self._on_ci_ch)
        for w in (self._ci_flags, self._ci_vflags):
            w.valueChanged.connect(self._on_ci_ch)
        for sp in self._ci_em: sp.valueChanged.connect(self._on_ci_ch)
        self._btn_apply_comp_preset.clicked.connect(self._apply_component_preset)
        for w in (self._p_audio, self._p_rf):         w.textChanged.connect(self._on_prop_ch)
        for w in (self._p_pflags,self._p_flags,self._p_anch,self._p_pid,self._p_hash):
            w.valueChanged.connect(self._on_prop_ch)
        for sp in self._p_em: sp.valueChanged.connect(self._on_prop_ch)
        self._btn_apply_prop_preset.clicked.connect(self._apply_prop_preset)
        self._ptex.changed.connect(self._on_ptex_ch)

        self._loading = False
        self._comp: Optional[ComponentEntry] = None
        self._dd:   Optional[DrawableEntry]  = None
        self._pe:   Optional[PropEntry]      = None
        self._pd:   Optional[PropDrawable]   = None
        self._draw_preset_items: list[dict[str, object]] = []

    # load helpers
    def _populate_drawable_presets(self, comp_id: int) -> None:
        self._draw_preset.blockSignals(True)
        self._draw_preset.clear()
        self._draw_preset_items = []

        comp_preset = _COMPONENT_DRAWABLE_PRESETS.get(comp_id)
        if comp_preset is not None:
            self._draw_preset.addItem(f"{comp_preset['title']} ({COMPONENT_NAMES.get(comp_id, comp_id)})")
            self._draw_preset_items.append(comp_preset)

        for name, preset in _DRAWABLE_PRESETS.items():
            self._draw_preset.addItem(name)
            self._draw_preset_items.append(preset)

        self._draw_preset.setCurrentIndex(0)
        self._draw_preset.blockSignals(False)

    def load_drawable(self, comp: ComponentEntry, dd: DrawableEntry) -> None:
        self._loading = True
        self._comp=comp; self._dd=dd; self._pe=None; self._pd=None
        self._populate_drawable_presets(comp.component_id)
        display = _component_display(comp.component_id, comp.name)
        texture_count = len(dd.textures) or dd.texture_count
        self._title.setText(f"Drawable {dd.drawable_id:03d}")
        self._context.setText(
            f"Editing {display}. Model variant uses {_mask_display(dd.prop_mask)}. Texture variants are separate names like _a_uni/_a_whi. Current texture count: {texture_count}."
        )
        for g in (self._grp_draw,self._grp_tex,self._grp_ci): g.setVisible(True)
        for g in (self._grp_prop,self._grp_ptex):              g.setVisible(False)
        self._spin_mask.setValue(dd.prop_mask)
        self._sync_mask_combo(dd.prop_mask)
        self._mask_info.setText(_mask_hint(dd.prop_mask))
        self._spin_alt.setValue(dd.num_alternatives)
        self._chk_cloth.setChecked(dd.has_cloth)
        textures = dd.textures or [TextureData(tex_id=i) for i in range(dd.texture_count)]
        self._tex_list.load(textures)
        ci = dd.comp_info or ComponentInfo(comp_idx=comp.component_id, drawbl_idx=dd.drawable_id)
        self._ci_audio.setText(ci.audio_id)
        self._ci_audio2.setText(ci.audio_id2)
        mods = ci.expression_mods
        for i,sp in enumerate(self._ci_em):
            try: sp.setValue(float(mods[i]) if i<len(mods) else 0.0)
            except: sp.setValue(0.0)
        self._ci_flags.setValue(ci.flags)
        self._ci_inc.setText(ci.inclusions)
        self._ci_exc.setText(ci.exclusions)
        self._ci_vfx.setText(ci.vfx_comps)
        self._ci_vflags.setValue(ci.vfx_flags)
        self._loading = False

    def load_prop_draw(self, pe: PropEntry, pd: PropDrawable) -> None:
        self._loading = True
        self._comp=None; self._dd=None; self._pe=pe; self._pd=pd
        display = _prop_display(pe.prop_id, pe.name)
        anchor_name = _PROP_FRIENDLY.get(pd.anchor_id, f"Anchor {pd.anchor_id}")
        self._title.setText(f"Prop drawable {pd.prop_index:03d}")
        self._context.setText(
            f"Editing {display}. This prop drawable is attached to {anchor_name} and has {len(pd.textures)} texture variant(s)."
        )
        for g in (self._grp_draw,self._grp_tex,self._grp_ci): g.setVisible(False)
        for g in (self._grp_prop,self._grp_ptex):              g.setVisible(True)
        self._p_audio.setText(pd.audio_id)
        mods = pd.expression_mods
        for i,sp in enumerate(self._p_em):
            try: sp.setValue(float(mods[i]) if i<len(mods) else 0.0)
            except: sp.setValue(0.0)
        self._p_rf.setText(pd.render_flags)
        self._p_pflags.setValue(pd.prop_flags)
        self._p_flags.setValue(pd.flags)
        self._p_anch.setValue(pd.anchor_id)
        self._anchor_info.setText(f"Anchor name: {anchor_name}")
        self._p_pid.setValue(pd.prop_id)
        self._p_hash.setValue(pd.hash_AC887A91)
        self._ptex.load(pd.textures)
        self._loading = False

    def clear(self) -> None:
        self._title.setText("Select a drawable")
        self._context.setText("Select a drawable on the left to see what component or prop you are editing.")
        for g in (self._grp_draw,self._grp_tex,self._grp_ci,self._grp_prop,self._grp_ptex):
            g.setVisible(False)
        self._comp=self._dd=self._pe=self._pd=None

    def _sync_mask_combo(self, mask: int) -> None:
        self._mask_combo.blockSignals(True)
        matched = False
        for index, (_label, value) in enumerate(_MASK_PRESETS):
            if value == mask:
                self._mask_combo.setCurrentIndex(index)
                matched = True
                break
        if not matched:
            self._mask_combo.setCurrentIndex(self._mask_combo.count() - 1)
        self._mask_combo.blockSignals(False)

    def _on_mask_preset_changed(self) -> None:
        value = self._mask_combo.currentData()
        if value is None:
            self._mask_info.setText(_mask_hint(self._spin_mask.value()))
            return
        if self._spin_mask.value() != int(value):
            self._spin_mask.setValue(int(value))
        else:
            self._mask_info.setText(_mask_hint(int(value)))

    def _apply_drawable_preset(self) -> None:
        if self._loading or not self._dd:
            return
        idx = self._draw_preset.currentIndex()
        if idx < 0 or idx >= len(self._draw_preset_items):
            return
        preset = self._draw_preset_items[idx]
        self._mask_combo.blockSignals(True)
        self._spin_mask.setValue(int(preset["mask"]))
        self._sync_mask_combo(int(preset["mask"]))
        self._mask_combo.blockSignals(False)
        self._spin_alt.setValue(int(preset["alternatives"]))
        self._chk_cloth.setChecked(bool(preset["cloth"]))
        self._on_draw_ch()

    def _apply_component_preset(self) -> None:
        if self._loading or not self._dd:
            return
        preset = _COMPONENT_META_PRESETS[self._comp_preset.currentText()]
        self._ci_audio.setText(preset["audio_id"])
        self._ci_audio2.setText(preset["audio_id2"])
        for spin, value in zip(self._ci_em, preset["expression_mods"]):
            spin.setValue(value)
        self._ci_flags.setValue(preset["flags"])
        self._ci_inc.setText(preset["inclusions"])
        self._ci_exc.setText(preset["exclusions"])
        if preset["vfx_comps"] is not None:
            self._ci_vfx.setText(preset["vfx_comps"])
        self._ci_vflags.setValue(preset["vfx_flags"])
        self._on_ci_ch()

    def _apply_prop_preset(self) -> None:
        if self._loading or not self._pd:
            return
        preset = _PROP_META_PRESETS[self._prop_preset.currentText()]
        self._p_audio.setText(preset["audio_id"])
        for spin, value in zip(self._p_em, preset["expression_mods"]):
            spin.setValue(value)
        self._p_rf.setText(preset["render_flags"])
        self._p_pflags.setValue(preset["prop_flags"])
        self._p_flags.setValue(preset["flags"])
        self._p_hash.setValue(preset["hash"])
        self._on_prop_ch()

    # change handlers
    def _on_draw_ch(self) -> None:
        if self._loading or not self._dd: return
        self._dd.prop_mask=self._spin_mask.value(); self._dd.flags=self._dd.prop_mask
        self._dd.num_alternatives=self._spin_alt.value()
        self._dd.has_cloth=self._chk_cloth.isChecked()
        self._sync_mask_combo(self._dd.prop_mask)
        self._mask_info.setText(_mask_hint(self._dd.prop_mask))
        if self._comp:
            texture_count = len(self._dd.textures) or self._dd.texture_count
            self._context.setText(
                f"Editing {_component_display(self._comp.component_id, self._comp.name)}. Model variant uses {_mask_display(self._dd.prop_mask)}. Texture variants are separate names like _a_uni/_a_whi. Current texture count: {texture_count}."
            )
        self.changed.emit()

    def _on_tex_ch(self) -> None:
        if self._loading or not self._dd: return
        t=self._tex_list.get_textures(); self._dd.textures=t; self._dd.texture_count=len(t)
        if self._comp:
            self._context.setText(
                f"Editing {_component_display(self._comp.component_id, self._comp.name)}. Model variant uses {_mask_display(self._dd.prop_mask)}. Texture variants are separate names like _a_uni/_a_whi. Current texture count: {len(t)}."
            )
        self.changed.emit()

    def _on_ci_ch(self) -> None:
        if self._loading or not self._dd: return
        if not self._dd.comp_info:
            cid=self._comp.component_id if self._comp else 0
            self._dd.comp_info=ComponentInfo(comp_idx=cid,drawbl_idx=self._dd.drawable_id)
        ci=self._dd.comp_info
        ci.audio_id=self._ci_audio.text(); ci.audio_id2=self._ci_audio2.text()
        ci.expression_mods=[str(sp.value()) for sp in self._ci_em]
        ci.flags=self._ci_flags.value(); ci.inclusions=self._ci_inc.text()
        ci.exclusions=self._ci_exc.text(); ci.vfx_comps=self._ci_vfx.text()
        ci.vfx_flags=self._ci_vflags.value()

    def _on_prop_ch(self) -> None:
        if self._loading or not self._pd: return
        p=self._pd; p.audio_id=self._p_audio.text()
        p.expression_mods=[str(sp.value()) for sp in self._p_em]
        p.render_flags=self._p_rf.text(); p.prop_flags=self._p_pflags.value()
        p.flags=self._p_flags.value(); p.anchor_id=self._p_anch.value()
        p.prop_id=self._p_pid.value(); p.hash_AC887A91=self._p_hash.value()
        anchor_name = _PROP_FRIENDLY.get(p.anchor_id, f"Anchor {p.anchor_id}")
        self._anchor_info.setText(f"Anchor name: {anchor_name}")
        if self._pe:
            self._context.setText(
                f"Editing {_prop_display(self._pe.prop_id, self._pe.name)}. This prop drawable is attached to {anchor_name} and has {len(p.textures)} texture variant(s)."
            )
        self.changed.emit()

    def _on_ptex_ch(self) -> None:
        if self._loading or not self._pd: return
        self._pd.textures=self._ptex.get_textures()
        anchor_name = _PROP_FRIENDLY.get(self._pd.anchor_id, f"Anchor {self._pd.anchor_id}")
        if self._pe:
            self._context.setText(
                f"Editing {_prop_display(self._pe.prop_id, self._pe.name)}. This prop drawable is attached to {anchor_name} and has {len(self._pd.textures)} texture variant(s)."
            )
        self.changed.emit()


# ---------------------------------------------------------------------------
#  Main editor widget
# ---------------------------------------------------------------------------

class YMTEditorWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._ymt: Optional[YMTFile] = None
        self._sections: list[_AccordionSection] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_file_header())
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left_panel())
        self._detail = _DetailPanel()
        self._detail.changed.connect(self._on_detail_changed)
        splitter.addWidget(self._detail)
        splitter.setSizes([380,660])
        root.addWidget(splitter,1)
        root.addWidget(self._build_status_bar())

    def _build_toolbar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("Toolbar"); bar.setFixedHeight(52)
        h = QHBoxLayout(bar); h.setContentsMargins(16,0,16,0); h.setSpacing(8)
        h.addWidget(QLabel("YMT Editor", objectName="PanelTitle")); h.addStretch()
        btn_new = QPushButton("New YMT"); btn_new.setObjectName("SecondaryButton")
        btn_new.clicked.connect(self._new_ymt); h.addWidget(btn_new)
        btn_open = QPushButton("Open YMT"); btn_open.setObjectName("PrimaryButton")
        btn_open.clicked.connect(self._open_ymt); h.addWidget(btn_open)
        self._btn_save = QPushButton("Save YMT"); self._btn_save.setObjectName("PrimaryButton")
        self._btn_save.setEnabled(False); self._btn_save.clicked.connect(self._save_ymt)
        h.addWidget(self._btn_save)
        self._btn_exp = QPushButton("Export XML"); self._btn_exp.setObjectName("SecondaryButton")
        self._btn_exp.setEnabled(False); self._btn_exp.clicked.connect(self._export_xml)
        h.addWidget(self._btn_exp)
        self._btn_creature = QPushButton("Export creaturemetadata.ymt")
        self._btn_creature.setObjectName("SecondaryButton")
        self._btn_creature.setEnabled(False)
        self._btn_creature.clicked.connect(self._export_creaturemetadata_ymt)
        h.addWidget(self._btn_creature)
        return bar

    def _build_file_header(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("ListPanel"); frame.setFixedHeight(44)
        h = QHBoxLayout(frame); h.setContentsMargins(16,4,16,4)
        h.addWidget(QLabel("File:", objectName="FormLabel"))
        self._lbl_file_name = QLabel("none")
        self._lbl_file_name.setObjectName("InfoLabel")
        self._lbl_file_name.setFixedWidth(180)
        h.addWidget(self._lbl_file_name)
        h.addSpacing(10)
        h.addWidget(QLabel("Ped:", objectName="FormLabel"))
        self._lbl_ped = QLabel("unknown")
        self._lbl_ped.setObjectName("InfoLabel")
        self._lbl_ped.setFixedWidth(180)
        h.addWidget(self._lbl_ped)
        h.addSpacing(18)
        h.addWidget(QLabel("dlcName:", objectName="FormLabel"))
        self._edit_dlc = QLineEdit(); self._edit_dlc.setPlaceholderText("mp_m_yourdlcname")
        self._edit_dlc.setFixedWidth(220); self._edit_dlc.setEnabled(False)
        self._edit_dlc.textChanged.connect(self._on_dlc_changed); h.addWidget(self._edit_dlc)
        h.addSpacing(24)
        self._chk_tv  = QCheckBox("HasTexVariations")
        self._chk_dv  = QCheckBox("HasDrawblVariations")
        self._chk_ll  = QCheckBox("HasLowLODs")
        self._chk_sl  = QCheckBox("IsSuperLOD")
        for chk in (self._chk_tv, self._chk_dv, self._chk_ll, self._chk_sl):
            chk.setEnabled(False); chk.stateChanged.connect(self._on_flag_changed); h.addWidget(chk)
        h.addStretch(); return frame

    def _build_left_panel(self) -> QFrame:
        outer = QFrame(); outer.setObjectName("ListPanel"); outer.setMinimumWidth(320)
        vbox = QVBoxLayout(outer); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        hdr = QFrame(); hdr.setObjectName("Toolbar"); hdr.setFixedHeight(46)
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,0,10,0); hl.setSpacing(6)
        structure_label = QLabel("Structure")
        structure_label.setStyleSheet(_SECTION_LABEL_STYLE)
        hl.addWidget(structure_label); hl.addStretch()
        self._btn_cm = QPushButton("Components ▾"); self._btn_cm.setObjectName("SecondaryButton")
        self._btn_cm.setFixedHeight(34); self._btn_cm.clicked.connect(self._show_comp_menu)
        hl.addWidget(self._btn_cm)
        self._btn_pm = QPushButton("Props ▾"); self._btn_pm.setObjectName("SecondaryButton")
        self._btn_pm.setFixedHeight(34); self._btn_pm.clicked.connect(self._show_prop_menu)
        hl.addWidget(self._btn_pm)
        vbox.addWidget(hdr)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._acc_w = QWidget(); self._acc_l = QVBoxLayout(self._acc_w)
        self._acc_l.setContentsMargins(6,6,6,6); self._acc_l.setSpacing(4)
        self._acc_l.addStretch(); scroll.setWidget(self._acc_w)
        vbox.addWidget(scroll); return outer

    def _build_status_bar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("StatusBar"); bar.setFixedHeight(28)
        h = QHBoxLayout(bar); h.setContentsMargins(16,0,16,0)
        self._lbl_status = QLabel("No file loaded"); self._lbl_status.setObjectName("StatusLabel")
        h.addWidget(self._lbl_status); h.addStretch(); return bar

    # file ops
    def _new_ymt(self) -> None:
        dlg = _NewYMTDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        pfx, short, full = dlg.result_values()
        self._ymt = YMTFile(path=Path(f"{full}.ymt")); self._ymt.dlc_name = full
        self._refresh_all(); self._set_status(f"Created: {full}.ymt")

    def _open_ymt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self,"Open YMT","","Clothing Metadata (*.ymt *.ymt.xml)")
        if not path: return
        try:
            self._ymt = YMTFile.load(path)
            self._ymt.dlc_name = _normalize_dlc_name(self._ymt.dlc_name, Path(path).stem)
            self._refresh_all()
            self._set_status(f"Opened: {Path(path).name}")
        except Exception as exc:
            QMessageBox.critical(self,"Error Loading YMT",str(exc))

    def _save_ymt(self) -> None:
        if not self._ymt: return
        out,_ = QFileDialog.getSaveFileName(self,"Save YMT",str(self._ymt.path),"Clothing Metadata (*.ymt)")
        if not out: return
        try:
            self._ymt.save(Path(out)); self._set_status(f"Saved: {out}")
            QMessageBox.information(self,"Saved",f"Saved to:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self,"Save Failed",str(exc))

    def _export_xml(self) -> None:
        if not self._ymt: return
        out,_ = QFileDialog.getSaveFileName(self,"Export XML",str(self._ymt.path)+".xml","XML (*.xml)")
        if not out: return
        try:
            self._ymt.save_xml(Path(out)); self._set_status(f"Exported XML: {out}")
        except Exception as exc:
            QMessageBox.critical(self,"Export Failed",str(exc))

    def _export_creaturemetadata_ymt(self) -> None:
        if not self._ymt:
            return
        dlc_source = _normalize_dlc_name(self._ymt.dlc_name, self._ymt.path.stem)
        collection = dlc_source
        if collection.startswith("mp_m_freemode_01_"):
            collection = collection[len("mp_m_freemode_01_"):]
        elif collection.startswith("mp_f_freemode_01_"):
            collection = collection[len("mp_f_freemode_01_"):]
        if collection.startswith("mp_m_") or collection.startswith("mp_f_"):
            collection = collection[5:]
        default_name = f"mp_creaturemetadata_{collection}.ymt"
        out, _ = QFileDialog.getSaveFileName(self, "Export CreatureMetadata YMT", default_name, "YMT (*.ymt)")
        if not out:
            return
        content = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<CPedModelInfo__InitDataList>\n"
            "  <residentTxd>uppr_diff_000_a_uni</residentTxd>\n"
            "  <InitDatas>\n"
            "    <Item>\n"
            f"      <Name>MP_CreatureMetadata_{collection}</Name>\n"
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
        try:
            Path(out).write_text(content, encoding="utf-8")
            self._set_status(f"Exported creaturemetadata ymt: {out}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    # menus
    def _show_comp_menu(self) -> None:
        if not self._ymt: return
        menu = QMenu(self)
        used = {c.component_id for c in self._ymt.components}
        for cid in sorted(COMPONENT_NAMES):
            act = QAction(_component_display(cid), menu)
            act.setCheckable(True); act.setChecked(cid in used)
            act.triggered.connect(lambda chk, c=cid, n=COMPONENT_NAMES[cid]: self._toggle_comp(c,n,chk))
            menu.addAction(act)
        menu.exec(QCursor.pos())

    def _show_prop_menu(self) -> None:
        if not self._ymt: return
        menu = QMenu(self)
        used = {p.prop_id for p in self._ymt.props}
        for pid in sorted(PROP_NAMES):
            act = QAction(_prop_display(pid), menu)
            act.setCheckable(True); act.setChecked(pid in used)
            act.triggered.connect(lambda chk, p=pid, n=PROP_NAMES[pid]: self._toggle_prop(p,n,chk))
            menu.addAction(act)
        menu.exec(QCursor.pos())

    def _toggle_comp(self, cid: int, name: str, add: bool) -> None:
        if not self._ymt: return
        if add:
            if not any(c.component_id==cid for c in self._ymt.components):
                self._ymt.components.append(ComponentEntry(name=name, component_id=cid))
                if cid < len(self._ymt.avail_comp): self._ymt.avail_comp[cid]=len(self._ymt.components)-1
                self._set_status(f"Added component: {name}")
        else:
            self._ymt.components=[c for c in self._ymt.components if c.component_id!=cid]
            self._set_status(f"Removed component: {name}")
        self._rebuild_accordion()

    def _toggle_prop(self, pid: int, name: str, add: bool) -> None:
        if not self._ymt: return
        if add:
            if not any(p.prop_id==pid for p in self._ymt.props):
                self._ymt.props.append(PropEntry(name=name, prop_id=pid))
                self._set_status(f"Added prop: {name}")
        else:
            self._ymt.props=[p for p in self._ymt.props if p.prop_id!=pid]
            self._set_status(f"Removed prop: {name}")
        self._rebuild_accordion()

    # accordion
    def _clear_accordion(self) -> None:
        while self._acc_l.count() > 1:
            item = self._acc_l.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._sections.clear()

    def _rebuild_accordion(self) -> None:
        self._clear_accordion()
        if not self._ymt: return
        insert = 0

        if self._ymt.components:
            lbl = QLabel("  Components"); f=lbl.font(); f.setBold(True); lbl.setFont(f)
            lbl.setObjectName("SectionGroupLabel")
            lbl.setStyleSheet(_GROUP_LABEL_STYLE)
            self._acc_l.insertWidget(insert, lbl); insert+=1
            for comp in sorted(self._ymt.components, key=lambda c:c.component_id):
                sec = _AccordionSection(comp, self._acc_w)
                sec.drawable_selected.connect(self._on_sel)
                sec.structure_changed.connect(self._upd_status)
                self._acc_l.insertWidget(insert, sec); self._sections.append(sec); insert+=1

        if self._ymt.props:
            lbl2 = QLabel("  Props"); f=lbl2.font(); f.setBold(True); lbl2.setFont(f)
            lbl2.setObjectName("SectionGroupLabel")
            lbl2.setStyleSheet(_GROUP_LABEL_STYLE)
            self._acc_l.insertWidget(insert, lbl2); insert+=1
            for pe in sorted(self._ymt.props, key=lambda p:p.prop_id):
                sec = _AccordionSection(pe, self._acc_w)
                sec.drawable_selected.connect(self._on_sel)
                sec.structure_changed.connect(self._upd_status)
                self._acc_l.insertWidget(insert, sec); self._sections.append(sec); insert+=1

        self._upd_status()

    def _refresh_all(self) -> None:
        if not self._ymt: return
        self._ymt.dlc_name = _normalize_dlc_name(self._ymt.dlc_name, self._ymt.path.stem)
        self._lbl_file_name.setText(self._ymt.path.name)
        ped_source = self._ymt.dlc_name or self._ymt.path.stem
        self._lbl_ped.setText(_infer_ped_from_name(ped_source))
        self._edit_dlc.setEnabled(True)
        for sig, txt in [(self._edit_dlc, self._ymt.dlc_name)]: sig.blockSignals(True); sig.setText(txt); sig.blockSignals(False)
        for chk,attr in [(self._chk_tv,"has_tex_variations"),(self._chk_dv,"has_drawbl_variations"),
                         (self._chk_ll,"has_low_lods"),(self._chk_sl,"is_super_lod")]:
            chk.setEnabled(True); chk.blockSignals(True)
            chk.setChecked(getattr(self._ymt,attr,False)); chk.blockSignals(False)
        self._btn_cm.setEnabled(True); self._btn_pm.setEnabled(True)
        self._btn_save.setEnabled(True); self._btn_exp.setEnabled(True); self._btn_creature.setEnabled(True)
        self._detail.clear()
        self._clear_accordion()
        self._rebuild_accordion()

    # selection
    def _on_sel(self, owner, drawable) -> None:
        for sec in self._sections:
            if sec._owner is not owner: sec.deselect_all()
        if drawable is None: self._detail.clear(); return
        if isinstance(owner, ComponentEntry) and isinstance(drawable, DrawableEntry):
            self._detail.load_drawable(owner, drawable)
        elif isinstance(owner, PropEntry) and isinstance(drawable, PropDrawable):
            self._detail.load_prop_draw(owner, drawable)

    def _on_detail_changed(self) -> None:
        for sec in self._sections:
            if sec._selected_row is not None:
                sec._selected_row.update_label()
        self._upd_status()

    # change handlers
    def _on_dlc_changed(self) -> None:
        if self._ymt:
            self._ymt.dlc_name = self._edit_dlc.text()
            self._lbl_ped.setText(_infer_ped_from_name(self._ymt.dlc_name))

    def _on_flag_changed(self) -> None:
        if not self._ymt: return
        self._ymt.has_tex_variations=self._chk_tv.isChecked()
        self._ymt.has_drawbl_variations=self._chk_dv.isChecked()
        self._ymt.has_low_lods=self._chk_ll.isChecked()
        self._ymt.is_super_lod=self._chk_sl.isChecked()

    def _upd_status(self) -> None:
        if not self._ymt: return
        td=sum(len(c.drawables) for c in self._ymt.components)
        tp=sum(len(p.items) for p in self._ymt.props)
        self._set_status(f"{self._ymt.path.name}  |  {len(self._ymt.components)} components  |  {td} drawables  |  {tp} prop drawables")

    def _set_status(self, msg: str) -> None:
        self._lbl_status.setText(msg)
