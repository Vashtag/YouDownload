"""Keep yt-dlp up to date without rebuilding the app.

YouTube changes often and old yt-dlp versions stop working. yt-dlp publishes a
pure-Python zip build ("yt-dlp" in each GitHub release). We download the latest
one into the user's data folder and, on the next launch, import yt_dlp from that
zip instead of the copy bundled inside the app.

`activate()` must run before anything imports yt_dlp.
"""

from __future__ import annotations

import hashlib
import importlib.machinery
import json
import os
import re
import sys
import tempfile
import urllib.request
import zipfile

from .paths import data_dir

RELEASES = "https://github.com/yt-dlp/yt-dlp/releases"
ZIP_NAME = "yt-dlp.zip"
STATE_NAME = "yt-dlp-update.json"
USER_AGENT = "YouDownload-updater"


def _zip_path() -> str:
    return os.path.join(data_dir(), ZIP_NAME)


def _state_path() -> str:
    return os.path.join(data_dir(), STATE_NAME)


def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or ""))


class _ZipFirstFinder:
    """Meta-path finder that resolves `yt_dlp` from the downloaded zip.

    It sits in front of PyInstaller's frozen importer, so the newer zip wins
    over the bundled copy.
    """

    def __init__(self, zip_path: str):
        self.zip_path = zip_path

    def find_spec(self, name, path=None, target=None):
        if name == "yt_dlp":
            return importlib.machinery.PathFinder.find_spec(name, [self.zip_path])
        if name.startswith("yt_dlp."):
            return importlib.machinery.PathFinder.find_spec(name, path)
        return None


def _bundled_version() -> str:
    """Read the bundled yt-dlp version without importing the whole package."""
    try:
        from importlib.metadata import version

        return version("yt-dlp")
    except Exception:  # noqa: BLE001
        return ""


def _zip_version(zip_path: str) -> str:
    try:
        with zipfile.ZipFile(zip_path) as z:
            src = z.read("yt_dlp/version.py").decode()
        m = re.search(r"__version__\s*=\s*'([^']+)'", src)
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def activate() -> None:
    """Use the downloaded yt-dlp if it's newer than the bundled one."""
    zp = _zip_path()
    if not os.path.isfile(zp):
        return
    if _version_tuple(_zip_version(zp)) <= _version_tuple(_bundled_version()):
        return
    sys.meta_path.insert(0, _ZipFirstFinder(zp))


def _get(url: str, timeout: int = 30) -> urllib.request.addinfourl:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)


def _load_state() -> dict:
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def check_and_update(current_version: str) -> dict:
    """Download a newer yt-dlp if there is one. Takes effect on next launch.

    Uses only release files (no API, no rate limits): the checksum list tells us
    whether the latest build differs from what we last saw.
    Returns {"updated": bool, "version": str}.
    """
    base = f"{RELEASES}/latest/download"
    with _get(f"{base}/SHA2-256SUMS") as r:
        sums = r.read().decode()
    expected = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == "yt-dlp":
            expected = parts[0].lower()
    if not expected:
        raise RuntimeError("Checksum for yt-dlp not found")

    state = _load_state()
    if state.get("sha256") == expected:
        return {"updated": False, "version": current_version}

    fd, tmp = tempfile.mkstemp(dir=data_dir(), suffix=".part")
    try:
        h = hashlib.sha256()
        with os.fdopen(fd, "wb") as f, _get(f"{base}/yt-dlp", timeout=120) as r:
            while chunk := r.read(1 << 16):
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != expected:
            raise RuntimeError("Downloaded yt-dlp failed its checksum")
        new_version = _zip_version(tmp)
        if not new_version:
            raise RuntimeError("Downloaded yt-dlp isn't a valid build")

        have = max(_version_tuple(current_version), _version_tuple(_zip_version(_zip_path())))
        updated = _version_tuple(new_version) > have
        if updated:
            os.replace(tmp, _zip_path())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    with open(_state_path(), "w") as f:
        json.dump({"sha256": expected, "version": new_version}, f)
    return {"updated": updated, "version": new_version}
