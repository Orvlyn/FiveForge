from __future__ import annotations

from pathlib import Path

THEMES: dict[str, tuple[str, str]] = {
    "forge_dark": ("Forge Dark", "dark_theme.qss"),
    "forge_ocean": ("Forge Ocean", "ocean_theme.qss"),
    "forge_graphite": ("Forge Graphite", "graphite_theme.qss"),
    "forge_ember": ("Forge Ember", "ember_theme.qss"),
    "forge_forest": ("Forge Forest", "forest_theme.qss"),
    "forge_light": ("Forge Light", "light_theme.qss"),
}



def theme_choices() -> list[tuple[str, str]]:
    return [(theme_id, data[0]) for theme_id, data in THEMES.items()]



def resolve_theme_file(theme_id: str) -> str:
    if theme_id in THEMES:
        return THEMES[theme_id][1]
    return THEMES["forge_dark"][1]



def load_theme_qss(base_dir: Path, theme_id: str) -> str:
    styles_dir = base_dir / "ui" / "styles"
    theme_path = styles_dir / resolve_theme_file(theme_id)
    if theme_path.exists():
        return theme_path.read_text(encoding="utf-8")

    fallback = styles_dir / THEMES["forge_dark"][1]
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    return ""
