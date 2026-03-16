"""
ymt_service.py
--------------
Service layer for reading and writing GTA V clothing metadata (.ymt).

Depends on CodeWalker.Core.dll via gta_bridge.

Uses RpfFile.LoadResourceFile<PedFile> + MetaXml.GetXml to read the binary
format without requiring a sidecar XML, then falls back to sidecar if the
binary path fails.  Saving round-trips through XmlMeta.GetMeta + ResourceBuilder.

Data model closely mirrors YMTEditor:
  https://github.com/grzybeek/YMTEditor
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from core.gta_bridge import initialize as _init, require as _require

logger = logging.getLogger(__name__)

# ── Component / Prop name tables ───────────────────────────────────────────────

COMPONENT_NAMES: dict[int, str] = {
    0: "Head", 1: "Berd", 2: "Hair", 3: "Uppr", 4: "Lowr",
    5: "Hand", 6: "Feet", 7: "Teef", 8: "Accs", 9: "Task",
    10: "Decl", 11: "Jbib",
}

PROP_NAMES: dict[int, str] = {
    0: "p_head", 1: "p_eyes", 2: "p_ears", 3: "p_mouth",
    4: "p_lhand", 5: "p_rhand", 6: "p_lwrist", 7: "p_rwrist",
    8: "p_lfoot", 9: "p_rfoot", 10: "p_ph_l_hand", 11: "p_ph_r_hand",
    12: "p_hat_ped",
}

# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class TextureData:
    """One texture slot inside a drawable (component side)."""
    tex_id: int = 0
    distribution: int = 255


@dataclass
class ComponentInfo:
    """Per-drawable extra info from the compInfos section."""
    audio_id: str = "none"
    audio_id2: str = ""
    expression_mods: list[str] = field(default_factory=lambda: ["0", "0", "0", "0", "0"])
    flags: int = 0
    inclusions: str = "0"
    exclusions: str = "0"
    vfx_comps: str = "PV_COMP_HEAD"
    vfx_flags: int = 0
    comp_idx: int = 0      # component ID (0-11)
    drawbl_idx: int = 0    # drawable index within that component


@dataclass
class DrawableEntry:
    """One .ydd drawable variation for a component."""
    drawable_id: int
    texture_count: int = 0          # kept for backwards-compat
    prop_mask: int = 1
    num_alternatives: int = 0
    has_cloth: bool = False
    textures: list[TextureData] = field(default_factory=list)
    comp_info: ComponentInfo | None = None
    flags: int = 0                   # alias for prop_mask (legacy)


@dataclass
class PropTextureData:
    """One texture slot inside a prop drawable."""
    tex_id: int = 0
    inclusions: str = "0"
    exclusions: str = "0"
    inclusion_id: int = 0
    exclusion_id: int = 0
    distribution: int = 255


@dataclass
class PropDrawable:
    """One .ydd variation for a prop anchor."""
    prop_index: int
    anchor_id: int = 0
    prop_id: int = 0
    audio_id: str = "none"
    expression_mods: list[str] = field(default_factory=lambda: ["0", "0", "0", "0", "0"])
    render_flags: str = ""
    prop_flags: int = 0
    flags: int = 0
    hash_AC887A91: int = 0
    textures: list[PropTextureData] = field(default_factory=list)


@dataclass
class ComponentEntry:
    name: str
    component_id: int
    drawables: list[DrawableEntry] = field(default_factory=list)


@dataclass
class PropEntry:
    name: str
    prop_id: int           # anchor ID
    items: list[PropDrawable] = field(default_factory=list)


@dataclass
class YMTFile:
    path: Path
    components: list[ComponentEntry] = field(default_factory=list)
    props: list[PropEntry] = field(default_factory=list)
    dlc_name: str = ""
    has_tex_variations: bool = False
    has_drawbl_variations: bool = False
    has_low_lods: bool = False
    is_super_lod: bool = False
    avail_comp: list[int] = field(default_factory=lambda: [255] * 12)
    _native_xml: str = field(default="", repr=False, compare=False)
    _source_xml_path: Path | None = field(default=None, repr=False, compare=False)

    # ── Public API ─────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str | Path) -> "YMTFile":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"YMT file not found: {path}")
        _init()
        _require()
        return cls._load_via_codewalker(path)

    # ── Loading ────────────────────────────────────────────────────────────────

    @classmethod
    def _load_via_codewalker(cls, path: Path) -> "YMTFile":
        from CodeWalker.GameFiles import PedFile, RpfFile, MetaXml  # type: ignore
        from System.IO import File  # type: ignore

        lower_name = path.name.lower()
        is_non_variation_ymt = "creaturemetadata" in lower_name

        data = File.ReadAllBytes(str(path))
        ped = PedFile()
        try:
            RpfFile.LoadResourceFile[PedFile](ped, data, 2)
            xml_str = str(MetaXml.GetXml(ped.Meta))
            instance = cls(path=path, _native_xml=xml_str)
            instance._parse_ped_xml(ET.fromstring(xml_str))
            return instance
        except Exception as exc:
            if is_non_variation_ymt:
                logger.info(
                    "Skipping CPedVariationInfo parse for non-variation YMT '%s': %s",
                    path,
                    exc,
                )
            else:
                logger.warning("Binary PedFile parse failed for '%s': %s — trying sidecar.", path, exc)

        xml_path = path.with_suffix(path.suffix + ".xml")
        if xml_path.exists():
            xml_str = xml_path.read_text(encoding="utf-8", errors="replace")
            instance = cls(path=path, _native_xml=xml_str, _source_xml_path=xml_path)
            instance._parse_ped_xml(ET.fromstring(xml_str))
            return instance

        if is_non_variation_ymt:
            logger.debug(
                "Non-variation YMT '%s' has no sidecar XML; returning empty clothing view.",
                path,
            )
        else:
            logger.warning(
                "YMT '%s' did not expose clothing variation info and no sidecar XML was found.",
                path,
            )
        return cls(path=path)

    def _parse_ped_xml(self, root: ET.Element) -> None:
        """Parse a CPedVariationInfo XML element into this instance."""

        # ---- Top-level flags --------------------------------------------------
        self.dlc_name = (root.findtext("dlcName") or "").strip()
        self.has_tex_variations = _xml_bool(root.find("bHasTexVariations"))
        self.has_drawbl_variations = _xml_bool(root.find("bHasDrawblVariations"))
        self.has_low_lods = _xml_bool(root.find("bHasLowLODs"))
        self.is_super_lod = _xml_bool(root.find("bIsSuperLOD"))

        # ---- availComp → ordered list of active component IDs ----------------
        avail_comp = _parse_avail_comp(root.find("availComp"))
        self.avail_comp = avail_comp
        active_ids = [i for i, v in enumerate(avail_comp) if v != 255]

        # ---- aComponentData3 -------------------------------------------------
        comp_root = root.find("aComponentData3")
        if comp_root is not None:
            items = comp_root.findall("Item")
            # When all 12 slots are present use positional index → comp ID.
            # When only active slots are present, use active_ids mapping.
            use_active_map = len(items) == len(active_ids) and len(items) < 12
            for slot_idx, comp_item in enumerate(items):
                if use_active_map and slot_idx < len(active_ids):
                    comp_id = active_ids[slot_idx]
                else:
                    comp_id = slot_idx
                comp_name = COMPONENT_NAMES.get(comp_id, f"Comp_{comp_id}")
                drawables: list[DrawableEntry] = []
                drawable_root = comp_item.find("aDrawblData3")
                if drawable_root is not None:
                    for draw_id, draw_item in enumerate(drawable_root.findall("Item")):
                        tex_root = draw_item.find("aTexData")
                        textures: list[TextureData] = []
                        if tex_root is not None:
                            for tex_item in tex_root.findall("Item"):
                                textures.append(TextureData(
                                    tex_id=_xml_int(tex_item.find("texId"), "value", 0),
                                    distribution=_xml_int(tex_item.find("distribution"), "value", 255),
                                ))
                        cloth_el = draw_item.find("clothData")
                        has_cloth = False
                        if cloth_el is not None:
                            has_cloth = _xml_bool(cloth_el.find("ownsCloth"))
                        prop_mask = _xml_int(draw_item.find("propMask"), "value", 1)
                        drawables.append(DrawableEntry(
                            drawable_id=draw_id,
                            texture_count=len(textures),
                            prop_mask=prop_mask,
                            num_alternatives=_xml_int(draw_item.find("numAlternatives"), "value", 0),
                            has_cloth=has_cloth,
                            textures=textures,
                            flags=prop_mask,
                        ))
                self.components.append(ComponentEntry(
                    name=comp_name,
                    component_id=comp_id,
                    drawables=drawables,
                ))

        # ---- compInfos → attach to matching drawables ------------------------
        comp_infos_root = root.find("compInfos")
        if comp_infos_root is not None:
            for ci_item in comp_infos_root.findall("Item"):
                ci = ComponentInfo(
                    # MetaXml uses pedXml_*; YMTEditor sidecars use hash_*
                    audio_id=_xml_text(ci_item, "pedXml_audioID", "hash_2FD08CEF", "none"),
                    audio_id2=_xml_text(ci_item, "pedXml_audioID2", "hash_FC507D28", ""),
                    expression_mods=_xml_expression_mods(
                        ci_item, "pedXml_expressionMods", "hash_07AE529D"
                    ),
                    flags=_xml_int(ci_item.find("flags"), "value", 0),
                    inclusions=(ci_item.findtext("inclusions") or "0").strip(),
                    exclusions=(ci_item.findtext("exclusions") or "0").strip(),
                    vfx_comps=_xml_text(ci_item, "pedXml_vfxComps", "hash_6032815C", "PV_COMP_HEAD"),
                    vfx_flags=_xml_int(ci_item.find("pedXml_flags") or ci_item.find("hash_7E103C8B"), "value", 0),
                    comp_idx=_xml_int(ci_item.find("pedXml_compIdx") or ci_item.find("hash_D12F579D"), "value", 0),
                    drawbl_idx=_xml_int(ci_item.find("pedXml_drawblIdx") or ci_item.find("hash_FA1F27BF"), "value", 0),
                )
                # Attach to the matching DrawableEntry
                for ce in self.components:
                    if ce.component_id == ci.comp_idx:
                        if ci.drawbl_idx < len(ce.drawables):
                            ce.drawables[ci.drawbl_idx].comp_info = ci
                        break

        # ---- propInfo --------------------------------------------------------
        prop_info = root.find("propInfo")
        if prop_info is not None:
            meta_root = prop_info.find("aPropMetaData")
            prop_groups: dict[int, list[PropDrawable]] = {}
            if meta_root is not None:
                for draw_idx, item in enumerate(meta_root.findall("Item")):
                    anchor_id = _xml_int(item.find("anchorId"), "value", 0)
                    prop_id = _xml_int(item.find("propId"), "value", 0)
                    audio_id = (item.findtext("audioId") or "none").strip()
                    exp_raw = (item.findtext("expressionMods") or "0 0 0 0 0").strip()
                    expression_mods = exp_raw.split() if exp_raw else ["0"] * 5
                    render_flags = (item.findtext("renderFlags") or "").strip()
                    prop_flags = _xml_int(item.find("propFlags"), "value", 0)
                    flags = _xml_int(item.find("flags"), "value", 0)
                    hash_val = _xml_int(item.find("hash_AC887A91"), "value", 0)
                    tex_root = item.find("texData")
                    prop_textures: list[PropTextureData] = []
                    if tex_root is not None:
                        for tex_item in tex_root.findall("Item"):
                            prop_textures.append(PropTextureData(
                                tex_id=_xml_int(tex_item.find("texId"), "value", 0),
                                inclusions=(tex_item.findtext("inclusions") or "0").strip(),
                                exclusions=(tex_item.findtext("exclusions") or "0").strip(),
                                inclusion_id=_xml_int(tex_item.find("inclusionId"), "value", 0),
                                exclusion_id=_xml_int(tex_item.find("exclusionId"), "value", 0),
                                distribution=_xml_int(tex_item.find("distribution"), "value", 255),
                            ))
                    prop_groups.setdefault(anchor_id, []).append(PropDrawable(
                        prop_index=len(prop_groups.get(anchor_id, [])),
                        anchor_id=anchor_id,
                        prop_id=prop_id,
                        audio_id=audio_id,
                        expression_mods=expression_mods,
                        render_flags=render_flags,
                        prop_flags=prop_flags,
                        flags=flags,
                        hash_AC887A91=hash_val,
                        textures=prop_textures,
                    ))
            for anchor_id, pdrawables in sorted(prop_groups.items()):
                self.props.append(PropEntry(
                    name=PROP_NAMES.get(anchor_id, f"Prop_{anchor_id}"),
                    prop_id=anchor_id,
                    items=pdrawables,
                ))

    # ── Saving ─────────────────────────────────────────────────────────────────

    def save(self, path: Path | None = None) -> None:
        _init()
        _require()
        from CodeWalker.GameFiles import XmlMeta, ResourceBuilder  # type: ignore
        from System.Xml import XmlDocument  # type: ignore

        output_path = path or self.path
        xml_str = self._build_xml()
        doc = XmlDocument()
        doc.LoadXml(xml_str)
        meta = XmlMeta.GetMeta(doc)
        raw = bytes(ResourceBuilder.Build(meta, 2))
        output_path.write_bytes(raw)

    def save_xml(self, path: Path) -> None:
        """Export as human-readable XML (equivalent to a sidecar .ymt.xml)."""
        path.write_text(self._build_xml(), encoding="utf-8")

    def _build_xml(self) -> str:
        """Regenerate a CPedVariationInfo XML string from in-memory data."""
        lines: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
        name_attr = f' name="{self.dlc_name}"' if self.dlc_name else ""
        lines.append(f"<CPedVariationInfo{name_attr}>")

        def b(v: bool) -> str:
            return "true" if v else "false"

        lines.append(f' <bHasTexVariations value="{b(self.has_tex_variations)}" />')
        lines.append(f' <bHasDrawblVariations value="{b(self.has_drawbl_variations)}" />')
        lines.append(f' <bHasLowLODs value="{b(self.has_low_lods)}" />')
        lines.append(f' <bIsSuperLOD value="{b(self.is_super_lod)}" />')
        lines.append(f' <availComp>{" ".join(str(v) for v in self.avail_comp)}</availComp>')

        # aComponentData3
        lines.append(' <aComponentData3 itemType="CPVComponentData">')
        for ce in self.components:
            num_avail_tex = sum(len(d.textures) for d in ce.drawables)
            lines.append("  <Item>")
            lines.append(f'   <numAvailTex value="{num_avail_tex}" />')
            lines.append('   <aDrawblData3 itemType="CPVDrawblData">')
            for dd in ce.drawables:
                lines.append("    <Item>")
                lines.append(f'     <propMask value="{dd.prop_mask}" />')
                lines.append(f'     <numAlternatives value="{dd.num_alternatives}" />')
                lines.append('     <aTexData itemType="CPVTextureData">')
                for tex in dd.textures:
                    lines.append("      <Item>")
                    lines.append(f'       <texId value="{tex.tex_id}" />')
                    lines.append(f'       <distribution value="{tex.distribution}" />')
                    lines.append("      </Item>")
                lines.append("     </aTexData>")
                lines.append("     <clothData>")
                lines.append(f'      <ownsCloth value="{b(dd.has_cloth)}" />')
                lines.append("     </clothData>")
                lines.append("    </Item>")
            lines.append("   </aDrawblData3>")
            lines.append("  </Item>")
        lines.append(" </aComponentData3>")

        lines.append(' <aSelectionSets itemType="CPedSelectionSet" />')

        # compInfos
        lines.append(' <compInfos itemType="CComponentInfo">')
        for ce in self.components:
            for dd in ce.drawables:
                ci = dd.comp_info or ComponentInfo(comp_idx=ce.component_id, drawbl_idx=dd.drawable_id)
                exp = " ".join(ci.expression_mods) if ci.expression_mods else "0 0 0 0 0"
                lines.append("  <Item>")
                lines.append(f"   <pedXml_audioID>{ci.audio_id}</pedXml_audioID>")
                lines.append(f"   <pedXml_audioID2>{ci.audio_id2}</pedXml_audioID2>")
                lines.append(f"   <pedXml_expressionMods>{exp}</pedXml_expressionMods>")
                lines.append(f'   <flags value="{ci.flags}" />')
                lines.append(f"   <inclusions>{ci.inclusions}</inclusions>")
                lines.append(f"   <exclusions>{ci.exclusions}</exclusions>")
                lines.append(f"   <pedXml_vfxComps>{ci.vfx_comps}</pedXml_vfxComps>")
                lines.append(f'   <pedXml_flags value="{ci.vfx_flags}" />')
                lines.append(f'   <pedXml_compIdx value="{ce.component_id}" />')
                lines.append(f'   <pedXml_drawblIdx value="{dd.drawable_id}" />')
                lines.append("  </Item>")
        lines.append(" </compInfos>")

        # propInfo
        total_props = sum(len(pe.items) for pe in self.props)
        lines.append(" <propInfo>")
        lines.append(f'  <numAvailProps value="{total_props % 256}" />')
        lines.append('  <aPropMetaData itemType="CPedPropMetaData">')
        for pe in self.props:
            for pd in pe.items:
                exp = " ".join(pd.expression_mods) if pd.expression_mods else "0 0 0 0 0"
                lines.append("   <Item>")
                lines.append(f"    <audioId>{pd.audio_id}</audioId>")
                lines.append(f"    <expressionMods>{exp}</expressionMods>")
                lines.append('    <texData itemType="CPedPropTexData">')
                for pt in pd.textures:
                    lines.append("     <Item>")
                    lines.append(f"      <inclusions>{pt.inclusions}</inclusions>")
                    lines.append(f"      <exclusions>{pt.exclusions}</exclusions>")
                    lines.append(f'      <texId value="{pt.tex_id}" />')
                    lines.append(f'      <inclusionId value="{pt.inclusion_id}" />')
                    lines.append(f'      <exclusionId value="{pt.exclusion_id}" />')
                    lines.append(f'      <distribution value="{pt.distribution}" />')
                    lines.append("     </Item>")
                lines.append("    </texData>")
                lines.append(f"    <renderFlags>{pd.render_flags}</renderFlags>")
                lines.append(f'    <propFlags value="{pd.prop_flags}" />')
                lines.append(f'    <flags value="{pd.flags}" />')
                lines.append(f'    <anchorId value="{pd.anchor_id}" />')
                lines.append(f'    <propId value="{pd.prop_id}" />')
                lines.append(f'    <hash_AC887A91 value="{pd.hash_AC887A91}" />')
                lines.append("   </Item>")
        lines.append("  </aPropMetaData>")
        lines.append('  <aAnchors itemType="CAnchorProps" />')
        lines.append(" </propInfo>")

        lines.append(f" <dlcName>{self.dlc_name}</dlcName>")
        lines.append("</CPedVariationInfo>")
        return "\n".join(lines)


# ── XML helpers ────────────────────────────────────────────────────────────────

def _xml_int(element: ET.Element | None, attr: str, default: int = 0) -> int:
    if element is None:
        return default
    value = element.get(attr)
    if value is None:
        value = (element.text or "").strip()
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _xml_bool(element: ET.Element | None) -> bool:
    if element is None:
        return False
    value = element.get("value", "")
    return value.lower() == "true"


def _xml_text(parent: ET.Element, *tag_names: str, default: str = "") -> str:
    """Try multiple tag names, return first found text."""
    for tag in tag_names:
        el = parent.find(tag)
        if el is not None:
            return (el.text or default).strip()
    return default


def _xml_expression_mods(parent: ET.Element, *tag_names: str) -> list[str]:
    for tag in tag_names:
        el = parent.find(tag)
        if el is not None and el.text:
            parts = el.text.strip().split()
            if len(parts) == 5:
                return parts
            if len(parts) > 0:
                return parts[:5] + ["0"] * (5 - len(parts))
    return ["0", "0", "0", "0", "0"]


def _parse_avail_comp(element: ET.Element | None) -> list[int]:
    """Parse the availComp element into a list of 12 byte values."""
    if element is None or not element.text:
        return [255] * 12
    raw = element.text.strip()
    result: list[int] = []
    if " " in raw:
        # Standard space-separated decimal format
        parts = raw.split()
        for p in parts:
            try:
                result.append(int(p))
            except ValueError:
                result.append(255)
    elif len(raw) > 4:
        # "Metatool" hex format: 2-char pairs where char[1] is the nibble value
        for i in range(0, len(raw), 2):
            pair = raw[i:i+2]
            if len(pair) < 2:
                break
            c = pair[1].upper()
            if c == "F":
                result.append(255)
            else:
                try:
                    result.append(int(c, 16))
                except ValueError:
                    result.append(255)
    else:
        try:
            result = [int(x) for x in raw.split()]
        except ValueError:
            return [255] * 12
    # Pad / clamp to exactly 12
    while len(result) < 12:
        result.append(255)
    return result[:12]


def save_ymt_resource_from_xml(xml_text: str, output_path: Path, version: int = 2) -> None:
    """Build a binary GTA resource (.ymt) from XML text and write it to disk."""
    _init()
    _require()
    from CodeWalker.GameFiles import XmlMeta, ResourceBuilder  # type: ignore
    from System.Xml import XmlDocument  # type: ignore

    doc = XmlDocument()
    doc.LoadXml(xml_text)
    meta = XmlMeta.GetMeta(doc)
    raw = bytes(ResourceBuilder.Build(meta, version))
    output_path.write_bytes(raw)
