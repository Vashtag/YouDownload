# YouDownload

A single-page web app for downloading YouTube videos. Paste a link and choose:

- **Video (MP4)** from 144p up to 4K, or "best available"
- **Audio (MP3)** at 64 to 320 kbps

**Live page:** https://vashtag.github.io/YouDownload

Everything is in [`index.html`](index.html): no build step, no install.

## How it works

Browsers can't download from YouTube directly (YouTube blocks cross-site requests), so the page sends the link to a [cobalt](https://github.com/imputnet/cobalt) server, which returns a download link for the chosen quality or MP3.

The first time you open the page, enter a cobalt server address (and API key, if it needs one) in **Settings**. It's saved in your browser only.

The public `api.cobalt.tools` server uses bot protection and isn't meant for other sites, so use either:

- **your own instance** ([guide](https://github.com/imputnet/cobalt/blob/main/docs/run-an-instance.md)). It must allow requests from other sites, for example with `CORS_WILDCARD=1`, or
- **an instance whose owner gave you access** (usually with an API key).

## Publishing on GitHub Pages

In the repo on GitHub go to **Settings > Pages**, set **Source** to "Deploy from a branch", choose `main` and `/ (root)`, and save.

## Note

Only download videos you own or have permission to download, and respect YouTube's Terms of Service and copyright law.
