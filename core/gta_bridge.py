"""
gta_bridge.py
-------------
Loads CodeWalker.Core.dll at runtime via pythonnet.

Place CodeWalker.Core.dll (and any dependency DLLs from its build output)
inside the  native/  directory at the project root.

Without this DLL the YTD and YMT editors will display an error message.
The Resource Builder and META Editor work without it.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

NATIVE_DIR = Path(__file__).parent.parent / "native"

_initialized: bool = False
_available: bool = False
_last_error: str | None = None


def initialize() -> bool:
    """Load the CodeWalker bridge. Safe to call multiple times."""
    global _initialized, _available, _last_error
    if _initialized:
        return _available
    _initialized = True

    dll_path = NATIVE_DIR / "CodeWalker.Core.dll"

    if not dll_path.exists():
        _last_error = f"Missing DLL: {dll_path}"
        logger.warning(
            "CodeWalker.Core.dll not found at '%s'. "
            "YTD/YMT editing will be unavailable. "
            "See native/README.md for setup instructions.",
            dll_path,
        )
        return False

    try:
        # Help CLR resolve dependent native DLLs from the same folder.
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(NATIVE_DIR.resolve()))
        sys.path.insert(0, str(NATIVE_DIR.resolve()))

        import clr  # type: ignore  # pythonnet

        clr.AddReference(str(dll_path.resolve()))
        _available = True
        _last_error = None
        logger.info("CodeWalker bridge initialised from '%s'.", dll_path)
    except ImportError:
        _last_error = (
            "pythonnet is not installed or failed to import. "
            f"Current Python version: {sys.version.split()[0]}"
        )
        logger.warning(
            "pythonnet is not installed. "
            "Run: pip install pythonnet"
        )
    except Exception as exc:
        _last_error = str(exc)
        logger.error("Failed to load CodeWalker bridge: %s", exc)

    return _available


def is_available() -> bool:
    """Return True if the bridge was loaded successfully."""
    return _available


def require() -> None:
    """Raise RuntimeError with a helpful message if the bridge is missing."""
    if not _available:
        py_ver = sys.version.split()[0]
        details = f"\n\nBridge error details:\n  {_last_error}" if _last_error else ""
        project_root = Path(__file__).parent.parent
        dev_python = project_root / ".venv312" / "Scripts" / "python.exe"
        exe_path = project_root / "dist" / "FiveForge" / "FiveForge.exe"
        raise RuntimeError(
            "CodeWalker bridge is not available for this feature.\n\n"
            "You are probably launching the app with the wrong Python interpreter.\n\n"
            "Use one of these launch paths instead:\n"
            f"  Dev: {dev_python} {project_root / 'main.py'}\n"
            f"  EXE: {exe_path}\n\n"
            "Steps to set it up:\n"
            "  1. Clone https://github.com/dexyfex/CodeWalker\n"
            "  2. Build the CodeWalker.Core project in Release mode\n"
            "  3. Copy CodeWalker.Core.dll (and its dependencies) to:\n"
            f"     {NATIVE_DIR}\n"
            "  4. Use Python 3.12 or 3.13 with pythonnet 3.x\n"
            f"     (current Python: {py_ver})\n\n"
            "Tip: Python 3.14 currently has limited pythonnet wheel support on Windows."
            f"{details}\n\n"
            "The Resource Builder and META Editor work without this bridge."
        )
