"""
ytd_service.py
--------------
Service layer for reading and writing GTA V texture dictionaries (.ytd).

Depends on CodeWalker.Core.dll via gta_bridge.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.gta_bridge import initialize as _init, require as _require

logger = logging.getLogger(__name__)


@dataclass
class TextureEntry:
    name: str
    width: int
    height: int
    fmt: str
    mip_levels: int
    dds_data: bytes
    index: int
    native_texture: object = field(repr=False, compare=False, default=None)


@dataclass
class YTDFile:
    path: Path
    textures: list[TextureEntry] = field(default_factory=list)
    _native: object = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: str | Path) -> "YTDFile":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"YTD file not found: {path}")

        _init()
        _require()

        return cls._load_via_codewalker(path)

    @classmethod
    def _load_via_codewalker(cls, path: Path) -> "YTDFile":
        from CodeWalker.GameFiles import YtdFile as _CWYtd  # type: ignore
        from System import Array, Byte  # type: ignore

        cw = _CWYtd()
        cw.Load(Array[Byte](path.read_bytes()))
        cw.Name = path.name

        instance = cls(path=path, _native=cw)
        instance._refresh_texture_cache()
        return instance

    def _refresh_texture_cache(self) -> None:
        from CodeWalker.Utils import DDSIO  # type: ignore

        self.textures.clear()
        td = self._native.TextureDict  # type: ignore[union-attr]
        if td is None or td.Textures is None:
            logger.warning("YTD has no texture dictionary: %s", self.path)
            return

        for i, tex in enumerate(td.Textures.data_items):
            try:
                raw_dds = bytes(DDSIO.GetDDSFile(tex)) if tex is not None else b""
                self.textures.append(TextureEntry(
                    name=str(tex.Name) if tex.Name else f"texture_{i}",
                    width=int(tex.Width),
                    height=int(tex.Height),
                    fmt=str(tex.Format),
                    mip_levels=int(tex.Levels) if hasattr(tex, "Levels") else 1,
                    dds_data=raw_dds,
                    index=i,
                    native_texture=tex,
                ))
            except Exception as exc:
                logger.error("Failed to read texture %d: %s", i, exc)

    def export_texture(self, index: int, output_path: Path) -> None:
        _require()
        tex = self.textures[index]

        if output_path.suffix.lower() == ".dds":
            output_path.write_bytes(tex.dds_data)
        else:
            _dds_bytes_to_image(tex.dds_data, output_path)

    def replace_texture(self, index: int, image_path: Path) -> str:
        _require()
        from CodeWalker.Utils import DDSIO  # type: ignore

        suffix = image_path.suffix.lower()
        if suffix == ".dds":
            new_dds = image_path.read_bytes()
            backend = "dds-direct"
        elif suffix == ".png":
            new_dds, backend = _image_to_dds_with_backend(image_path)
        else:
            raise ValueError(f"Unsupported image format: {suffix}")

        td = self._native.TextureDict  # type: ignore[union-attr]
        current = td.Textures.data_items[index]
        new_tex = DDSIO.GetTexture(new_dds)
        new_tex.Name = current.Name
        new_tex.NameHash = current.NameHash
        new_tex.Usage = current.Usage
        new_tex.UsageFlags = current.UsageFlags
        new_tex.Unknown_32h = current.Unknown_32h

        textures = [tex for tex in td.Textures.data_items if tex is not current]
        textures.append(new_tex)
        td.BuildFromTextureList(textures)
        self._refresh_texture_cache()
        return backend

    def save(self, path: Path | None = None) -> None:
        _require()
        output_path = path or self.path
        output_path.write_bytes(bytes(self._native.Save()))  # type: ignore[union-attr]


def _dds_bytes_to_image(dds_data: bytes, output_path: Path) -> None:
    """Convert raw DDS bytes to a viewable image format using Pillow."""
    from PIL import Image  # type: ignore

    try:
        with Image.open(io.BytesIO(dds_data)) as src:
            rgba = src.convert("RGBA")
            rgba.save(str(output_path))
        return
    except Exception as exc:
        logger.debug("Pillow DDS read failed (%s), trying temp-file fallback", exc)

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".dds", delete=False) as tmp:
        tmp.write(dds_data)
        tmp_path = Path(tmp.name)
    try:
        with Image.open(str(tmp_path)) as src:
            rgba = src.convert("RGBA")
            rgba.save(str(output_path))
    finally:
        tmp_path.unlink(missing_ok=True)


def dds_bytes_to_qimage(dds_data: bytes) -> Optional["QImage"]:  # type: ignore[name-defined]
    """Convert raw DDS bytes to a QImage for UI preview. Returns None on failure."""
    try:
        from PIL import Image  # type: ignore
        from PySide6.QtGui import QImage

        with Image.open(io.BytesIO(dds_data)) as src:
            rgba = src.convert("RGBA")
            data = rgba.tobytes("raw", "RGBA")
            qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
            # Detach from temporary Python buffer to avoid lifetime issues.
            return qimg.copy()
    except Exception as exc:
        logger.debug("DDS preview conversion failed: %s", exc)
        return None


def _image_to_dds_with_backend(image_path: Path) -> tuple[bytes, str]:
    """Convert PNG to DDS bytes and report backend used."""
    # Try Pillow first. Some builds can write DDS directly.
    try:
        from PIL import Image  # type: ignore
        with Image.open(str(image_path)).convert("RGBA") as img:
            buf = io.BytesIO()
            img.save(buf, format="DDS")
            data = buf.getvalue()
            if data:
                return data, "Pillow"
    except Exception:
        pass

    # Fallback to Wand / ImageMagick if Pillow DDS writing is unavailable.
    try:
        from wand.image import Image as WandImage  # type: ignore
        with WandImage(filename=str(image_path)) as img:
            img.format = "dds"
            return img.make_blob(), "Wand"
    except ImportError:
        pass

    raise RuntimeError(
        "PNG to DDS conversion requires either Pillow DDS-save support or the 'Wand' library (ImageMagick backend).\n"
        "Install ImageMagick: https://imagemagick.org\n"
        "Then run: pip install Wand\n\n"
        "Alternatively, convert your texture to .dds first using a tool like\n"
        "Paint.NET (with DDS plugin) or GIMP."
    )


def _image_to_dds(image_path: Path) -> bytes:
    data, _backend = _image_to_dds_with_backend(image_path)
    return data


def convert_png_to_dds(input_png: Path, output_dds: Path) -> str:
    """Convert a PNG file to DDS on disk. Returns backend name used."""
    if input_png.suffix.lower() != ".png":
        raise ValueError("Input must be a .png file")
    data, backend = _image_to_dds_with_backend(input_png)
    output_dds.write_bytes(data)
    return backend
