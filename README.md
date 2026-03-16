# FiveForge

A polished desktop toolkit for building and editing FiveM and GTA V resource assets.

## Why FiveForge
- Fast workflow for clothing packs with proper binary `.ymt` output.
- Dedicated editors for YTD, YMT, and META files.
- Resource Builder for turning loose files into deployable resource folders.
- Built-in Home/Help hub and multi-theme UI.
- Packaged for end users as `FiveForge.exe` (no manual Python install required).

## Modules
- Home: quick start, useful info, and in-app help.
- YTD Editor: inspect and edit texture dictionaries.
- YMT Editor: read/write binary YMT resources.
- META Editor: edit XML/meta files with highlighting.
- Clothing Builder: import drawables/textures, then export complete packs.
- Resource Builder: normalize structure and generate `fxmanifest.lua` entries.

## Build (Windows)
1. Open terminal in project root.
2. Run `build_exe.bat`.
3. Output is generated in `dist/FiveForge/`.

Result layout:
- `dist/FiveForge/FiveForge.exe`
- `dist/FiveForge/native/*.dll`
- other runtime dependencies bundled by PyInstaller

## Runtime Requirements
- End users: only the packaged app folder.
- Developers: Python 3.11+ and dependencies from `requirements.txt`.

## Update Checker
FiveForge checks `version.json` at startup. Keep that file updated in your GitHub repo:

- Repository: https://github.com/Orvlyn/FiveForge
- Version feed (raw): https://raw.githubusercontent.com/Orvlyn/FiveForge/main/version.json
- Icon (raw): https://raw.githubusercontent.com/Orvlyn/FiveForge/main/assets/fiveforge.ico

```json
{
  "version": "1.1.0",
  "url": "https://github.com/Orvlyn/FiveForge"
}
```

## License
This repository ships with a credit-required, non-commercial license in `Git/LICENSE.md`.

## Credits
- Built by Orvlyn.
- Thanks to @dexyfex for <a href="https://github.com/dexyfex/CodeWalker">Codewalker.Core</a>.
