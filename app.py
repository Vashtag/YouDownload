"""YouDownload: a small local web app for downloading YouTube videos or MP3 audio.

Run with:  python app.py   then open http://127.0.0.1:5000
"""

import os
import re
import shutil
import tempfile
import threading
import time
import uuid

from flask import Flask, abort, jsonify, render_template, request, send_file
import yt_dlp

app = Flask(__name__)

# Downloaded files live here until they are fetched or expire.
DOWNLOAD_ROOT = os.path.join(tempfile.gettempdir(), "youdownload")
JOB_TTL_SECONDS = 60 * 60  # clean up finished jobs after an hour
AUDIO_BITRATES = ("128", "192", "256", "320")

os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()

YOUTUBE_RE = re.compile(
    r"^(https?://)?((www|m|music)\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/", re.I
)


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_RE.match(url.strip()))


def base_opts() -> dict:
    return {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,  # a watch?v=...&list=... link downloads just the one video
    }


def extract_qualities(info: dict) -> list:
    """Return the distinct video heights available, highest first."""
    heights = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        if h and f.get("vcodec") not in (None, "none"):
            heights.add(int(h))
    return sorted(heights, reverse=True)


def label_for_height(h: int) -> str:
    names = {4320: "8K", 2160: "4K", 1440: "2K"}
    return f"{h}p" + (f" ({names[h]})" if h in names else "")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html", bitrates=AUDIO_BITRATES)


@app.post("/api/info")
def info():
    url = (request.get_json(silent=True) or {}).get("url", "").strip()
    if not url or not is_youtube_url(url):
        return jsonify(error="Please enter a valid YouTube link."), 400
    try:
        with yt_dlp.YoutubeDL(base_opts()) as ydl:
            data = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return jsonify(error=clean_error(e)), 400

    heights = extract_qualities(data)
    return jsonify(
        title=data.get("title"),
        uploader=data.get("uploader"),
        duration=data.get("duration"),
        thumbnail=data.get("thumbnail"),
        url=data.get("webpage_url") or url,
        qualities=[{"height": h, "label": label_for_height(h)} for h in heights],
        bitrates=list(AUDIO_BITRATES),
    )


@app.post("/api/download")
def start_download():
    body = request.get_json(silent=True) or {}
    url = body.get("url", "").strip()
    kind = body.get("kind")
    if not url or not is_youtube_url(url):
        return jsonify(error="Please enter a valid YouTube link."), 400
    if kind not in ("video", "audio"):
        return jsonify(error="Unknown download type."), 400

    height = None
    bitrate = None
    if kind == "video":
        try:
            height = int(body.get("height"))
        except (TypeError, ValueError):
            return jsonify(error="Pick a video quality."), 400
    else:
        bitrate = str(body.get("bitrate", "192"))
        if bitrate not in AUDIO_BITRATES:
            return jsonify(error="Pick an audio bitrate."), 400

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(DOWNLOAD_ROOT, job_id)
    os.makedirs(job_dir)
    with jobs_lock:
        jobs[job_id] = {
            "status": "queued",
            "progress": 0.0,
            "message": "Starting...",
            "dir": job_dir,
            "file": None,
            "created": time.time(),
        }

    threading.Thread(
        target=run_download, args=(job_id, url, kind, height, bitrate), daemon=True
    ).start()
    return jsonify(job_id=job_id)


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(
        status=job["status"],
        progress=round(job["progress"], 1),
        message=job["message"],
        filename=os.path.basename(job["file"]) if job["file"] else None,
    )


@app.get("/api/file/<job_id>")
def get_file(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job["file"]:
        abort(404)
    return send_file(job["file"], as_attachment=True, download_name=os.path.basename(job["file"]))


# ---------------------------------------------------------------------------
# Download worker
# ---------------------------------------------------------------------------


def update(job_id, **fields):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(fields)


def build_opts(job_id, job_dir, kind, height, bitrate) -> dict:
    # Video and audio are downloaded as separate streams, so the progress hook
    # fires once per stream. Track which stream we're on to keep the bar moving forward.
    state = {"stream": 0, "streams": 2 if kind == "video" else 1}

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = done / total if total else 0
            overall = (state["stream"] + frac) / state["streams"] * 90  # last 10% = processing
            speed = d.get("_speed_str", "").strip()
            update(
                job_id,
                status="downloading",
                progress=min(overall, 90),
                message=f"Downloading... {speed}".strip(),
            )
        elif d["status"] == "finished":
            state["stream"] = min(state["stream"] + 1, state["streams"])

    def post_hook(d):
        if d["status"] == "started":
            label = "Converting to MP3..." if kind == "audio" else "Merging video and audio..."
            update(job_id, status="processing", progress=92, message=label)

    opts = base_opts()
    opts.update(
        {
            "outtmpl": os.path.join(job_dir, "%(title).150B [%(id)s].%(ext)s"),
            "progress_hooks": [hook],
            "postprocessor_hooks": [post_hook],
            "restrictfilenames": False,
            "windowsfilenames": True,
        }
    )

    if kind == "video":
        # Prefer MP4/M4A so the result plays everywhere; fall back to anything at that height.
        opts["format"] = (
            f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={height}]+ba/"
            f"b[height<={height}]/b"
        )
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
            {"key": "FFmpegMetadata"},
        ]
    return opts


def run_download(job_id, url, kind, height, bitrate):
    job_dir = jobs[job_id]["dir"]
    try:
        with yt_dlp.YoutubeDL(build_opts(job_id, job_dir, kind, height, bitrate)) as ydl:
            ydl.extract_info(url, download=True)

        wanted = ".mp3" if kind == "audio" else ".mp4"
        files = [f for f in os.listdir(job_dir) if not f.endswith((".part", ".ytdl"))]
        files.sort(key=lambda f: (not f.endswith(wanted), f))
        if not files:
            raise RuntimeError("Download finished but no file was produced.")
        update(
            job_id,
            status="done",
            progress=100,
            message="Ready!",
            file=os.path.join(job_dir, files[0]),
        )
    except Exception as e:  # noqa: BLE001 - report any failure to the UI
        update(job_id, status="error", message=clean_error(e))


def clean_error(e: Exception) -> str:
    msg = str(e)
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)  # strip terminal colours
    msg = msg.replace("ERROR: ", "")
    return msg[:300] or "Something went wrong."


def cleanup_loop():
    while True:
        time.sleep(300)
        now = time.time()
        with jobs_lock:
            expired = [j for j, v in jobs.items() if now - v["created"] > JOB_TTL_SECONDS]
            for j in expired:
                shutil.rmtree(jobs[j]["dir"], ignore_errors=True)
                del jobs[j]


threading.Thread(target=cleanup_loop, daemon=True).start()


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        print("WARNING: ffmpeg was not found on PATH. MP3 conversion and HD video will not work.")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
