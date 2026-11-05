"""Start YouDownload: open the app window."""

from __future__ import annotations

import os
import sys


def selftest(out_path: str) -> int:
    """Check the bundled tools without opening a window (used by CI).

    Writes a JSON report to out_path because windowed apps have no console.
    """
    import json
    import subprocess

    from . import core, paths  # noqa: F401 - importing core checks the app's modules load

    report = {"ok": True}
    try:
        import yt_dlp

        report["yt_dlp"] = yt_dlp.version.__version__
        for name, path in (("ffmpeg", paths.ffmpeg_path()), ("deno", paths.deno_path())):
            if not path:
                report[name] = None
                report["ok"] = False
                continue
            flag = "-version" if name == "ffmpeg" else "--version"
            out = subprocess.run([path, flag], capture_output=True, text=True, timeout=60).stdout
            report[name] = out.splitlines()[0] if out else "no output"
        report["ui"] = os.path.isfile(os.path.join(paths.bundle_dir(), "youdownload", "ui", "index.html"))
        report["ok"] = report["ok"] and report["ui"]
    except Exception as e:  # noqa: BLE001
        report.update(ok=False, error=repr(e))
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    return 0 if report["ok"] else 1


def main():
    # Must run before yt_dlp is imported so a newer downloaded copy is used.
    from . import updater

    updater.activate()

    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        out = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "selftest.json"
        sys.exit(selftest(out))

    import webview

    from . import paths
    from .core import Api

    api = Api()
    html = os.path.join(paths.bundle_dir(), "youdownload", "ui", "index.html")
    window = webview.create_window(
        "YouDownload",
        url=html,
        js_api=api,
        width=720,
        height=820,
        min_size=(420, 560),
        background_color="#f5f5f7",
    )
    api._window = window
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
