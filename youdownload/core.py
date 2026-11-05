"""Download engine. `Api` is exposed to the app window's JavaScript as window.pywebview.api."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import yt_dlp

from . import paths, updater

AUDIO_BITRATES = ("320", "256", "192", "128")
YOUTUBE_RE = re.compile(
    r"^(https?://)?((www|m|music)\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/", re.I
)


class Cancelled(Exception):
    pass


def clean_error(e: BaseException) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "").strip()
    if "Sign in to confirm" in msg:
        return "YouTube wants to confirm you're not a bot. Try again in a little while."
    if "Private video" in msg:
        return "This video is private."
    if "Video unavailable" in msg:
        return "This video is unavailable."
    if "is not a valid URL" in msg or "Unsupported URL" in msg:
        return "That doesn't look like a YouTube video link."
    return msg[:400] or "Something went wrong."


def label_for_height(h: int) -> str:
    names = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}
    return f"{h}p" + (f" ({names[h]})" if h in names else "")


class Api:
    def __init__(self):
        self._window = None
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._settings_file = os.path.join(paths.data_dir(), "settings.json")
        self._settings = self._load_settings()
        self._ffmpeg = paths.ffmpeg_path()
        self._deno = paths.deno_path()
        self._update_note = ""
        threading.Thread(target=self._auto_update, daemon=True).start()

    # ---- settings -------------------------------------------------------

    def _load_settings(self) -> dict:
        try:
            with open(self._settings_file) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}

    def _save_settings(self):
        try:
            with open(self._settings_file, "w") as f:
                json.dump(self._settings, f)
        except OSError:
            pass

    def _folder(self) -> str:
        folder = self._settings.get("folder")
        return folder if folder and os.path.isdir(folder) else paths.default_download_dir()

    def _auto_update(self):
        try:
            res = updater.check_and_update(yt_dlp.version.__version__)
            if res["updated"]:
                self._update_note = (
                    f"Downloader updated to {res['version']}. Restart YouDownload to use it."
                )
        except Exception:  # noqa: BLE001 - offline, rate limited, etc.
            pass

    # ---- calls from the page --------------------------------------------

    def get_state(self) -> dict:
        return {
            "folder": self._folder(),
            "ytdlp": yt_dlp.version.__version__,
            "ffmpeg": bool(self._ffmpeg),
            "deno": bool(self._deno),
            "update_note": self._update_note,
            "bitrates": list(AUDIO_BITRATES),
        }

    def choose_folder(self) -> str:
        import webview

        if not self._window:
            return self._folder()
        result = self._window.create_file_dialog(
            webview.FileDialog.FOLDER, directory=self._folder()
        )
        if result:
            self._settings["folder"] = result[0] if isinstance(result, (list, tuple)) else result
            self._save_settings()
        return self._folder()

    def open_folder(self, path: str | None = None):
        """Open the download folder, selecting the file if one is given."""
        target = path if path and os.path.exists(path) else self._folder()
        try:
            if sys.platform == "win32":
                if os.path.isfile(target):
                    subprocess.Popen(["explorer", "/select,", os.path.normpath(target)])
                else:
                    os.startfile(target)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", target] if os.path.isfile(target) else ["open", target])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(target) if os.path.isfile(target) else target])
        except OSError:
            pass

    def get_info(self, url: str) -> dict:
        url = (url or "").strip()
        if not YOUTUBE_RE.match(url):
            return {"error": "Please paste a YouTube video link."}
        try:
            with yt_dlp.YoutubeDL(self._base_opts()) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001
            return {"error": clean_error(e)}

        heights = sorted(
            {
                int(f["height"])
                for f in info.get("formats") or []
                if f.get("height") and f.get("vcodec") not in (None, "none")
            },
            reverse=True,
        )
        return {
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "url": info.get("webpage_url") or url,
            "qualities": [{"height": h, "label": label_for_height(h)} for h in heights],
        }

    def start_download(self, url: str, kind: str, value: str) -> dict:
        if kind not in ("video", "audio"):
            return {"error": "Unknown download type."}
        if not self._ffmpeg:
            return {"error": "ffmpeg is missing, so this download can't be processed."}
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "status": "starting",
                "progress": 0.0,
                "message": "Starting...",
                "file": None,
                "cancel": False,
            }
        threading.Thread(
            target=self._run, args=(job_id, url, kind, str(value)), daemon=True
        ).start()
        return {"job_id": job_id}

    def progress(self, job_id: str) -> dict:
        job = self._jobs.get(job_id)
        if not job:
            return {"status": "error", "message": "Unknown download."}
        return {
            "status": job["status"],
            "progress": round(job["progress"], 1),
            "message": job["message"],
            "file": job["file"],
            "filename": os.path.basename(job["file"]) if job["file"] else None,
        }

    def cancel(self, job_id: str):
        job = self._jobs.get(job_id)
        if job:
            job["cancel"] = True

    # ---- the actual work ------------------------------------------------

    def _base_opts(self) -> dict:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "remote_components": ["ejs:github"],
        }
        if self._ffmpeg:
            opts["ffmpeg_location"] = self._ffmpeg
        if self._deno:
            opts["js_runtimes"] = {"deno": {"path": self._deno}}
        return opts

    def _update(self, job_id, **fields):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def _build_opts(self, job_id, kind, value) -> dict:
        state = {"stream": 0, "streams": 2 if kind == "video" else 1}
        job = self._jobs[job_id]

        def hook(d):
            if job["cancel"]:
                raise Cancelled()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                frac = (d.get("downloaded_bytes") or 0) / total if total else 0
                overall = (state["stream"] + frac) / state["streams"] * 90
                speed = (d.get("_speed_str") or "").strip()
                eta = (d.get("_eta_str") or "").strip()
                extra = " · ".join(x for x in (speed, f"{eta} left" if eta and eta != "Unknown" else "") if x)
                self._update(
                    job_id,
                    status="downloading",
                    progress=min(overall, 90),
                    message=f"Downloading... {extra}".strip(),
                )
            elif d["status"] == "finished":
                state["stream"] = min(state["stream"] + 1, state["streams"])

        def post_hook(d):
            if d["status"] == "started":
                msg = "Converting to MP3..." if kind == "audio" else "Merging video and audio..."
                self._update(job_id, status="processing", progress=93, message=msg)

        opts = self._base_opts()
        opts.update(
            {
                "paths": {"home": self._folder(), "temp": tempfile.gettempdir()},
                # Include the resolution so different qualities don't overwrite each other.
                "outtmpl": "%(title).150B (%(height)sp).%(ext)s" if kind == "video" else "%(title).150B.%(ext)s",
                "windowsfilenames": True,
                "progress_hooks": [hook],
                "postprocessor_hooks": [post_hook],
            }
        )
        if kind == "video":
            h = int(value) if value.isdigit() else 100000
            # Prefer H.264 MP4 + M4A audio so the file plays everywhere (Windows, phones, TVs).
            opts["format"] = (
                f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/"
                f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/"
                f"bv*[height<={h}]+ba/b[height<={h}]/b"
            )
            opts["merge_output_format"] = "mp4"
            opts["final_ext"] = "mp4"
        else:
            bitrate = value if value in AUDIO_BITRATES else "192"
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
                {"key": "FFmpegMetadata"},
            ]
            opts["final_ext"] = "mp3"
        return opts

    def _run(self, job_id, url, kind, value):
        try:
            with yt_dlp.YoutubeDL(self._build_opts(job_id, kind, value)) as ydl:
                info = ydl.extract_info(url, download=True)
            downloads = info.get("requested_downloads") or []
            path = downloads[0].get("filepath") if downloads else None
            if not path or not os.path.exists(path):
                raise RuntimeError("The download finished but the file wasn't found.")
            self._update(job_id, status="done", progress=100, message="Done!", file=path)
        except Exception as e:  # noqa: BLE001
            if self._jobs[job_id]["cancel"] or isinstance(e, Cancelled) or "Cancelled" in repr(e):
                self._update(job_id, status="cancelled", progress=0, message="Cancelled.")
            else:
                self._update(job_id, status="error", message=clean_error(e))
        finally:
            # Forget finished jobs after a while.
            t = threading.Timer(600, lambda: self._jobs.pop(job_id, None))
            t.daemon = True
            t.start()
