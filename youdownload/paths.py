"""Where things live: bundled tools, user data, and the default download folder."""

from __future__ import annotations

import os
import shutil
import stat
import sys

APP_NAME = "YouDownload"
IS_WINDOWS = sys.platform == "win32"
EXE = ".exe" if IS_WINDOWS else ""


def bundle_dir() -> str:
    """Folder holding bundled files (PyInstaller's temp dir when frozen)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """Per-user folder for settings, cached tools and the updated yt-dlp."""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def default_download_dir() -> str:
    path = os.path.join(os.path.expanduser("~"), "Downloads")
    return path if os.path.isdir(path) else os.path.expanduser("~")


def _executable(path: str) -> str:
    """Make sure a bundled binary can be run (a one-file app may drop the x bit)."""
    if not IS_WINDOWS and not os.access(path, os.X_OK):
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def ffmpeg_path() -> str | None:
    try:
        import imageio_ffmpeg

        return _executable(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


def deno_path() -> str | None:
    bundled = os.path.join(bundle_dir(), "vendor", "deno" + EXE)
    if os.path.isfile(bundled):
        return _executable(bundled)
    return shutil.which("deno")
