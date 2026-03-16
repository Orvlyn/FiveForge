# FiveForge v1.1.0

## Highlights
- Added project-name sanitization for Clothing Builder output.
- Added Home module with quick-start guidance and built-in Help dialog.
- Added selectable UI themes (Forge Dark, Forge Light, Forge Ocean).
- Added application icon plumbing and executable icon in PyInstaller build.
- Added startup version checker using remote `version.json`.
- Updated META Editor file-open dialog to default to `All Files (*)`.

## Clothing Builder
- Project names now normalize spaces to underscores so generated folder/file/meta names are safe and consistent.
- Existing workflow for gender YMT and creaturemetadata generation remains intact.

## Packaging
- Added `build_exe.bat` for one-command EXE builds.
- Updated `build.ps1` to auto-copy `native` dependencies into `dist/FiveForge/native`.
- Updated `build.spec` to use `assets/fiveforge.ico` as application icon.

## Notes
- End users do not need Python installed when running packaged builds.
- Keep native CodeWalker dependencies inside `native/` to preserve YTD/YMT functionality.

## Upgrade Advice
- Replace older local builds with the full `dist/FiveForge` folder from this release.
- If you publish GitHub releases, update your hosted `version.json` on each release.
