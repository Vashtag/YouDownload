# YouDownload

A small local web app for downloading YouTube videos. Paste a link and choose:

- **Video (MP4)** in any quality the video offers (144p up to 4K/8K)
- **Audio (MP3)** at 128, 192, 256 or 320 kbps

**Website:** https://vashtag.github.io/YouDownload

The website is a static page on GitHub Pages. YouTube doesn't allow websites to download videos directly from the browser, so the page talks to a small helper (`app.py`) running on your computer. The helper uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading and [ffmpeg](https://ffmpeg.org/) for merging and MP3 conversion.

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

Keep it running, then open https://vashtag.github.io/YouDownload (or http://127.0.0.1:5000, which serves the same page). The page shows a green dot once it finds the helper.

If your browser asks whether the site may access devices on your local network, choose **Allow**. Chrome, Edge and Firefox work. Safari blocks https pages from reaching a local http server, so use http://127.0.0.1:5000 there.

## Publishing the page (GitHub Pages)

The page lives in `docs/`. In the repo on GitHub go to **Settings > Pages**, set **Source** to "Deploy from a branch", pick branch `main` and folder `/docs`, and save. It appears at https://vashtag.github.io/YouDownload after a minute.

If you host the page on another domain, allow it in the helper with `EXTRA_ORIGINS=https://your.domain python app.py`.

## How it works

The helper exposes a small API (CORS-enabled for the GitHub Pages site):

1. `GET /api/health` lets the page detect the helper.
2. `POST /api/info` reads the video's title, thumbnail and available resolutions.
3. `POST /api/download` starts a background job (video at a chosen height, or MP3 at a chosen bitrate).
4. The page polls `GET /api/progress/<id>` to show a progress bar.
5. When it's done, `GET /api/file/<id>` sends the file to your browser.

Finished files are kept in your system temp folder and removed after an hour.

## Troubleshooting

YouTube changes often. If downloads start failing, update yt-dlp first:

```bash
pip install -U yt-dlp
```

## Note

Only download videos you own or have permission to download, and respect YouTube's Terms of Service and copyright law.
