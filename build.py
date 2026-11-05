"""Build YouDownload into a single app for this computer's OS.

    pip install -r requirements.txt pyinstaller
    python build.py

Output: dist/YouDownload.exe (Windows), dist/YouDownload.app (macOS), dist/YouDownload (Linux).
"""

from __future__ import annotations

import io
import os
import platform
import stat
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(ROOT, "vendor")


def deno_target() -> str:
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "win32":
        return f"deno-{arch}-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return f"deno-{arch}-apple-darwin.zip"
    return f"deno-{arch}-unknown-linux-gnu.zip"


def fetch_deno() -> str:
    """Download Deno (the JavaScript runtime yt-dlp needs for YouTube) into vendor/."""
    exe = "deno.exe" if sys.platform == "win32" else "deno"
    dest = os.path.join(VENDOR, exe)
    if os.path.exists(dest):
        return dest
    os.makedirs(VENDOR, exist_ok=True)
    url = f"https://github.com/denoland/deno/releases/latest/download/{deno_target()}"
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extract(exe, VENDOR)
    if sys.platform != "win32":
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dest


def main():
    deno = fetch_deno()
    sep = os.pathsep
    args = [
        sys.executable, "-m", "PyInstaller", "run.py",
        "--name", "YouDownload",
        # macOS gets a normal .app folder; Windows/Linux get a single file.
        "--onedir" if sys.platform == "darwin" else "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data", f"youdownload/ui{sep}youdownload/ui",
        "--add-binary", f"{deno}{sep}vendor",
        "--collect-data", "imageio_ffmpeg",
        "--collect-all", "yt_dlp",
        "--collect-all", "yt_dlp_ejs",
        "--copy-metadata", "yt-dlp",
        "--hidden-import", "youdownload.core",
    ]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "io.github.vashtag.youdownload"]
    print(" ".join(args))
    subprocess.check_call(args, cwd=ROOT)


if __name__ == "__main__":
    main()
