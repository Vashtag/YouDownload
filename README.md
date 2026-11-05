# YouDownload

A small local web app for downloading YouTube videos. Paste a link and choose:

- **Video (MP4)** in any quality the video offers (144p up to 4K/8K)
- **Audio (MP3)** at 128, 192, 256 or 320 kbps

It runs on your own computer, using [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading and [ffmpeg](https://ffmpeg.org/) for merging and MP3 conversion.

## Requirements

- Python 3.9+
- ffmpeg on your PATH
  - macOS: `brew install ffmpeg`
  - Windows: `winget install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000.

## How it works

1. `POST /api/info` reads the video's title, thumbnail and available resolutions.
2. `POST /api/download` starts a background job (video at a chosen height, or MP3 at a chosen bitrate).
3. The page polls `GET /api/progress/<id>` to show a progress bar.
4. When it's done, `GET /api/file/<id>` sends the file to your browser.

Finished files are kept in your system temp folder and removed after an hour.

## Troubleshooting

YouTube changes often. If downloads start failing, update yt-dlp first:

```bash
pip install -U yt-dlp
```

## Note

Only download videos you own or have permission to download, and respect YouTube's Terms of Service and copyright law.
