# YouDownload

A desktop app for downloading YouTube videos. Paste a link and choose:

- **Video (MP4)** in any quality the video offers (144p up to 4K/8K)
- **Audio (MP3)** at 128, 192, 256 or 320 kbps

**Download page:** https://vashtag.github.io/YouDownload

It runs entirely on your computer: no server, no account. The app bundles everything it needs:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) does the downloading, and updates itself in the background (YouTube changes often)
- [ffmpeg](https://ffmpeg.org/) (via `imageio-ffmpeg`) merges video and audio and converts to MP3
- [Deno](https://deno.com/), the JavaScript runtime yt-dlp needs to handle YouTube
- [pywebview](https://pywebview.flowrl.com/) shows the interface (`youdownload/ui/index.html`) in a native window

## Project layout

| Path | What it is |
| --- | --- |
| `youdownload/main.py` | Opens the app window (also `--selftest <file>` for CI) |
| `youdownload/core.py` | Download engine, called from the window's JavaScript |
| `youdownload/updater.py` | Keeps yt-dlp up to date without rebuilding the app |
| `youdownload/paths.py` | Locates bundled tools and the user's folders |
| `youdownload/ui/index.html` | The app's interface |
| `build.py` | Builds the app with PyInstaller for the current OS |
| `index.html` | The GitHub Pages download page |
| `.github/workflows/build.yml` | Builds Windows and macOS apps on every push; publishes them on `v*` tags |

## Run from source

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

You also need [Deno](https://docs.deno.com/runtime/getting_started/installation/) on your PATH when running from source, or run `python build.py` once, which downloads it into `vendor/`. The built app includes it.

## Build the app yourself

```bash
pip install -r requirements.txt pyinstaller
python build.py
```

This creates `dist/YouDownload.exe` on Windows or `dist/YouDownload.app` on macOS. PyInstaller can only build for the OS it runs on, which is why GitHub Actions builds both.

## Publishing a release

1. Push a tag starting with `v` (for example `v1.0.1`), or bump `VERSION` and put `[release]` in the commit message.
2. GitHub Actions builds both apps and attaches `YouDownload-Windows.exe` and `YouDownload-macOS.zip` to a new release.
3. The download page always links to the latest release.

To publish the download page: **Settings > Pages**, source "Deploy from a branch", branch `main`, folder `/ (root)`.

## Note

The app isn't code-signed, so Windows SmartScreen and macOS Gatekeeper show a warning the first time. Only download videos you own or have permission to download, and respect YouTube's Terms of Service and copyright law.
